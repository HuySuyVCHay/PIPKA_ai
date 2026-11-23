"""Распознавание русской речи без интернета (Vosk) и слово-активатор «ПИПКА»."""

import json
import queue
import threading
import time

import requests

from pipka.config import PROJECT_DIR, WAKE_PREFIXES, WAKE_WORDS

MODELS_DIR = PROJECT_DIR / "models"
SAMPLE_RATE = 16000
ONCE_TIMEOUT = 20      # сколько секунд ждать речь по кнопке «Сказать»
AWAIT_COMMAND = 8      # сколько секунд ждать команду после слова «ПИПКА»
MAX_UTTERANCE = SAMPLE_RATE * 2 * 20   # не больше 20 секунд звука на одну фразу

# Онлайн-распознавание Google: слово «ПИПКА» ловит Vosk без интернета,
# а саму команду точнее распознаёт Google (понимает и английские названия).
# Нет интернета — остаётся текст от Vosk.
ONLINE_STT = True
GOOGLE_STT_URL = "https://www.google.com/speech-api/v2/recognize"
GOOGLE_STT_KEY = "AIzaSyBOti4mM-6x9WDnZIjIeyEU21OpBXqWBgw"


def recognize_online(pcm):
    """Распознаёт фразу (16 кГц, 16 бит, моно) через Google. Возвращает текст или ""."""
    if not ONLINE_STT or len(pcm) < SAMPLE_RATE // 2:
        return ""
    try:
        response = requests.post(
            GOOGLE_STT_URL,
            params={"client": "chromium", "lang": "ru-RU", "key": GOOGLE_STT_KEY},
            data=bytes(pcm),
            headers={"Content-Type": f"audio/l16; rate={SAMPLE_RATE}"},
            timeout=(3, 6),
        )
    except requests.RequestException:
        return ""
    if response.status_code != 200:
        return ""
    for line in response.text.splitlines():
        try:
            data = json.loads(line)
        except ValueError:
            continue
        for result in data.get("result", []):
            alternatives = result.get("alternative") or []
            if alternatives and alternatives[0].get("transcript"):
                return alternatives[0]["transcript"].strip()
    return ""


def after_wake(online_text, offline_text):
    """Текст команды после слова «ПИПКА» из онлайн-результата.
    Если Google записал «ПИПКА» иначе — отрезаем столько же первых слов, сколько у Vosk."""
    found, rest = split_wake(online_text)
    if found:
        return rest
    offline_words = norm(offline_text).split()
    wake = {norm(w).strip() for w in WAKE_WORDS}
    prefixes = tuple(norm(p).strip() for p in WAKE_PREFIXES)
    skip = 0
    for index, word in enumerate(offline_words):
        if word in wake or word.startswith(prefixes):
            skip = index + 1
            break
    return " ".join(online_text.split()[skip:])

_model = None
_model_lock = threading.Lock()


def norm(text):
    text = str(text).lower().replace("ё", "е")
    return "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text)


def split_wake(text):
    """Ищет слово-активатор. Возвращает (нашли, остаток после него)."""
    wake = {norm(w).strip() for w in WAKE_WORDS}
    words = norm(text).split()
    prefixes = tuple(norm(p).strip() for p in WAKE_PREFIXES)
    for index, word in enumerate(words):
        if word in wake or (len(word) <= 8 and word.startswith(prefixes)):
            return True, " ".join(words[index + 1:])
    return False, ""


def libs_available():
    """Проверяет, что установлены vosk и sounddevice. Возвращает (да/нет, причина)."""
    try:
        import sounddevice  # noqa: F401
        import vosk  # noqa: F401
    except Exception as exc:
        return False, str(exc)
    return True, ""


def find_local_model():
    """Ищет скачанную вручную модель в папке models/."""
    if not MODELS_DIR.is_dir():
        return None
    for folder in sorted(MODELS_DIR.iterdir()):
        if folder.is_dir() and ((folder / "am").is_dir() or (folder / "conf").is_dir()):
            return folder
        if folder.is_dir():
            # модель могла распаковаться в папку внутри папки
            for inner in sorted(folder.iterdir()):
                if inner.is_dir() and ((inner / "am").is_dir() or (inner / "conf").is_dir()):
                    return inner
    return None


def load_model(on_status):
    global _model
    with _model_lock:
        if _model is not None:
            return _model

        import vosk

        vosk.SetLogLevel(-1)
        local = find_local_model()

        try:
            if local is not None:
                on_status("Загружаю модель распознавания речи…")
                _model = vosk.Model(model_path=str(local))
            else:
                on_status("Скачиваю русскую модель речи (около 45 МБ), подожди…")
                _model = vosk.Model(lang="ru")
        except Exception as exc:
            raise RuntimeError(
                "Не удалось загрузить модель распознавания речи. Скачай "
                "vosk-model-small-ru-0.22 с alphacephei.com/vosk/models, распакуй "
                f"в папку {MODELS_DIR} и попробуй снова. ({exc})"
            ) from exc

        return _model


