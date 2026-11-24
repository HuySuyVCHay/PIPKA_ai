"""Дополнительные команды ПИПКИ: звук и музыка, «закрой программу», поиск на YouTube,
таймеры и напоминания, скриншот, казино (фишки, рулетка, монетка) и погода.

handle(n) получает уже очищенную фразу в нижнем регистре и возвращает
{"message": ..., "photo": путь_или_""} или None, если это не наша команда."""

import ctypes
import json
import os
import random
import re
import subprocess
import threading
import time
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote_plus

import requests

from pipka import apps, files
from pipka.config import PROJECT_DIR, WAKE_PREFIXES
from pipka.system import IS_MAC, NO_WINDOW, osascript

# Окно ПИПКИ подписывается сюда, чтобы показывать напоминания и обновлять фишки
on_reminder = None   # функция(текст)



def _reply(message, photo=""):
    return {"message": message, "photo": photo}


# ---------- звук и музыка ----------
VK_VOLUME_MUTE, VK_VOLUME_DOWN, VK_VOLUME_UP = 0xAD, 0xAE, 0xAF
VK_NEXT, VK_PREV, VK_PLAY = 0xB0, 0xB1, 0xB3

VOLUME_UP_RE = re.compile(
    r"^(?:сделай\s+)?(?:громче|погромче|прибавь(?:\s+звук|\s+громкость)?|"
    r"увеличь\s+(?:звук|громкость))(?:\s+на\s+(\d+)(?:\s*%|\s+процент\w*)?)?$")
VOLUME_DOWN_RE = re.compile(
    r"^(?:сделай\s+)?(?:тише|потише|убавь(?:\s+звук|\s+громкость)?|"
    r"уменьши\s+(?:звук|громкость))(?:\s+на\s+(\d+)(?:\s*%|\s+процент\w*)?)?$")
VOLUME_MAX_RE = re.compile(r"^(?:звук|громкость)\s+на\s+(?:максимум|полную|сто|100)$")
MUTE_RE = re.compile(r"^(?:выключи|отключи|включи|верни)\s+звук$|^без\s+звука$")
PLAY_RE = re.compile(
    r"^(?:пауза|на\s+паузу|поставь\s+на\s+паузу|сними\s+с\s+паузы|продолжи|продолжай|"
    r"стоп\s+музыка|останови\s+музыку|играй\s+дальше)$")
NEXT_RE = re.compile(r"^(?:следующ(?:ий|ая|ее|ую)(?:\s+(?:трек|песн[яю]|видео))?|переключи\s+трек)$")
PREV_RE = re.compile(r"^(?:предыдущ(?:ий|ая|ее|ую)(?:\s+(?:трек|песн[яю]|видео))?)$")


def _press(key, times=1):
    if os.name != "nt":
        return
    user32 = ctypes.windll.user32
    for _ in range(times):
        user32.keybd_event(key, 0, 0, 0)
        user32.keybd_event(key, 0, 2, 0)


# На Mac звук и музыка управляются через AppleScript
MAC_PLAYER = """
if application "Spotify" is running then
    tell application "Spotify" to {action}
else if application "Music" is running then
    tell application "Music" to {action}
end if
"""


