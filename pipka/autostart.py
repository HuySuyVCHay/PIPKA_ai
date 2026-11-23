"""Запуск ПИПКИ вместе с Windows.

Создаётся батник PIPKA.bat в папке «Автозагрузка» пользователя. Windows выполняет его
после входа в систему. Удаление батника выключает автозапуск."""

import os
import sys
from pathlib import Path

IS_WINDOWS = os.name == "nt"
FILE_NAME = "PIPKA.bat"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def startup_dir():
    base = os.environ.get("APPDATA")
    if not base:
        return None
    return Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def startup_file():
    folder = startup_dir()
    return folder / FILE_NAME if folder is not None else None


def build_script(frozen, program, root, pythonw):
    """Текст батника. Готовая программа запускает PIPKA.exe, иначе main.py через pythonw."""
    lines = ["@echo off", "chcp 65001 >nul"]
    if frozen:
        lines.append(f'start "" "{program}"')
    else:
        lines.append(f'cd /d "{root}"')
        lines.append(f'start "" "{pythonw}" "{Path(root) / "main.py"}"')
    return "\r\n".join(lines) + "\r\n"


def is_enabled():
    path = startup_file()
    return path is not None and path.exists()


def enable(frozen=None, program=None, root=None, pythonw=None):
    if not IS_WINDOWS:
        return False, "Автозапуск работает только в Windows."

    path = startup_file()
    if path is None:
        return False, "Не нашла папку «Автозагрузка» (переменная APPDATA не задана)."

    if frozen is None:
        frozen = getattr(sys, "frozen", False)
    if frozen:
        program = program or sys.executable
    root = root or PROJECT_ROOT
    if pythonw is None:
        pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not frozen and not Path(pythonw).exists():
        return False, f"Не нашла {pythonw}. Запусти ПИПКУ через PIPKA.exe или из папки .venv."

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(build_script(frozen, program, root, pythonw).encode("utf-8"))
    except OSError as exc:
        return False, f"Не удалось включить автозапуск: {exc}"

    return True, "Готово: ПИПКА будет запускаться после входа в Windows."


def disable():
    if not IS_WINDOWS:
        return False, "Автозапуск работает только в Windows."

    path = startup_file()
    if path is None:
        return False, "Не нашла папку «Автозагрузка» (переменная APPDATA не задана)."

    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        return False, f"Не удалось выключить автозапуск: {exc}"

    return True, "Автозапуск выключен."
