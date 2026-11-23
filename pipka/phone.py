"""Общий «мозг» для телефона: страница по Wi-Fi и Telegram-бот отвечают одинаково.
Команды выполняются обычным кодом, но опасные (выключение, память) отключены."""

import threading

from pipka import ai, commands
from pipka.database import ChatDatabase

MAX_HISTORY = 10


class PhoneAssistant:
    def __init__(self):
        self._history = []
        self._lock = threading.Lock()
        self.last_photo = ""

    def reply(self, text):
        self.last_photo = ""
        try:
            command = commands.handle(text, remote=True)
        except Exception as exc:
            return f"Не получилось выполнить команду: {exc}"

        if command.handled:
            self.last_photo = command.photo
            return command.message

        with self._lock:
            history = self._history[-MAX_HISTORY:] + [{"role": "user", "content": text}]

            facts = []
            try:
                db = ChatDatabase()
                try:
                    facts = db.facts()
                finally:
                    db.close()
            except Exception:
                facts = []

            try:
                answer = ai.ask(history, facts)
            except Exception as exc:
                return f"Не получилось ответить: {exc}"

            self._history = history + [{"role": "assistant", "content": answer}]
            return answer
