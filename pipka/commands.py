"""Разбор команд из чата. Команды выполняются обычным Python-кодом,
а не нейросетью: ИИ ничего не запускает сам."""

import difflib
import os
import re
import subprocess
import threading
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

from pipka import ai, apps, extras, files
from pipka.system import IS_MAC, IS_WINDOWS, osascript, reveal as reveal_in_folder

HELP_TEXT = (
    "Что я умею:\n"
    "• открой <программа / игра / сайт> — стим, майнкрафт, ютуб, emaktab\n"
    "• открой папку папа, открой файл горгаз 2025, открой любой реферат на рабочем столе\n"
    "• найди файл <название> — покажу его в папке\n"
    "• закрой <программа> — закрой стим, закрой майнкрафт\n"
    "• громче / тише / выключи звук / пауза / следующий трек\n"
    "• включи на ютубе <запрос>, загугли <запрос>\n"
    "• таймер на 5 минут, напомни через 20 минут выключить чайник, отмени таймеры\n"
    "• сделай скриншот — пришлю и в Telegram\n"
    "• брось кубик, что выпало, рулетка на красное 100 фишек, подбрось монетку, баланс\n"
    "• какая погода, погода в Ташкенте\n"
    "• который час, какое сегодня число\n"
    "• запомни, что <как слышу> это <программа> — если путаю название\n"
    "• выключи компьютер (с подтверждением)\n"
    "Всё остальное я обсуждаю как ИИ."
)

SITES = {
    "youtube": "https://www.youtube.com",
    "ютуб": "https://www.youtube.com",
    "ютьюб": "https://www.youtube.com",
    "google": "https://www.google.com",
    "гугл": "https://www.google.com",
    "браузер": "https://www.google.com",
    "emaktab": "https://emaktab.uz",
    "эмактаб": "https://emaktab.uz",
    "емактаб": "https://emaktab.uz",
    "мактаб": "https://emaktab.uz",
    "дневник": "https://emaktab.uz",
    "электронный дневник": "https://emaktab.uz",
    # Так микрофон слышит «eMaktab» (взято из журнала pipka_log.txt)
    "октав": "https://emaktab.uz",
    "мы октав": "https://emaktab.uz",
    "ем октав": "https://emaktab.uz",
    "им октав": "https://emaktab.uz",
    "и октав": "https://emaktab.uz",
    "эм октав": "https://emaktab.uz",
    "е октав": "https://emaktab.uz",
    "ей октав": "https://emaktab.uz",
    "мактап": "https://emaktab.uz",
    "мак тап": "https://emaktab.uz",
    "мак таб": "https://emaktab.uz",
}

# Как называть сайт в ответе
SITE_TITLES = {
    "https://www.youtube.com": "YouTube",
    "https://www.google.com": "Google",
    "https://emaktab.uz": "eMaktab",
}

# Папки пользователя: название -> имя папки внутри домашней папки
FOLDERS = {
    "загрузки": "Downloads",
    "загрузка": "Downloads",
    "документы": "Documents",
    "рабочий стол": "Desktop",
    "музыка": "Music",
    "изображения": "Pictures",
    "картинки": "Pictures",
    "фото": "Pictures",
    "видео": "Videos",
    "проводник": "",
    "домашняя папка": "",
}

MONTHS = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]
WEEKDAYS = [
    "понедельник", "вторник", "среда", "четверг",
    "пятница", "суббота", "воскресенье",
]