def _volume(percent):
    if IS_MAC:
        osascript(f"set volume output volume ((output volume of (get volume settings)) + {percent})")
    else:
        _press(VK_VOLUME_UP if percent > 0 else VK_VOLUME_DOWN, max(1, abs(percent) // 2))


def _volume_max():
    if IS_MAC:
        osascript("set volume output volume 100")
    else:
        _press(VK_VOLUME_UP, 50)


def _mute():
    if IS_MAC:
        osascript("set volume output muted not (output muted of (get volume settings))")
    else:
        _press(VK_VOLUME_MUTE)


def _player(action):
    """action: playpause, next track, previous track."""
    if IS_MAC:
        osascript(MAC_PLAYER.format(action=action))
    else:
        _press({"playpause": VK_PLAY, "next track": VK_NEXT, "previous track": VK_PREV}[action])


def _media(n):
    match = VOLUME_UP_RE.match(n)
    if match:
        percent = int(match.group(1) or 10)
        _volume(percent)
        return _reply(f"Громче на {percent}%.")
    match = VOLUME_DOWN_RE.match(n)
    if match:
        percent = int(match.group(1) or 10)
        _volume(-percent)
        return _reply(f"Тише на {percent}%.")
    if VOLUME_MAX_RE.match(n):
        _volume_max()
        return _reply("Звук на максимум. Держись!")
    if MUTE_RE.match(n):
        _mute()
        return _reply("Переключила звук.")
    if PLAY_RE.match(n):
        _player("playpause")
        return _reply("Пауза / продолжаю.")
    if NEXT_RE.match(n):
        _player("next track")
        return _reply("Следующий трек.")
    if PREV_RE.match(n):
        _player("previous track")
        return _reply("Предыдущий трек.")
    return None


# ---------- закрыть программу ----------
CLOSE_RE = re.compile(r"^(?:закрой|закрыть|заверши|заверши\s+работу|выруби|убей)\s+"
                      r"(?:мне\s+)?(?:программу\s+|приложение\s+|игру\s+)?(.+)$")
PROTECTED = {"explorer", "svchost", "csrss", "winlogon", "dwm", "system", "lsass", "services",
             "smss", "wininit", "taskmgr", "conhost", "searchhost", "startmenuexperiencehost",
             "shellexperiencehost", "textinputhost", "applicationframehost", "systemsettings",
             "finder", "dock", "windowserver", "loginwindow", "systemuiserver", "launchd",
             "kernel_task", "controlcenter", "notificationcenter"}


def _compact(text):
    return re.sub(r"[^0-9a-zа-я]", "", apps.norm(text))


def _mac_processes():
    """{pid: (имя программы, [])} на Mac. Для программ .app берём название из пути."""
    result = {}
    try:
        out = subprocess.run(["ps", "-axo", "pid=,comm="], capture_output=True, text=True,
                             timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return result
    for line in out.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2 or not parts[0].isdigit():
            continue
        path = parts[1]
        app = re.search(r"/([^/]+)\.app/", path)
        result[int(parts[0])] = (app.group(1) if app else os.path.basename(path), [])
    return result


def _processes():
    """{pid: (имя exe без .exe, [заголовки окон])} — все процессы и их видимые окна."""
    if IS_MAC:
        return _mac_processes()
    result = {}
    try:
        out = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True,
                             creationflags=NO_WINDOW, timeout=10).stdout
        text = out.decode("cp866", errors="replace")
        for line in text.splitlines():
            parts = [p.strip('"') for p in line.split('","')]
            if len(parts) >= 2 and parts[1].isdigit():
                result[int(parts[1])] = (os.path.splitext(parts[0])[0], [])
    except (OSError, subprocess.SubprocessError):
        return result

    if os.name == "nt":
        user32 = ctypes.windll.user32
        proto = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def callback(hwnd, _):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length:
                    buffer = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buffer, length + 1)
                    pid = ctypes.c_ulong()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    if pid.value in result:
                        result[pid.value][1].append(buffer.value)
            return True

        user32.EnumWindows(proto(callback), 0)
    return result


def _kill(pid, force):
    """Сначала просим программу закрыться, force=True — закрываем принудительно."""
    if IS_MAC or os.name != "nt":
        subprocess.run(["kill", "-KILL" if force else "-TERM", str(pid)], capture_output=True)
        return
    args = ["taskkill", "/PID", str(pid), "/T"] + (["/F"] if force else [])
    subprocess.run(args, capture_output=True, creationflags=NO_WINDOW)


def _wanted_names(target):
    """Как ещё может называться программа: «стим» -> steam, «майнкрафт» -> Lexplosion."""
    q = apps.norm(target)
    names = {q, apps.resolve_word(q)}
    names.update(apps.ALIASES.get(apps.resolve_word(q), []))
    found = apps.find(q)
    if found is not None:
        if apps.last_found_name:
            names.add(apps.last_found_name)
        kind, path = found
        if kind in ("file", "exe"):
            names.add(Path(path).stem)
    return {_compact(name) for name in names if len(_compact(name)) >= 3}


def _close(n):
    match = CLOSE_RE.match(n)
    if not match:
        return None
    target = match.group(1).strip()
    if any(apps.norm(target).startswith(p) for p in WAKE_PREFIXES):
        return _reply("Себя закрыть не могу — я же тогда не услышу, как ты меня позовёшь!")

    wanted = _wanted_names(target)
    own = os.getpid()
    hits = {}
    for pid, (exe, titles) in _processes().items():
        if pid == own or exe.lower() in PROTECTED:
            continue
        exe_c = _compact(exe)
        for name in wanted:
            title = next((t for t in titles if name in _compact(t)), "")
            if title or exe_c == name or (len(name) >= 4 and name in exe_c):
                hits[pid] = title or exe
                break
    if not hits:
        return _reply(f"Не вижу запущенной программы «{target}».")

    for pid in hits:
        _kill(pid, force=False)

    def finish_off():
        time.sleep(3)
        alive = _processes()
        for pid in hits:
            if pid in alive:
                _kill(pid, force=True)

    threading.Thread(target=finish_off, daemon=True).start()
    shown = sorted(set(hits.values()), key=len)[0]
    return _reply(f"Закрываю «{shown}».")


# ---------- YouTube ----------
YT_WORDS = r"(?:ютубе|ютюбе|ютуб|ютьюбе|youtube)"
YT_RES = [
    re.compile(rf"^(?:включи|найди|поставь|открой|покажи|поищи)\s+(?:мне\s+)?(?:на|в)\s+{YT_WORDS}\s+(.+)$"),
    re.compile(rf"^(?:включи|найди|поставь|открой|покажи|поищи)\s+(?:мне\s+)?(.+?)\s+(?:на|в)\s+{YT_WORDS}$"),
    re.compile(rf"^{YT_WORDS}\s+(.+)$"),
]


def _youtube(n):
    for pattern in YT_RES:
        match = pattern.match(n)
        if match:
            query = match.group(1).strip()
            webbrowser.open("https://www.youtube.com/results?search_query=" + quote_plus(query))
            return _reply(f"Ищу на YouTube: {query}")
    return None


# ---------- таймеры и напоминания ----------
_timers = []
_timers_lock = threading.Lock()

DURATION_RE = re.compile(
    r"^\s*(?:(\d+)\s*)?(полчаса|полминуты|секунд\w*|сек|минут\w*|мин|час\w*)\b")
AT_RE = re.compile(r"^\s*в\s+(\d{1,2})(?:[:.\s](\d{2}))?(?:\s*час\w*)?\b")
TIMER_RE = re.compile(r"^(?:поставь\s+|заведи\s+|включи\s+)?таймер\s+(?:на\s+)?(.+)$")
REMIND_RE = re.compile(r"^напомни(?:\s+мне)?\s+(.+)$")
CANCEL_TIMERS_RE = re.compile(r"^(?:отмени|убери|удали|сбрось)\s+(?:все\s+)?"
                              r"(?:таймер\w*|напоминани\w*)$")
LIST_TIMERS_RE = re.compile(r"^(?:какие|покажи|мои)\s+(?:таймер\w*|напоминани\w*)$")


def parse_duration(text):
    """«20 минут выключить чайник» -> (1200, "выключить чайник"). Нет времени — (0, текст)."""
    total = 0
    rest = text
    while True:
        match = DURATION_RE.match(rest)
        if not match:
            break
        number = int(match.group(1)) if match.group(1) else 1
        unit = match.group(2)
        if unit == "полчаса":
            total += 1800
        elif unit == "полминуты":
            total += 30
        elif unit.startswith("сек"):
            total += number
        elif unit.startswith("мин"):
            total += number * 60
        else:
            total += number * 3600
        rest = rest[match.end():].lstrip()
        rest = re.sub(r"^и\s+", "", rest)
    return total, rest


def _format_seconds(seconds):
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    parts = []
    if hours:
        parts.append(f"{hours} ч")
    if minutes:
        parts.append(f"{minutes} мин")
    if secs and not hours:
        parts.append(f"{secs} сек")
    return " ".join(parts) or "0 сек"


def _fire(text):
    with _timers_lock:
        _timers[:] = [t for t in _timers if t["timer"].is_alive() and t["text"] != text]
    if on_reminder is not None:
        on_reminder(text)


def add_timer(seconds, text):
    timer = threading.Timer(seconds, _fire, args=(text,))
    timer.daemon = True
    timer.start()
    with _timers_lock:
        _timers.append({"timer": timer, "text": text, "at": time.time() + seconds})


def _reminders(n):
    if CANCEL_TIMERS_RE.match(n):
        with _timers_lock:
            count = len(_timers)
            for item in _timers:
                item["timer"].cancel()
            _timers.clear()
        return _reply(f"Отменила: {count}." if count else "Таймеров и напоминаний нет.")

    if LIST_TIMERS_RE.match(n):
        with _timers_lock:
            items = [t for t in _timers if t["timer"].is_alive()]
        if not items:
            return _reply("Таймеров и напоминаний нет.")
        lines = [f"• через {_format_seconds(t['at'] - time.time())}: {t['text']}" for t in items]
        return _reply("Запланировано:\n" + "\n".join(lines))

    match = TIMER_RE.match(n)
    if match:
        seconds, _ = parse_duration(match.group(1))
        if not seconds:
            return _reply("На сколько поставить таймер? Например: таймер на 5 минут.")
        add_timer(seconds, f"Таймер на {_format_seconds(seconds)} — время вышло!")
        return _reply(f"Таймер на {_format_seconds(seconds)} пошёл.")

    match = REMIND_RE.match(n)
    if not match:
        return None
    body = match.group(1)
    seconds, what = 0, body
    if body.startswith("через"):
        seconds, what = parse_duration(body[len("через"):])
    else:
        at = AT_RE.match(body)
        if at:
            hour, minute = int(at.group(1)), int(at.group(2) or 0)
            if hour < 24 and minute < 60:
                now = datetime.now()
                moment = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if moment <= now:
                    moment += timedelta(days=1)
                seconds = (moment - now).total_seconds()
                what = body[at.end():].strip()
    what = re.sub(r"^что(?:бы)?\s+", "", what).strip() or "ты просил напомнить"
    if not seconds:
        return _reply("Когда напомнить? Например: напомни через 20 минут выключить чайник.")
    add_timer(seconds, f"Напоминаю: {what}")
    return _reply(f"Хорошо, через {_format_seconds(seconds)} напомню: {what}.")


# ---------- скриншот ----------
SCREENSHOT_RE = re.compile(r"^(?:сделай|сними|скинь|пришли|отправь)?\s*(?:мне\s+)?"
                           r"(?:скриншот|скрин|снимок\s+экрана)(?:\s+экрана)?$")
SCREENSHOT_PS = r"""
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
Add-Type -Namespace Dpi -Name Native -MemberDefinition '[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();'
[void][Dpi.Native]::SetProcessDPIAware()
$b = [System.Windows.Forms.SystemInformation]::VirtualScreen
$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($b.Left, $b.Top, 0, 0, $bmp.Size)
$bmp.Save($env:PIPKA_SHOT, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
"""


def screenshots_dir():
    pictures = Path.home() / "Pictures"
    if not pictures.is_dir():
        pictures = Path.home() / "OneDrive" / "Pictures"
    folder = pictures / "ПИПКА скриншоты"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def take_screenshot():
    """Снимок всего экрана в PNG. Возвращает путь или выбрасывает OSError."""
    path = screenshots_dir() / datetime.now().strftime("Скриншот %Y-%m-%d %H-%M-%S.png")
    if IS_MAC:
        result = subprocess.run(["screencapture", "-x", str(path)], capture_output=True, timeout=30)
        if result.returncode != 0 or not path.exists():
            raise OSError("Mac не дал сделать снимок. Разреши ПИПКЕ запись экрана: "
                          "Системные настройки → Конфиденциальность → Запись экрана.")
        return str(path)
    env = dict(os.environ, PIPKA_SHOT=str(path))
    result = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                             "-Command", SCREENSHOT_PS], env=env, capture_output=True,
                            creationflags=NO_WINDOW, timeout=30)
    if result.returncode != 0 or not path.exists():
        message = result.stderr.decode("utf-8", errors="replace").strip()[:150]
        raise OSError(message or "PowerShell не смог сделать снимок")
    return str(path)


