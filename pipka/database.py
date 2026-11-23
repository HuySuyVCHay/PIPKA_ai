import functools
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from pipka.config import PROJECT_DIR

DEFAULT_PATH = PROJECT_DIR / "pipka_memory.sqlite3"


def _locked(method):
    """Базой пользуются окно и фоновые потоки (команды, Telegram), поэтому по очереди."""
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self.lock:
            return method(self, *args, **kwargs)
    return wrapper


class ChatDatabase:
    def __init__(self, path=None):
        # База всегда лежит в папке проекта, откуда бы ни запустили main.py
        self.path = Path(path) if path else DEFAULT_PATH
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS messages ("
            "id INTEGER PRIMARY KEY, "
            "role TEXT NOT NULL, "
            "content TEXT NOT NULL, "
            "created_at TEXT NOT NULL)"
        )
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS facts ("
            "id INTEGER PRIMARY KEY, "
            "text TEXT NOT NULL, "
            "created_at TEXT NOT NULL)"
        )
        self.conn.commit()

    @_locked
    def add(self, role, content):
        self.conn.execute(
            "INSERT INTO messages(role,content,created_at) VALUES(?,?,?)",
            (role, content, datetime.now().isoformat(timespec="seconds")),
        )
        self.conn.commit()

    @_locked
    def recent(self, limit=20):
        rows = self.conn.execute(
            "SELECT role,content FROM messages ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        rows.reverse()
        return [{"role": r, "content": c} for r, c in rows]

    @_locked
    def remove_last_if_user(self):
        """Удаляет последнее сообщение, если это вопрос без ответа
        (нужно, когда модель не смогла ответить)."""
        row = self.conn.execute(
            "SELECT id, role FROM messages ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row and row[1] == "user":
            self.conn.execute("DELETE FROM messages WHERE id=?", (row[0],))
            self.conn.commit()

    @_locked
    def clear_messages(self):
        self.conn.execute("DELETE FROM messages")
        self.conn.commit()

    @_locked
    def count_messages(self):
        return self.conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]

    # ----- факты, которые ПИПКА запомнила о пользователе -----
    @_locked
    def add_fact(self, text):
        text = str(text).strip()
        if not text:
            return
        self.conn.execute(
            "INSERT INTO facts(text,created_at) VALUES(?,?)",
            (text, datetime.now().isoformat(timespec="seconds")),
        )
        self.conn.commit()

    @_locked
    def facts(self, limit=30):
        rows = self.conn.execute(
            "SELECT text FROM facts ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        rows.reverse()
        return [r[0] for r in rows]

    @_locked
    def clear_facts(self):
        self.conn.execute("DELETE FROM facts")
        self.conn.commit()

    @_locked
    def close(self):
        self.conn.close()
