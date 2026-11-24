"""Всё, что на Windows и Mac делается по-разному: открыть файл, звук, папка данных, шрифт.
Остальной код зовёт эти функции и не думает, на какой он системе."""

import os
import subprocess
import sys
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

FONT = "Segoe UI" if IS_WINDOWS else ("Helvetica Neue" if IS_MAC else "Sans Serif")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

try:
    import winsound
except ImportError:
    winsound = None


def data_dir():
    """Папка с данными готового приложения (память, ключи, настройки)."""
    if IS_WINDOWS:
        return Path(os.environ.get("APPDATA") or Path.home()) / "PIPKA"
    if IS_MAC:
        return Path.home() / "Library" / "Application Support" / "PIPKA"
    return Path.home() / ".pipka"


def open_path(target):
    """Открывает файл, папку, программу или ссылку так, как это сделал бы двойной клик."""
    target = str(target)
    if IS_WINDOWS:
        os.startfile(target)
    elif IS_MAC:
        subprocess.Popen(["open", target])
    else:
        subprocess.Popen(["xdg-open", target])


def reveal(path):
    """Показывает файл выделенным в папке (Проводник / Finder)."""
    if IS_WINDOWS:
        subprocess.Popen(["explorer", "/select,", str(path)])
    elif IS_MAC:
        subprocess.Popen(["open", "-R", str(path)])
    else:
        open_path(Path(path).parent)


MAC_SOUNDS = {"low": "Tink", "mid": "Glass", "high": "Hero"}


def beep(freq=880, ms=120):
    """Короткий звуковой сигнал. На Mac — системный звук, ближайший по высоте."""
    if winsound is not None:
        try:
            winsound.Beep(int(freq), int(ms))
        except RuntimeError:
            pass
        return
    if IS_MAC:
        name = MAC_SOUNDS["low" if freq < 900 else ("mid" if freq < 1300 else "high")]
        try:
            subprocess.Popen(["afplay", f"/System/Library/Sounds/{name}.aiff"])
        except OSError:
            pass


def osascript(script, timeout=10):
    """Выполняет AppleScript на Mac. Возвращает (успех, вывод)."""
    try:
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True,
                                timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    return result.returncode == 0, (result.stdout or result.stderr).strip()