def _screenshot(n):
    if not SCREENSHOT_RE.match(n):
        return None
    try:
        path = take_screenshot()
    except (OSError, subprocess.SubprocessError) as exc:
        return _reply(f"Не получилось сделать скриншот: {exc}")
    return _reply(f"Скриншот готов: Картинки\\ПИПКА скриншоты\\{Path(path).name}", photo=path)


# ---------- казино: фишки, рулетка, монетка ----------
CHIPS_FILE = PROJECT_DIR / "casino.json"
START_CHIPS = 1000
REFILL = 500
_chips_lock = threading.Lock()
_chips = None

RED_NUMBERS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
BALANCE_RE = re.compile(r"^(?:сколько\s+(?:у\s+меня\s+)?фиш\w*|мой\s+баланс|баланс|мои\s+фишки)$")
ROULETTE_RE = re.compile(r"рулетк")
COIN_RE = re.compile(r"монетк|орел\s+или\s+решка|орёл\s+или\s+решка|ставлю\s+на\s+(?:орла|решку)")


def chips():
    global _chips
    with _chips_lock:
        if _chips is None:
            try:
                _chips = int(json.loads(CHIPS_FILE.read_text(encoding="utf-8"))["chips"])
            except (OSError, ValueError, KeyError, TypeError):
                _chips = START_CHIPS
        return _chips