WAKE_RE = re.compile(r"^\s*(?:пипк|пепк)[ауиеоы]?\b[\s,:;!\-—]*", re.IGNORECASE)
# Слова в начале фразы, которые ничего не значат: «ну давай открой…», «можешь открыть…»
LEAD_RE = re.compile(
    r"^(?:(?:ну|а|давай|пожалуйста|можешь|можешь ли|ты можешь|быстро|слушай)\s+)+",
    re.IGNORECASE,
)
OPEN_RE = re.compile(
    r"^(?:открой|открою|открыть|откройте|открывай|запусти|запустить|запускай|"
    r"включи|включить|зайди\s+в|зайди\s+на|перейди\s+в|перейди\s+на)\s+"
    r"(?:мне\s+)?(?:(программу|приложение|сайт|папку|игру|файл|документ)\s+)?(.+)$",
    re.IGNORECASE,
)
FIND_FILE_RE = re.compile(
    r"^(?:найди|найти|покажи|поищи|где)\s+(?:мне\s+)?(?:(папку|файл|документ)\s+)(.+)$",
    re.IGNORECASE,
)
SEARCH_RE = re.compile(
    r"^(?:(?:найди|поищи)\s+в\s+(?:гугле|google|интернете|инете)|загугли)\s+(.+)$",
    re.IGNORECASE,
)
REMEMBER_RE = re.compile(
    r"^(?:запомни|добавь)\s+программу\s+(.+?)\s*=\s*(.+)$",
    re.IGNORECASE,
)
SHUTDOWN_RE = re.compile(r"^(?:выключи|выключить|отключи)\s+(?:мой\s+)?(?:компьютер|пк|комп)$")
RESTART_RE = re.compile(r"^(?:перезагрузи|перезагрузить|перезапусти)\s+(?:мой\s+)?(?:компьютер|пк|комп)$")
CANCEL_RE = re.compile(r"^(?:отмени|отменить|отмена)\s+(?:выключени[ея]|перезагрузк[уи])$")
TIME_RE = re.compile(r"^(?:который час|сколько времени|скажи время|время)$")
DATE_RE = re.compile(
    r"^(?:какое сегодня число|какая сегодня дата|какое число|какой сегодня день|дата)$"
)
FACT_RE = re.compile(r"^запомни(?:\s*[,:])?\s+(?:что\s+)?(.+)$", re.IGNORECASE)
LIST_FACTS_RE = re.compile(
    r"^(?:что ты помнишь|что ты знаешь обо мне|покажи память|мои факты|что ты запомнила)$"
)
FORGET_RE = re.compile(r"^забудь\s+(?:все|всё)$")
CLEAR_HISTORY_RE = re.compile(r"^(?:очисти|удали|сотри)\s+историю(?:\s+чата)?$")
# Слова-паразиты, которые мешают понять название: «открой, к примеру, Айзек»
FILLER_RE = re.compile(
    r"\b(?:к примеру|например|типа|короче|пожалуйста|пожалуй|давай|можешь|можете|"
    r"будь добра|ну|вот|мне|там|это|под названием|с названием|который называется|"
    r"которая называется|называется|по имени)\b"
)
OPEN_ONLY_RE = re.compile(
    r"^(?:открой|открыть|запусти|запустить|включи|зайди|перейди)(?:\s+(?:мне|пожалуйста|это))*$"
)
SEARCH_ONLY_RE = re.compile(r"^(?:загугли|найди в гугле|найди в интернете)$")
POWER_ONLY_RE = re.compile(r"^(?:выключи|выключить|перезагрузи|перезагрузить)$")
TEACH_RE = re.compile(r"^запомни(?:\s*[,:])?\s+что\s+(.+?)\s+(?:это|значит|=)\s+(.+)$", re.IGNORECASE)
HELP_RE = re.compile(r"^(?:помощь|команды|что ты умеешь|что умеешь|список команд)$")


def clean_target(text):
    """Оставляет только название: без «к примеру», «пожалуйста», «мне» и одиночных букв."""
    text = FILLER_RE.sub(" ", apps.norm(text))
    return " ".join(word for word in text.split() if len(word) > 1)


@dataclass
class Result:
    handled: bool = False
    message: str = ""
    confirm: str = ""        # "shutdown" или "restart", если нужно подтверждение
    confirm_text: str = ""   # вопрос для окна подтверждения
    follow_up: str = ""      # команда ждёт продолжения: следующая фраза допишется к этому слову
    photo: str = ""          # путь к картинке (скриншот), которую можно отправить в Telegram


