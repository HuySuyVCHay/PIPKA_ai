#!/bin/bash
# Сборка ПИПКИ для Mac. Двойной клик в Finder или в Терминале: ./build_mac.command
set -e
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Не найден python3. Установи Python 3.12 или 3.13 с сайта python.org и запусти снова."
    read -r -p "Нажми Enter, чтобы закрыть..."
    exit 1
fi

if [ ! -x .venv/bin/python ]; then
    echo "[1/3] Создаю окружение .venv..."
    python3 -m venv .venv
fi

echo "[2/3] Ставлю библиотеки (несколько минут, нужен интернет)..."
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt -r requirements_voice.txt pyinstaller pillow

echo "[3/3] Собираю PIPKA.app..."
.venv/bin/python -m PyInstaller --noconfirm --clean pipka_mac.spec

echo
echo "Готово: dist/PIPKA.app"
echo "Перетащи PIPKA.app в папку «Программы» и открой (первый раз — правой кнопкой → Открыть)."
open dist
read -r -p "Нажми Enter, чтобы закрыть..."