def change_chips(delta):
    global _chips
    current = chips()
    with _chips_lock:
        _chips = max(0, current + delta)
        try:
            CHIPS_FILE.write_text(json.dumps({"chips": _chips}), encoding="utf-8")
        except OSError:
            pass
        return _chips


def _bet(n, default):
    match = re.search(r"(\d+)\s*фиш", n) or re.search(r"ставк\w*\s+(\d+)", n) \
        or re.search(r"\bпо\s+(\d+)", n)
    return int(match.group(1)) if match else default


def ensure_chips():
    if chips() == 0:
        change_chips(REFILL)
        return f"Банк в хорошем настроении: держи {REFILL} фишек. "
    return ""


ROULETTE_BETS = {
    "red": "красное", "black": "чёрное", "even": "чётное", "odd": "нечётное",
    "low": "1–18", "high": "19–36", "number": "число",
}


def roulette_color(spin):
    return "зеро" if spin == 0 else ("красное" if spin in RED_NUMBERS else "чёрное")


def roulette_wins(spin, pick, number=None):
    """Сыграла ли ставка. Ставки на число/зеро платят 35 к 1, остальные 1 к 1."""
    if pick == "number":
        return spin == number
    if spin == 0:
        return False
    return {
        "red": spin in RED_NUMBERS,
        "black": spin not in RED_NUMBERS,
        "even": spin % 2 == 0,
        "odd": spin % 2 == 1,
        "low": spin <= 18,
        "high": spin >= 19,
    }[pick]


