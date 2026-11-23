"""Telegram-бот: управление ПИПКОЙ с телефона из любой сети.
Бот отвечает только одному привязанному чату (владельцу)."""

import hmac
import os
import secrets
import threading
import time

import requests

from pipka import keystore
from pipka.phone import PhoneAssistant

API = "https://api.telegram.org"
MAX_PARTS = 3500
MAX_WRONG_CODES = 5

HELP = (
    "Я ПИПКА на твоём компьютере 🎲 Пиши команды или вопросы:\n"
    "открой стим / майнкрафт / ютуб / emaktab, открой папку папа, закрой стим,\n"
    "громче, тише, пауза, включи на ютубе <запрос>, сделай скриншот,\n"
    "напомни через 10 минут <что>, погода, рулетка на красное, баланс.\n"
    "Или просто задай вопрос — отвечу как ИИ.\n"
    "Выключение и перезагрузка с телефона отключены.\n"
    "Внизу — кнопки для частых команд.\n"
    "/unpair — отвязать этот чат."
)

# Кнопки под полем ввода в Telegram: текст кнопки -> команда
BUTTONS = {
    "🎮 Steam": "открой стим",
    "⛏️ Minecraft": "открой майнкрафт",
    "🎒 eMaktab": "открой emaktab",
    "▶️ YouTube": "открой ютуб",
    "✈️ Telegram": "открой телеграм",
    "🕒 Время": "который час",
    "📸 Скриншот": "сделай скриншот",
    "🌦️ Погода": "какая погода",
    "🎡 Рулетка": "рулетка на красное",
    "🔊 Громче": "громче",
    "🔉 Тише": "тише",
    "⏯️ Пауза": "пауза",
    "🪙 Баланс": "баланс",
    "❓ Помощь": "помощь",
}
KEYBOARD = {
    "keyboard": [
        [{"text": "🎮 Steam"}, {"text": "⛏️ Minecraft"}, {"text": "🎒 eMaktab"}],
        [{"text": "▶️ YouTube"}, {"text": "✈️ Telegram"}, {"text": "🕒 Время"}],
        [{"text": "📸 Скриншот"}, {"text": "🌦️ Погода"}, {"text": "🎡 Рулетка"}],
        [{"text": "🔊 Громче"}, {"text": "🔉 Тише"}, {"text": "⏯️ Пауза"}],
        [{"text": "🪙 Баланс"}, {"text": "❓ Помощь"}],
    ],
    "resize_keyboard": True,
}


def split_text(text, size=MAX_PARTS):
    text = str(text)
    parts = []
    while len(text) > size:
        cut = text.rfind("\n", 0, size)
        if cut < size // 2:
            cut = text.rfind(" ", 0, size)
        if cut < size // 2:
            cut = size
        parts.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    if text or not parts:
        parts.append(text)
    return parts


