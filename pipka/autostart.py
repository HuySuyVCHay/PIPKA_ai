"""Запуск ПИПКИ вместе с системой.

Windows: батник PIPKA.bat в папке «Автозагрузка», Windows выполняет его после входа.
Mac: файл com.pipka.assistant.plist в ~/Library/LaunchAgents, macOS запускает ПИПКУ
после входа. Удаление файла выключает автозапуск."""

import os
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from pipka.system import IS_MAC, IS_WINDOWS

FILE_NAME = "PIPKA.bat"
MAC_LABEL = "com.pipka.assistant"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def startup_dir():
    if IS_MAC:
        return Path.home() / "Library" / "LaunchAgents"
    base = os.environ.get("APPDATA")
    if not base:
        return None
    return Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def startup_file():
    folder = startup_dir()
    if folder is None:
        return None
    return folder / (f"{MAC_LABEL}.plist" if IS_MAC else FILE_NAME)


def build_plist(arguments, workdir):
    """LaunchAgent для Mac: какую программу запустить после входа."""
    items = "\n".join(f"        <string>{escape(str(a))}</string>" for a in arguments)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{MAC_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
{items}
    </array>
    <key>WorkingDirectory</key>
    <string>{escape(str(workdir))}</string>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
"""


def _enable_mac():
    path = startup_file()
    if getattr(sys, "frozen", False):
        arguments, workdir = [sys.executable], Path(sys.executable).parent
    else:
        arguments, workdir = [sys.executable, str(PROJECT_ROOT / "main.py")], PROJECT_ROOT
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(build_plist(arguments, workdir), encoding="utf-8")
    except OSError as exc:
        return False, f"Не удалось включить автозапуск: {exc}"
    return True, "Готово: ПИПКА будет запускаться после входа в macOS."


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
    if IS_MAC:
        return _enable_mac()
    if not IS_WINDOWS:
        return False, "Автозапуск работает только в Windows и на Mac."

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
    if not IS_WINDOWS and not IS_MAC:
        return False, "Автозапуск работает только в Windows и на Mac."

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