def roulette_settle(spin, pick, bet, number=None):
    """Считает ставку и меняет фишки. Возвращает (выиграл, выигрыш, баланс)."""
    win = roulette_wins(spin, pick, number)
    payout = bet * 35 if pick == "number" else bet
    balance = change_chips(payout if win else -bet)
    return win, payout, balance


def roulette_label(pick, number=None):
    if pick == "number":
        return "зеро" if number == 0 else f"число {number}"
    return ROULETTE_BETS[pick]


def _roulette(n):
    if not ROULETTE_RE.search(n):
        return None
    bonus = ensure_chips()
    bet = min(_bet(n, 100), chips())
    pick, number = "red", None
    if re.search(r"черн|чёрн", n):
        pick = "black"
    elif re.search(r"нечетн|нечётн", n):
        pick = "odd"
    elif re.search(r"четн|чётн", n):
        pick = "even"
    elif re.search(r"зеро|\bноль\b", n):
        pick, number = "number", 0
    elif re.search(r"(?:1|один)\s*(?:-|–|до)\s*18|малы", n):
        pick = "low"
    elif re.search(r"19\s*(?:-|–|до)\s*36|больш", n):
        pick = "high"
    else:
        single = re.search(r"на\s+(\d{1,2})\b(?!\s*фиш)", n)
        if single and int(single.group(1)) <= 36:
            pick, number = "number", int(single.group(1))

    spin = random.randint(0, 36)
    win, payout, balance = roulette_settle(spin, pick, bet, number)
    result = f"выигрыш {payout} фишек!" if win else "ставка сгорела."
    return _reply(f"{bonus}Шарик остановился на {spin} ({roulette_color(spin)}). "
                  f"Ставка {bet} на {roulette_label(pick, number)} — {result} "
                  f"Теперь у тебя {balance} фишек.")