class VoiceListener:
    """Слушает микрофон в отдельном потоке.
    mode «once» — одна фраза по кнопке; mode «wake» — ждёт слово «ПИПКА»."""

    def __init__(self, on_status, on_heard, on_text, on_wake, on_error,
                 on_stopped, is_muted):
        self.on_status = on_status
        self.on_heard = on_heard
        self.on_text = on_text
        self.on_wake = on_wake
        self.on_error = on_error
        self.on_stopped = on_stopped
        self.is_muted = is_muted
        self._thread = None
        self._stop = threading.Event()
        self.mode = ""
        self.session = 0
        self._awaiting_until = 0.0

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self, mode):
        if self.running:
            self._stop.set()
            self._thread.join(timeout=3)
            if self.running:
                return False
        self._stop.clear()
        self.mode = mode
        self.session += 1
        self._thread = threading.Thread(
            target=self._run, args=(mode, self.session), daemon=True
        )
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()

    def expect_command(self, seconds=AWAIT_COMMAND):
        """Следующую фразу принять как команду без слова «ПИПКА»
        (например, после вопроса «Что открыть?»)."""
        self._awaiting_until = time.time() + seconds

    def _run(self, mode, session):
        try:
            ok, reason = libs_available()
            if not ok:
                self.on_error(
                    "Для голоса нужны библиотеки vosk и sounddevice. Выполни в терминале: "
                    "python -m pip install -r requirements_voice.txt  "
                    f"(причина: {reason})"
                )
                return

            import sounddevice as sd
            import vosk

            model = load_model(self.on_status)
            recognizer = vosk.KaldiRecognizer(model, SAMPLE_RATE)
            audio = queue.Queue(maxsize=300)

            def callback(indata, frames, time_info, status):
                try:
                    audio.put_nowait(bytes(indata))
                except queue.Full:
                    pass

            with sd.RawInputStream(
                samplerate=SAMPLE_RATE,
                blocksize=4000,
                dtype="int16",
                channels=1,
                callback=callback,
            ):
                if mode == "once":
                    self.on_status("Слушаю: говори…")
                else:
                    self.on_status("Жду слово «ПИПКА»…")

                started = time.time()
                self._awaiting_until = 0.0
                was_muted = False
                utterance = bytearray()

                while not self._stop.is_set():
                    if mode == "once" and time.time() - started > ONCE_TIMEOUT:
                        self.on_status("Ничего не услышала.")
                        break

                    if self.is_muted():
                        # пока ПИПКА говорит, микрофон не слушаем (чтобы не слышать саму себя)
                        try:
                            while True:
                                audio.get_nowait()
                        except queue.Empty:
                            pass
                        was_muted = True
                        time.sleep(0.1)
                        continue

                    if was_muted:
                        recognizer = vosk.KaldiRecognizer(model, SAMPLE_RATE)
                        was_muted = False
                        started = time.time()
                        utterance = bytearray()

                    try:
                        data = audio.get(timeout=0.3)
                    except queue.Empty:
                        continue

                    utterance.extend(data)
                    if len(utterance) > MAX_UTTERANCE:
                        del utterance[:len(utterance) - MAX_UTTERANCE]

                    if not recognizer.AcceptWaveform(data):
                        continue

                    pcm, utterance = utterance, bytearray()
                    text = json.loads(recognizer.Result()).get("text", "").strip()
                    if not text:
                        continue

                    now = time.time()
                    wants_command = mode == "once" or now < self._awaiting_until
                    found, rest = (False, "") if wants_command else split_wake(text)

                    # Онлайн-распознавание только для команд: фоновые разговоры не отправляем
                    online = recognize_online(pcm) if (wants_command or (found and rest)) else ""
                    self.on_heard(f"{text}  →  {online}" if online else text)

                    if mode == "once":
                        self.on_text(online or text)
                        break

                    if wants_command:
                        self._awaiting_until = 0.0
                        self.on_text(online or text)
                        continue

                    if found:
                        if rest:
                            self.on_text((after_wake(online, text) if online else "") or rest)
                        else:
                            self._awaiting_until = now + AWAIT_COMMAND
                            self.on_wake()

        except Exception as exc:
            self.on_error(f"Микрофон или распознавание не запустились: {exc}")
        finally:
            if session == self.session:
                self.on_status("Микрофон выключен.")
            self.on_stopped(session)
