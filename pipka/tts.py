"""Современная озвучка ответов с использованием нейросетевых голосов Microsoft Edge."""

import asyncio
import edge_tts
import pygame
import tempfile
import os
import threading
import queue
import re
import subprocess
import time
from pathlib import Path

from pipka.config import TTS_PITCH, TTS_RATE

# Настройка голоса: 'ru-RU-DmitryNeural' — приятный мужской голос
VOICE = "ru-RU-DmitryNeural"

def clean_for_speech(text):
    """Убирает лишнее из текста перед озвучкой."""
    text = str(text or "")
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[*_`#>•\[\]{}|~^]", " ", text)
    text = "".join(ch for ch in text if ord(ch) <= 0xFFFF)
    text = re.sub(r"\s*\n+\s*", ". ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

class Speaker:
    def __init__(self, on_error=None):
        self.on_error = on_error
        self._queue = queue.Queue()
        self._speaking = threading.Event()
        self._stop_event = threading.Event()
        self._edge_off_until = 0.0
        self._proc = None

        # Инициализируем pygame для воспроизведения звука
        pygame.mixer.init()

        # Запускаем отдельный поток для обработки очереди озвучки
        threading.Thread(target=self._loop, daemon=True).start()

    @staticmethod
    def available():
        return True # Edge-TTS работает почти везде при наличии интернета

    @property
    def speaking(self):
        return self._speaking.is_set() or not self._queue.empty()

    def say(self, text):
        text = clean_for_speech(text)
        if not text:
            return False
        self._speaking.set()
        self._queue.put(text)
        return True

    def stop(self):
        # Очищаем очередь
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass
        proc = self._proc
        if proc is not None and proc.poll() is None:
            proc.kill()
        self._speaking.clear()

    def _report(self, message):
        if self.on_error:
            self.on_error(message)

    def _loop(self):
        # Создаем отдельный цикл событий для asyncio (так как edge-tts асинхронный)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        while True:
            text = self._queue.get()
            try:
                loop.run_until_complete(self._speak_async(text))
            except Exception as exc:
                self._report(f"Ошибка озвучки: {exc}")
            finally:
                if self._queue.empty():
                    self._speaking.clear()

    async def _speak_async(self, text):
        # Онлайн-голос Microsoft Edge иногда ничего не возвращает (NoAudioReceived).
        # Тогда говорим встроенным голосом Windows и 10 минут Edge не трогаем.
        if time.time() >= self._edge_off_until:
            if await self._speak_edge(text):
                return
            self._edge_off_until = time.time() + 600
        self._speak_windows(text)

    def _speak_windows(self, text):
        """Встроенный русский голос Windows (Irina) через tts.ps1. Работает без интернета."""
        script = Path(__file__).with_name("tts.ps1")
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt", encoding="utf-8") as tmp:
                tmp.write(text)
                tmp_path = tmp.name
            env = dict(os.environ, PIPKA_TTS_FILE=tmp_path,
                       PIPKA_TTS_PITCH=TTS_PITCH, PIPKA_TTS_RATE=TTS_RATE)
            self._proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            _, err = self._proc.communicate()
            code = self._proc.returncode
            if code == 3:
                self._report("Нет русского голоса Windows: Параметры → Время и язык → Речь.")
            elif code not in (0, None) and not self._stop_event.is_set():
                message = err.decode("utf-8", errors="replace").strip()[:150]
                self._report(f"Ошибка озвучки Windows: {message or code}")
        except OSError as exc:
            self._report(f"Ошибка озвучки Windows: {exc}")
        finally:
            self._proc = None
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

    async def _speak_edge(self, text):
        """Возвращает True, если получилось сказать голосом Edge."""
        # Создаем временный файл для аудио
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
            tmp_path = tmp.name
        try:
            # Генерируем голос через Edge-TTS
            communicate = edge_tts.Communicate(text, VOICE)
            await communicate.save(tmp_path)
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            return False

        try:
            # Воспроизводим файл через pygame
            pygame.mixer.music.load(tmp_path)
            pygame.mixer.music.play()

            # Ждем, пока звук доиграет
            while pygame.mixer.music.get_busy():
                await asyncio.sleep(0.1)

            pygame.mixer.music.unload()
        except Exception as exc:
            self._report(f"Ошибка воспроизведения звука: {exc}")
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        return True