class TelegramBot:
    def __init__(self, on_event=None):
        self.token = keystore.get_telegram_token()
        self.owner = keystore.get_telegram_owner()
        self.pair_code = str(secrets.randbelow(900000) + 100000)
        self.on_event = on_event or (lambda message: None)
        self.assistant = PhoneAssistant()
        self.wrong_codes = 0
        self.username = ""
        self._stop = threading.Event()
        self._thread = None
        self._last_error = ""

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        if not self.token:
            raise ValueError("Нет токена бота.")
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    # ---------- работа с Telegram ----------
    def _call(self, method, params, timeout=(5, 15)):
        try:
            response = requests.post(
                f"{API}/bot{self.token}/{method}", json=params, timeout=timeout
            )
        except requests.Timeout as exc:
            raise ConnectionError("Telegram не ответил вовремя.") from exc
        except requests.RequestException as exc:
            raise ConnectionError("Нет связи с Telegram (проверь интернет).") from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise ConnectionError("Telegram вернул непонятный ответ.") from exc

        if not data.get("ok"):
            code = data.get("error_code")
            if code == 401:
                raise PermissionError("Telegram не принял токен бота. Проверь его в ⚙ Настройках.")
            if code == 409:
                raise BlockingIOError("Бот уже запущен в другом месте.")
            raise ConnectionError(f"Ошибка Telegram {code}: {str(data.get('description', ''))[:120]}")

        return data.get("result")

    def send(self, chat_id, text, keyboard=True):
        for part in split_text(text):
            payload = {"chat_id": chat_id, "text": part}
            if keyboard:
                payload["reply_markup"] = KEYBOARD
            try:
                self._call("sendMessage", payload)
            except ConnectionError as exc:
                self._report(str(exc))
                return

    def send_photo(self, chat_id, path):
        """Отправляет картинку (скриншот). Большие снимки — файлом, без сжатия."""
        try:
            with open(path, "rb") as file:
                response = requests.post(
                    f"{API}/bot{self.token}/sendPhoto",
                    data={"chat_id": chat_id},
                    files={"photo": (os.path.basename(path), file, "image/png")},
                    timeout=(5, 60),
                )
            if response.ok and response.json().get("ok"):
                return
            with open(path, "rb") as file:
                requests.post(
                    f"{API}/bot{self.token}/sendDocument",
                    data={"chat_id": chat_id},
                    files={"document": (os.path.basename(path), file, "image/png")},
                    timeout=(5, 120),
                )
        except (OSError, requests.RequestException, ValueError) as exc:
            self._report(f"Не удалось отправить скриншот в Telegram: {exc}")

    def _report(self, message):
        if message != self._last_error:
            self._last_error = message
            self.on_event(message)

    def _loop(self):
        try:
            me = self._call("getMe", {})
            self.username = (me or {}).get("username", "")
            self.on_event(f"Telegram-бот @{self.username} запущен.")
            if self.owner is None:
                self.on_event(
                    f"Код привязки: {self.pair_code}. Открой в Telegram бота @{self.username}, "
                    f"нажми «Старт» и отправь ему этот код."
                )
            self._last_error = ""
        except PermissionError as exc:
            self.on_event(str(exc))
            return
        except (ConnectionError, BlockingIOError) as exc:
            self._report(str(exc))
            self.username = ""

        offset = None

        while not self._stop.is_set():
            try:
                if offset is None:
                    # старые сообщения не выполняем: берём только то, что придёт после запуска
                    pending = self._call("getUpdates", {"offset": -1, "timeout": 0}) or []
                    offset = pending[-1]["update_id"] + 1 if pending else 0

                updates = self._call(
                    "getUpdates",
                    {"offset": offset, "timeout": 25, "allowed_updates": ["message"]},
                    timeout=(5, 40),
                ) or []
                self._last_error = ""

                for update in updates:
                    offset = update["update_id"] + 1
                    try:
                        self.handle_update(update)
                    except Exception as exc:  # одно плохое сообщение не должно ронять бота
                        self.on_event(f"Ошибка при обработке сообщения: {exc}")

            except PermissionError as exc:
                self.on_event(str(exc))
                return
            except BlockingIOError:
                self._stop.wait(3)
            except ConnectionError as exc:
                self._report(str(exc))
                self._stop.wait(5)
            except Exception as exc:
                self._report(f"Сбой Telegram-бота: {exc}")
                self._stop.wait(5)

    # ---------- обработка сообщений ----------
    def handle_update(self, update):
        message = update.get("message") or {}
        text = message.get("text")
        chat = message.get("chat") or {}

        if not text or chat.get("type") != "private":
            return

        chat_id = chat.get("id")
        text = text.strip()

        if self.owner is None:
            self._handle_pairing(chat_id, text)
            return

        if chat_id != self.owner:
            return  # чужим не отвечаем

        text = BUTTONS.get(text, text)
        low = text.lower()

        if low.startswith("/start") or low.startswith("/help"):
            self.send(chat_id, HELP)
        elif low.startswith("/unpair"):
            keystore.clear_telegram_owner()
            self.owner = None
            self.pair_code = str(secrets.randbelow(900000) + 100000)
            self.send(
                chat_id,
                "Чат отвязан. Чтобы привязать снова, выключи и включи Telegram-бот "
                "в ПИПКЕ: появится новый код.",
                keyboard=False,
            )
            self.on_event("Телефон отвязан от Telegram-бота.")
        elif text:
            self.send(chat_id, self.assistant.reply(text))
            if self.assistant.last_photo:
                self.send_photo(chat_id, self.assistant.last_photo)

    def _handle_pairing(self, chat_id, text):
        parts = text.split(maxsplit=1)
        command = parts[0].lower() if parts else ""

        # Можно прислать просто код из 6 цифр, без /pair
        if command.isdigit() and len(command) == 6:
            parts = ["/pair", command]
            command = "/pair"

        if command != "/pair":
            self.send(
                chat_id,
                "Привет! Чтобы привязать меня к этому чату, отправь код из 6 цифр — "
                "он написан в окне ПИПКИ на компьютере.",
                keyboard=False,
            )
            return

        if self.wrong_codes >= MAX_WRONG_CODES:
            self.send(
                chat_id,
                "Слишком много неверных попыток. Выключи и снова включи бота в ПИПКЕ.",
                keyboard=False,
            )
            return

        supplied = parts[1].strip() if len(parts) > 1 else ""

        if hmac.compare_digest(supplied.encode("utf-8"), self.pair_code.encode("utf-8")):
            keystore.save_telegram_owner(chat_id)
            self.owner = chat_id
            self.send(chat_id, "Готово, чат привязан. Напиши: помощь")
            self.on_event("Телефон привязан к Telegram-боту.")
        else:
            self.wrong_codes += 1
            self.send(chat_id, "Неверный код.", keyboard=False)
