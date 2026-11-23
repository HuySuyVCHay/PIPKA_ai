"""Хранение секретов в файлах рядом с программой: ключ Gemini и токен Telegram-бота."""

import os
import re

from pipka.config import PROJECT_DIR

GEMINI_KEY_FILE = PROJECT_DIR / "gemini_key.txt"
TELEGRAM_TOKEN_FILE = PROJECT_DIR / "telegram_token.txt"
TELEGRAM_OWNER_FILE = PROJECT_DIR / "telegram_owner.txt"

TELEGRAM_TOKEN_RE = re.compile(r"^\d{6,}:[A-Za-z0-9_-]{30,}$")


def clean_key(text):
    return str(text or "").strip().strip('"').strip("'").strip()


def get_gemini_key():
    """Ключ из файла gemini_key.txt, а если файла нет — из переменной GEMINI_API_KEY."""
    try:
        with open(GEMINI_KEY_FILE, "r", encoding="utf-8") as file:
            key = clean_key(file.read())
            if key:
                return key
    except OSError:
        pass
    return clean_key(os.environ.get("GEMINI_API_KEY", ""))


def save_gemini_key(key):
    """Сохраняет ключ. Возвращает (успех, сообщение)."""
    key = clean_key(key)
    if len(key) < 20 or " " in key or "\n" in key:
        return False, "Это не похоже на ключ Gemini: он длинный и без пробелов."
    try:
        with open(GEMINI_KEY_FILE, "w", encoding="utf-8") as file:
            file.write(key)
    except OSError as exc:
        return False, f"Не удалось сохранить ключ: {exc}"
    return True, "Ключ Gemini сохранён."


def delete_gemini_key():
    try:
        os.remove(GEMINI_KEY_FILE)
    except FileNotFoundError:
        pass
    except OSError as exc:
        return False, f"Не удалось удалить ключ: {exc}"
    return True, "Ключ Gemini удалён."


# ---------- Telegram-бот ----------
def get_telegram_token():
    try:
        with open(TELEGRAM_TOKEN_FILE, "r", encoding="utf-8") as file:
            return clean_key(file.read())
    except OSError:
        return ""


def save_telegram_token(token):
    """Сохраняет токен бота от @BotFather. Возвращает (успех, сообщение)."""
    token = clean_key(token)
    if not TELEGRAM_TOKEN_RE.match(token):
        return False, "Это не похоже на токен бота: он выглядит как 123456789:AAH... (из @BotFather)."
    try:
        with open(TELEGRAM_TOKEN_FILE, "w", encoding="utf-8") as file:
            file.write(token)
    except OSError as exc:
        return False, f"Не удалось сохранить токен: {exc}"
    return True, "Токен бота сохранён."


def get_telegram_owner():
    """Номер чата, к которому привязан бот (или None)."""
    try:
        with open(TELEGRAM_OWNER_FILE, "r", encoding="utf-8") as file:
            return int(file.read().strip())
    except (OSError, ValueError):
        return None


def save_telegram_owner(chat_id):
    try:
        with open(TELEGRAM_OWNER_FILE, "w", encoding="utf-8") as file:
            file.write(str(int(chat_id)))
    except (OSError, ValueError):
        return False
    return True


def clear_telegram_owner():
    try:
        os.remove(TELEGRAM_OWNER_FILE)
    except FileNotFoundError:
        pass
    except OSError:
        return False
    return True