def _clean(text):
    cleaned = WAKE_RE.sub("", text.strip(), count=1)
    # Запятые и восклицания — это не часть команды (двоеточие оставляем: в путях C:\ оно нужно)
    cleaned = re.sub(r"[,;!?]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = LEAD_RE.sub("", cleaned)
    return cleaned.strip().rstrip(".… ").strip()


def _known_names():
    """Все названия, которые ПИПКА точно знает: для поиска похожего слова."""
    names = set(SITES) | set(FOLDERS) | set(apps.SYSTEM_APPS) | set(apps.ALIASES)
    names |= set(apps.WORD_FIXES) | set(apps.load_user_apps()) | set(apps.load_aliases())
    return names


def _closest_name(q):
    """Микрофон часто слышит слово чуть иначе: «телеграмму», «ютубе», «блакнот».
    Ищем самое похожее известное название. Если похожего нет — None."""
    if len(q) < 3:
        return None
    match = difflib.get_close_matches(q, _known_names(), n=1, cutoff=0.75)
    return match[0] if match else None


def _folder_path(name):
    sub = FOLDERS[name]
    home = Path.home()
    options = [home / sub, home / "OneDrive" / sub] if sub else [home]
    for path in options:
        if path.is_dir():
            return path
    return None


def _file_kind(word):
    word = (word or "").lower()
    if word == "папку":
        return "папку"
    if word in ("файл", "документ"):
        return "файл"
    return ""


def _open_file(target, kind, reveal=False):
    """Ищет файл или папку по названию и открывает. Возвращает сообщение или None."""
    if not files.ready():
        files.build_in_background()
        return "Я ещё собираю список файлов на компьютере. Попробуй через минутку."
    found = files.search(target, kind)
    if found is None:
        return None
    path, is_dir = found
    name = Path(path).name
    try:
        if reveal and not is_dir:
            reveal_in_folder(path)
            return f"Нашла файл «{name}», показываю в папке."
        apps.launch("folder" if is_dir else "file", path)
    except OSError as exc:
        return f"Нашла «{name}», но открыть не получилось: {exc}"
    if not is_dir and Path(path).suffix.lower() in (".lnk", ".url"):
        return f"Запускаю «{Path(path).stem}»."
    return f"Открываю {'папку' if is_dir else 'файл'} «{name}»."


def _open_target(target, kind=""):
    q = apps.norm(target)

    if kind:
        message = _open_file(target, kind)
        if message:
            return message
        what = "папку" if kind == "папку" else "файл"
        return f"Не нашла {what} «{target}» на рабочем столе, в документах, загрузках и на дисках."

    # Слово неточное и такой программы нет — пробуем самое похожее известное название
    if q not in SITES and q not in FOLDERS and apps.find(q) is None:
        # Сначала похожее слово, потом сайт «по звучанию» («имак тоб» -> emaktab)
        q = _closest_name(q) or apps.sound_match(q, SITES, cutoff=0.75) or q

    if q in SITES:
        try:
            ok = webbrowser.open(SITES[q])
        except webbrowser.Error as exc:
            return f"Не получилось открыть сайт: {exc}"
        if ok:
            return f"Открываю {SITE_TITLES.get(SITES[q], q)}."
        return "Не получилось открыть браузер. Открой сайт вручную."

    if q in FOLDERS:
        path = _folder_path(q)
        if path is None:
            return f"Не нашла папку «{q}» на этом компьютере."
        try:
            apps.launch("folder", str(path))
        except OSError as exc:
            return f"Не удалось открыть папку «{q}»: {exc}"
        return f"Открываю папку «{q}»."

    found = apps.find(q)
    shown = apps.last_found_name or target

    if found is None:
        # Может, это файл или папка с таким названием
        message = _open_file(target, "")
        if message and not message.startswith("Я ещё собираю"):
            return message

    if found is None:
        # Последняя попытка: Gemini угадывает, что имелось в виду (английские названия)
        items = apps.catalog()
        name = ai.pick_program(target, list(items))
        if name is not None:
            found, shown = items[name], name

    if found is None:
        return (
            f"Не нашла «{target}» ни среди программ, ни среди файлов. "
            f"Если это программа, скажи: запомни, что {target} это название программы."
        )

    kind, path = found

    if kind == "missing":
        return (
            f"Программа «{target}» записана в apps.json, но файла нет по пути: {path}. "
            "Укажи новый путь командой «запомни программу ...»."
        )

    # У ярлыков бывают названия вроде «Запустить The Binding of Isaac»
    shown = re.sub(r"^(?:запустить|играть)\s+", "", shown, flags=re.IGNORECASE)

    try:
        apps.launch(kind, path)
    except OSError as exc:
        return f"Я попыталась открыть «{shown}», но не получилось: {exc}"

    return f"Запускаю «{shown}»."


def _run_shutdown_tool(args):
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.run(
        args,
        check=True,
        shell=False,
        capture_output=True,
        creationflags=flags,
    )


# На Mac нет «shutdown через 30 секунд», поэтому ждём сами и даём время отменить
_mac_power_timer = None


def _mac_power(action):
    command = "shut down" if action == "shutdown" else "restart"
    osascript(f'tell application "System Events" to {command}')


def execute_confirmed(action):
    """Выполняет подтверждённое действие. Возвращает (успех, сообщение)."""
    global _mac_power_timer
    if IS_MAC:
        if action not in ("shutdown", "restart"):
            return False, "Неизвестное действие."
        if _mac_power_timer is not None:
            _mac_power_timer.cancel()
        _mac_power_timer = threading.Timer(30, _mac_power, args=(action,))
        _mac_power_timer.daemon = True
        _mac_power_timer.start()
        what = "Выключение" if action == "shutdown" else "Перезагрузка"
        return True, f"{what} через 30 секунд. Чтобы отменить, напиши: отмени выключение."
    if not IS_WINDOWS:
        return False, "Выключение и перезагрузка работают только в Windows и на Mac."

    if action == "shutdown":
        args = ["shutdown", "/s", "/t", "30"]
        text = "Выключение через 30 секунд. Чтобы отменить, напиши: отмени выключение."
    elif action == "restart":
        args = ["shutdown", "/r", "/t", "30"]
        text = "Перезагрузка через 30 секунд. Чтобы отменить, напиши: отмени выключение."
    else:
        return False, "Неизвестное действие."

    try:
        _run_shutdown_tool(args)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"Не получилось выполнить команду: {exc}"

    return True, text


def _cancel_shutdown():
    global _mac_power_timer
    if IS_MAC:
        if _mac_power_timer is None or not _mac_power_timer.is_alive():
            return "Сейчас нет запланированного выключения, отменять нечего."
        _mac_power_timer.cancel()
        _mac_power_timer = None
        return "Готово, выключение отменено."
    if not IS_WINDOWS:
        return "Отмена работает только в Windows и на Mac."
    try:
        _run_shutdown_tool(["shutdown", "/a"])
    except (OSError, subprocess.SubprocessError):
        return "Сейчас нет запланированного выключения, отменять нечего."
    return "Готово, выключение отменено."


REMOTE_BLOCKED = Result(True, "Эта команда с телефона отключена: сделай это на компьютере.")


def handle(text, db=None, remote=False):
    """Пытается понять сообщение как команду.
    db — база памяти (нужна для «запомни…»); remote=True — команда пришла с телефона,
    опасные команды при этом отключены.
    Если это не команда, возвращает Result(handled=False) — тогда отвечает ИИ."""
    original = (text or "").strip()
    if not original:
        return Result()

    cleaned = _clean(original)

    if not cleaned:
        return Result(True, "Я здесь! Что нужно сделать?")

    n = apps.norm(cleaned)

    if HELP_RE.match(n):
        return Result(True, HELP_TEXT)

    extra = extras.handle(n)
    if extra is not None:
        return Result(True, extra["message"], photo=extra["photo"])

    if SHUTDOWN_RE.match(n):
        if remote:
            return REMOTE_BLOCKED
        return Result(
            True,
            "Хочешь выключить компьютер? Жду подтверждения.",
            confirm="shutdown",
            confirm_text="Выключить компьютер? Он выключится через 30 секунд.\n"
                         "Сохрани открытые файлы.",
        )

    if RESTART_RE.match(n):
        if remote:
            return REMOTE_BLOCKED
        return Result(
            True,
            "Хочешь перезагрузить компьютер? Жду подтверждения.",
            confirm="restart",
            confirm_text="Перезагрузить компьютер? Он перезагрузится через 30 секунд.\n"
                         "Сохрани открытые файлы.",
        )

    if CANCEL_RE.match(n):
        return Result(True, _cancel_shutdown())

    if TIME_RE.match(n):
        return Result(True, "Сейчас " + datetime.now().strftime("%H:%M") + ".")

    if DATE_RE.match(n):
        now = datetime.now()
        return Result(
            True,
            f"Сегодня {now.day} {MONTHS[now.month - 1]} {now.year} года, "
            f"{WEEKDAYS[now.weekday()]}.",
        )

    remember = REMEMBER_RE.match(cleaned)
    if remember:
        if remote:
            return REMOTE_BLOCKED
        ok, message = apps.add_user_app(remember.group(1), remember.group(2))
        return Result(True, message)

    if LIST_FACTS_RE.match(n):
        if remote or db is None:
            return REMOTE_BLOCKED
        facts = db.facts()
        if not facts:
            return Result(True, "Пока я ничего о тебе не запомнила. Скажи: запомни, что ...")
        return Result(True, "Вот что я помню:\n" + "\n".join("• " + f for f in facts))

    if FORGET_RE.match(n):
        if remote or db is None:
            return REMOTE_BLOCKED
        return Result(
            True,
            "Забыть всё, что я о тебе запомнила? Жду подтверждения.",
            confirm="forget_facts",
            confirm_text="Забыть всё, что ПИПКА запомнила о тебе?",
        )

    if CLEAR_HISTORY_RE.match(n):
        if remote or db is None:
            return REMOTE_BLOCKED
        return Result(
            True,
            "Очистить историю чата? Жду подтверждения.",
            confirm="clear_history",
            confirm_text="Удалить всю историю чата? Запомненные факты останутся.",
        )

    teach = TEACH_RE.match(cleaned)
    if teach:
        if remote:
            return REMOTE_BLOCKED
        ok, message = apps.add_alias(teach.group(1), teach.group(2))
        return Result(True, message)

    fact = FACT_RE.match(cleaned)
    if fact:
        if remote or db is None:
            return REMOTE_BLOCKED
        fact_text = fact.group(1).strip()
        if apps.norm(fact_text).startswith("программу"):
            return Result(
                True,
                "Чтобы запомнить программу, напиши: запомни программу название = C:\\путь\\к\\программе.exe",
            )
        db.add_fact(fact_text)
        return Result(True, f"Запомнила: {fact_text}")

    search = SEARCH_RE.match(cleaned)
    if search:
        query = search.group(1).strip()
        url = "https://www.google.com/search?q=" + quote_plus(query)
        try:
            ok = webbrowser.open(url)
        except webbrowser.Error as exc:
            return Result(True, f"Не получилось открыть браузер: {exc}")
        if ok:
            return Result(True, f"Ищу в Google: {query}")
        return Result(True, "Не получилось открыть браузер.")

    find_file = FIND_FILE_RE.match(cleaned)
    if find_file:
        target = clean_target(find_file.group(2))
        kind = _file_kind(find_file.group(1))
        message = _open_file(target, kind, reveal=True)
        what = "папку" if kind == "папку" else "файл"
        return Result(True, message or f"Не нашла {what} «{target}».")

    open_cmd = OPEN_RE.match(cleaned)
    if open_cmd:
        kind = _file_kind(open_cmd.group(1))
        target = clean_target(open_cmd.group(2))
        if not target:
            return Result(True, "Что открыть?", follow_up="открой")
        return Result(True, _open_target(target, kind))

    # Неполные команды не отдаём ИИ: он начинает придумывать
    if OPEN_ONLY_RE.match(n):
        return Result(True, "Что открыть?", follow_up="открой")
    if SEARCH_ONLY_RE.match(n):
        return Result(True, "Что загуглить?", follow_up="загугли")
    if POWER_ONLY_RE.match(n):
        return Result(True, "Скажи полностью: «выключи компьютер» или «перезагрузи компьютер».")

    return Result()