def _coin(n):
    if not COIN_RE.search(n):
        return None
    side = random.choice(["орёл", "решка"])
    guess = "орёл" if re.search(r"орл|орел|орёл", n) and "ставлю" in n else (
        "решка" if "ставлю" in n and "решк" in n else "")
    if not guess:
        return _reply(f"Подбрасываю… {side.capitalize()}!")
    bonus = ensure_chips()
    bet = min(_bet(n, 50), chips())
    balance = change_chips(bet if side == guess else -bet)
    verdict = f"угадал, +{bet}!" if side == guess else f"мимо, -{bet}."
    return _reply(f"{bonus}Подбрасываю… {side.capitalize()}! Ты {verdict} Фишек: {balance}.")


def _casino(n):
    if BALANCE_RE.match(n):
        return _reply(f"У тебя {chips()} фишек.")
    return _roulette(n) or _coin(n)


# ---------- погода ----------
WEATHER_RE = re.compile(
    r"^(?:(?:какая|какой)\s+)?(?:сейчас\s+)?(?:погода|прогноз(?:\s+погоды)?)"
    r"(?:\s+(?:сейчас|сегодня))?(?:\s+(?:в|во)\s+(.+?))?(?:\s+(?:сейчас|сегодня))?$"
    r"|^сколько\s+(?:сейчас\s+)?градусов(?:\s+(?:в|во)\s+(.+))?$"
    r"|^что\s+(?:там\s+)?с\s+погодой(?:\s+(?:в|во)\s+(.+))?$")


WEATHER_WORDS = {
    "clear": "ясно", "sunny": "солнечно", "partly cloudy": "переменная облачность",
    "cloudy": "облачно", "overcast": "пасмурно", "mist": "дымка", "fog": "туман",
    "freezing fog": "морозный туман", "haze": "мгла", "smoke": "дым", "smog": "смог",
    "patchy rain nearby": "местами дождь", "patchy rain possible": "возможен дождь",
    "light rain": "небольшой дождь", "light drizzle": "морось", "drizzle": "морось",
    "moderate rain": "дождь", "heavy rain": "сильный дождь", "light rain shower": "небольшой ливень",
    "rain shower": "ливень", "thunderstorm": "гроза", "light snow": "небольшой снег",
    "snow": "снег", "heavy snow": "сильный снегопад", "patchy snow nearby": "местами снег",
    "light sleet": "мокрый снег", "sleet": "мокрый снег", "blizzard": "метель",
}


def _weather(n):
    match = WEATHER_RE.match(n)
    if not match:
        return None
    city = next((g for g in match.groups() if g), "")
    try:
        response = requests.get(f"https://wttr.in/{quote_plus(city)}",
                                params={"format": "j1", "lang": "ru"}, timeout=(4, 8))
        data = response.json()
        now = data["current_condition"][0]
        desc = (now.get("lang_ru") or now.get("weatherDesc") or [{"value": ""}])[0]["value"]
        temp = int(now["temp_C"])
        feels = int(now["FeelsLikeC"])
        wind = round(int(now["windspeedKmph"]) / 3.6)
        place = f"В {city.title()}" if city else "У тебя"
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError):
        return _reply("Не получилось узнать погоду: проверь интернет.")
    desc = WEATHER_WORDS.get(desc.strip().lower(), desc.strip().lower())
    sign = lambda v: f"+{v}" if v > 0 else str(v)
    return _reply(f"{place} сейчас {desc}, {sign(temp)}°, ощущается как {sign(feels)}°, "
                  f"ветер {wind} м/с.")


# ---------- общий вход ----------
def handle(n):
    n = files.words_to_digits(n)
    for handler in (_media, _youtube, _reminders, _screenshot, _casino, _weather, _close):
        result = handler(n)
        if result is not None:
            return result
    return None
