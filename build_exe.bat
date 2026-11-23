@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo The .venv folder was not found. Create it first:
  echo   python -m venv .venv
  echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
  echo   .venv\Scripts\python.exe -m pip install -r requirements_voice.txt
  pause
  exit /b 1
)

echo [1/4] Installing PyInstaller...
".venv\Scripts\python.exe" -m pip install pyinstaller
if errorlevel 1 goto failed

set EXTRA=
".venv\Scripts\python.exe" -c "import vosk" 2>nul && set EXTRA=%EXTRA% --collect-all vosk
".venv\Scripts\python.exe" -c "import sounddevice" 2>nul && set EXTRA=%EXTRA% --collect-all sounddevice

echo [2/4] Building PIPKA.exe (this takes a few minutes)...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --windowed --name PIPKA --icon "assets\pipka.ico" --add-data "pipka\tts.ps1;pipka" --add-data "assets;assets" %EXTRA% main.py
if errorlevel 1 goto failed

set DATA=%APPDATA%\PIPKA
if not exist "%DATA%" mkdir "%DATA%"

echo [3/4] Copying your data to %DATA% (only files that are not there yet)...
for %%F in (pipka_memory.sqlite3 gemini_key.txt apps.json aliases.json telegram_token.txt telegram_owner.txt) do (
  if not exist "%DATA%\%%F" if exist "%%F" copy /Y "%%F" "%DATA%\" >nul
)
if not exist "%DATA%\models" if exist "models" xcopy /E /I /Y "models" "%DATA%\models" >nul

echo [4/4] Creating the desktop shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0make_shortcut.ps1"

echo.
echo Done. Start PIPKA from the desktop shortcut (PIPKA) or from dist\PIPKA\PIPKA.exe.
pause
exit /b 0

:failed
echo.
echo Build failed. Copy the text above and send it to the assistant.
pause
exit /b 1
