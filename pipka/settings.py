"""Настройки, которые помнятся между запусками (файл settings.json в папке данных)."""

import json

from pipka.config import PROJECT_DIR

SETTINGS_FILE = PROJECT_DIR / "settings.json"
DEFAULTS = {"bot_on_start": False, "wake_on_start": False}


def load():
    data = dict(DEFAULTS)
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as file:
            stored = json.load(file)
        if isinstance(stored, dict):
            for key in DEFAULTS:
                if key in stored:
                    data[key] = bool(stored[key])
    except (OSError, ValueError):
        pass
    return data


def get(key, default=False):
    data = load()
    return data.get(key, default)


def save(changes):
    """Сохраняет только известные настройки. Возвращает True, если записалось."""
    data = load()
    for key, value in changes.items():
        if key in DEFAULTS:
            data[key] = bool(value)
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
    except OSError:
        return False
    return True
