"""Поиск и запуск программ в Windows."""

import difflib
import json
import os
import re
import subprocess
from pathlib import Path

from pipka.config import PROJECT_DIR

USER_APPS_FILE = PROJECT_DIR / "apps.json"
ALIASES_FILE = PROJECT_DIR / "aliases.json"

# Как распознавание русской речи записывает английские названия -> что на самом деле имеется в виду.
# Своё можно добавить командой: «запомни, что <как слышу> это <программа>».
WORD_FIXES = {
    "set them": "steam",
    "сет зэм": "steam",
    "сет дем": "steam",
    "айзек": "isaac",
    "исаак": "isaac",
    "забить гол айзек": "isaac",
    "забить айзек": "isaac",
    "чтим": "steam",
    "штим": "steam",
    "стив": "steam",
    "лекс плуг сью": "lexplosion",
    "лекс плохой сон": "lexplosion",
    "лишь по и сон": "lexplosion",
    "лекс плоужн": "lexplosion",
    "лексплоужн": "lexplosion",
    "лекс плошен": "lexplosion",
    "лекс плоу жн": "lexplosion",
    "лекс плоушн": "lexplosion",
}

# Русские названия -> что искать в меню «Пуск»
ALIASES = {
    "телеграм": ["telegram"],
    "телега": ["telegram"],
    "хром": ["chrome"],
    "гугл хром": ["chrome"],
    "опера": ["opera"],
    "фаерфокс": ["firefox"],
    "файрфокс": ["firefox"],
    "яндекс": ["yandex", "яндекс"],
    "яндекс браузер": ["yandex", "яндекс"],
    "эдж": ["edge"],
    "ворд": ["word"],
    "эксель": ["excel"],
    "пауэрпоинт": ["powerpoint"],
    "повер поинт": ["powerpoint"],
    "дискорд": ["discord"],
    "стим": ["steam"],
    "зум": ["zoom"],
    "скайп": ["skype"],
    "ватсап": ["whatsapp"],
    "вацап": ["whatsapp"],
    "пайчарм": ["pycharm"],
    "пицарм": ["pycharm"],
    "вс код": ["visual studio code"],
    "вскод": ["visual studio code"],
    "визуал студио код": ["visual studio code"],
    "код": ["visual studio code"],
    "блендер": ["blender"],
    "обс": ["obs studio"],
    "торрент": ["torrent"],
}

# Системные программы Windows: (тип запуска, что запускать)
SYSTEM_APPS = {
    "калькулятор": ("exe", "calc.exe"),
    "блокнот": ("exe", "notepad.exe"),
    "paint": ("exe", "mspaint.exe"),
    "пейнт": ("exe", "mspaint.exe"),
    "диспетчер задач": ("exe", "taskmgr.exe"),
    "панель управления": ("exe", "control.exe"),
    "настройки": ("uri", "ms-settings:"),
    "параметры": ("uri", "ms-settings:"),
}

# Слова, из-за которых ярлык в меню «Пуск» пропускаем
SKIP_WORDS = ("uninstall", "удалить", "удаление", "деинсталл", "readme", "справка", "help")

# Обычные места установки, если программы нет в меню «Пуск»
KNOWN_PATHS = {
    "telegram": [
        ("APPDATA", "Telegram Desktop", "Telegram.exe"),
        ("LOCALAPPDATA", "Telegram Desktop", "Telegram.exe"),
        ("PROGRAMFILES", "Telegram Desktop", "Telegram.exe"),
    ],
}

_shortcuts_cache = None


def norm(text):
    return " ".join(str(text).lower().replace("ё", "е").split())


def _start_menu_dirs():
    dirs = []
    for env_name in ("ProgramData", "APPDATA"):
        base = os.environ.get(env_name)
        if base:
            folder = Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
            if folder.is_dir():
                dirs.append(folder)
    return dirs


def _desktop_dirs():
    folders = (Path.home() / "Desktop", Path.home() / "OneDrive" / "Desktop",
               Path(os.environ.get("PUBLIC", "C:/Users/Public")) / "Desktop")
    return [folder for folder in folders if folder.is_dir()]


def _shortcuts():
    """Список ярлыков из меню «Пуск»: {название: путь}. Читается один раз."""
    global _shortcuts_cache
    if _shortcuts_cache is None:
        items = {}
        sources = [(folder, "**/*.lnk") for folder in _start_menu_dirs()]
        # На рабочем столе — только ярлыки сверху и в папках первого уровня (например «Игры»)
        sources += [(folder, pattern) for folder in _desktop_dirs() for pattern in ("*.lnk", "*/*.lnk")]
        for folder, pattern in sources:
            try:
                for path in folder.glob(pattern):
                    name = norm(path.stem)
                    if any(word in name for word in SKIP_WORDS):
                        continue
                    items.setdefault(name, path)
            except OSError:
                continue
        _shortcuts_cache = items
    return _shortcuts_cache


def refresh_shortcuts():
    global _shortcuts_cache
    _shortcuts_cache = None


def _match_shortcut(query):
    shortcuts = _shortcuts()
    if not shortcuts:
        return None

    candidates = [query] + ALIASES.get(query, [])

    for cand in candidates:
        if cand in shortcuts:
            return shortcuts[cand]

    for cand in candidates:
        if len(cand) < 3:
            continue
        starts = [name for name in shortcuts if name.startswith(cand)]
        if starts:
            return shortcuts[min(starts, key=len)]

    for cand in candidates:
        if len(cand) < 3:
            continue
        inside = [name for name in shortcuts if cand in name]
        if inside:
            return shortcuts[min(inside, key=len)]

    return None


def load_user_apps():
    """Читает apps.json: {название: путь}. При ошибке возвращает пустой словарь."""
    try:
        with open(USER_APPS_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, ValueError):
        return {}

    if not isinstance(data, dict):
        return {}

    return {norm(k): str(v) for k, v in data.items()}


def add_user_app(name, path):
    """Запоминает программу. Возвращает (успех, сообщение)."""
    name = norm(name)
    path = str(path).strip().strip('"').strip("'").strip()

    if not name:
        return False, "Не вижу названия программы."

    if "://" not in path and not Path(path).exists():
        return False, f"Не нашла такой файл: {path}"

    apps = load_user_apps()
    apps[name] = path

    try:
        with open(USER_APPS_FILE, "w", encoding="utf-8") as file:
            json.dump(apps, file, ensure_ascii=False, indent=2)
    except OSError as exc:
        return False, f"Не удалось сохранить список программ: {exc}"

    return True, f"Запомнила: «{name}» → {path}"


def load_aliases():
    """Слова-замены, которые пользователь научил ПИПКУ: {как слышу: что открыть}."""
    try:
        with open(ALIASES_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {norm(k): norm(v) for k, v in data.items() if norm(k) and norm(v)}


def add_alias(heard, meaning):
    heard = norm(heard)
    meaning = norm(meaning)
    if not heard or not meaning:
        return False, "Не поняла, что с чем связать. Скажи: запомни, что <как слышу> это <программа>."

    aliases = load_aliases()
    aliases[heard] = meaning
    try:
        with open(ALIASES_FILE, "w", encoding="utf-8") as file:
            json.dump(aliases, file, ensure_ascii=False, indent=2)
    except OSError as exc:
        return False, f"Не удалось сохранить: {exc}"

    return True, f"Запомнила: когда слышу «{heard}», открываю «{meaning}»."


def resolve_word(q):
    """Сначала слова, которым научил пользователь, потом встроенные исправления."""
    aliases = load_aliases()
    return aliases.get(q) or WORD_FIXES.get(q) or q


def _user_target(path):
    if "://" in path:
        return ("uri", path)  # например steam://rungameid/...
    if Path(path).exists():
        return ("file", path)
    return ("missing", path)


# ---------- Игры Steam ----------
_steam_cache = None
STEAM_SKIP = ("redistributable", "steamworks", "soundtrack", "dedicated server", "sdk")


def _steam_root():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            return Path(winreg.QueryValueEx(key, "SteamPath")[0])
    except (ImportError, OSError):
        return None


def steam_games():
    """Установленные игры Steam: {название: номер игры}. Читается один раз."""
    global _steam_cache
    if _steam_cache is not None:
        return _steam_cache

    games = {}
    root = _steam_root()
    if root is not None:
        libraries = {root}
        try:
            vdf = (root / "steamapps" / "libraryfolders.vdf").read_text(encoding="utf-8", errors="replace")
            for path in re.findall(r'"path"\s+"(.+?)"', vdf):
                libraries.add(Path(path.replace("\\\\", "\\")))
        except OSError:
            pass

        for library in libraries:
            try:
                manifests = list((library / "steamapps").glob("appmanifest_*.acf"))
            except OSError:
                continue
            for manifest in manifests:
                try:
                    text = manifest.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                appid = re.search(r'"appid"\s+"(\d+)"', text)
                name = re.search(r'"name"\s+"(.+?)"', text)
                if appid and name and not any(w in name.group(1).lower() for w in STEAM_SKIP):
                    games[name.group(1)] = appid.group(1)

    _steam_cache = games
    return games


def catalog():
    """Всё, что можно открыть: {название: (тип, цель)} — меню «Пуск», игры Steam, apps.json."""
    items = {name: ("file", str(path)) for name, path in _shortcuts().items()}
    for name, appid in steam_games().items():
        items[name] = ("uri", f"steam://rungameid/{appid}")
    for name, path in load_user_apps().items():
        items[name] = _user_target(path)
    return items


# ---------- Сравнение «по звучанию» ----------
# Русская модель речи пишет английские слова русскими буквами: «зе байндинг оф айзек».
# Переводим обе строки в грубый «звуковой ключ» (только согласные, похожие звуки
# склеены), тогда «айзек» и «isaac» становятся одинаковыми.
_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ж": "zh", "з": "z",
    "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p",
    "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch",
    "ш": "sh", "щ": "sh", "ъ": "", "ы": "i", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}
_DIGRAPHS = (("th", "s"), ("ph", "f"), ("ck", "k"), ("sh", "S"), ("zh", "S"), ("ch", "C"),
             ("kh", "k"), ("wh", "v"), ("qu", "kv"), ("x", "ks"), ("j", "dS"))
_SOUND_GROUPS = str.maketrans({
    "b": "p", "d": "t", "g": "k", "c": "k", "q": "k", "v": "f", "w": "f", "z": "s",
})
_STOP_WORDS = {"the", "of", "a", "an", "зе", "зэ", "де", "дэ", "оф", "ов", "э"}


def sound_key(text):
    words = []
    for word in re.findall(r"[a-zа-я]+", norm(text)):
        if word in _STOP_WORDS:
            continue
        word = "".join(_TRANSLIT.get(ch, ch) for ch in word)
        for a, b in _DIGRAPHS:
            word = word.replace(a, b)
        word = re.sub(r"[aeiouyh]", "", word).translate(_SOUND_GROUPS)
        word = re.sub(r"(.)\1+", r"\1", word)
        if word:
            words.append(word)
    return words


def _ratio(a, b):
    score = difflib.SequenceMatcher(None, a, b).ratio()
    # Первый звук слова микрофон обычно слышит верно: если он разный — слова вряд ли те
    if a and b and a[0] != b[0]:
        score *= 0.8
    return score


def _sound_score(qk, nk):
    whole = _ratio("".join(qk), "".join(nk))
    # Очень короткое слово («опера» -> «pr») совпадает с чем угодно — только целиком
    if len("".join(qk)) < 3:
        return whole - 0.08
    # Каждое сказанное слово ищем среди слов названия. Можно сказать только часть
    # названия: «айзек ребёрт» -> «The Binding of Isaac: Rebirth».
    bests = [max(_ratio(w, n) for n in nk) for w in qk]
    word_score = sum(bests) / len(bests)
    used = sum(1 for n in nk if max(_ratio(w, n) for w in qk) >= 0.7)
    word_score *= 0.9 + 0.1 * used / len(nk)
    # Целиком строкой (для названий из букв, вроде R.E.P.O.) — с более строгим порогом
    return max(word_score, whole - 0.08)


def sound_match(query, names, cutoff=0.84):
    """Самое похожее по звучанию название из names или None."""
    qk = sound_key(query)
    if len("".join(qk)) < 2:
        return None

    best, best_score = None, 0.0
    for name in names:
        nk = sound_key(name)
        if not nk:
            continue
        score = _sound_score(qk, nk)
        if score > best_score or (score == best_score and best and len(name) < len(best)):
            best, best_score = name, score

    return best if best_score >= cutoff else None


last_found_name = ""


def find(query):
    """Ищет программу. Возвращает (тип, цель) или None.
    Тип 'missing' — программа записана, но файла уже нет.
    Название найденного кладётся в last_found_name."""
    global last_found_name
    last_found_name = ""
    q = norm(query)
    if not q:
        return None
    result = _find(q)
    if result is not None and not last_found_name:
        last_found_name = q
    return result


def _find(q):
    global last_found_name

    user_apps = load_user_apps()
    resolved = resolve_word(q)
    if resolved != q:
        last_found_name = resolved

    # Сначала то, что пользователь записал под тем же словом, как оно прозвучало
    for key in dict.fromkeys([q, resolved]):
        if key in user_apps:
            target = user_apps[key]
            if not last_found_name and "://" not in target:
                last_found_name = Path(target).stem  # «майнкрафт» -> Lexplosion
            return _user_target(target)

    if resolved in SYSTEM_APPS:
        return SYSTEM_APPS[resolved]

    shortcut = _match_shortcut(resolved)
    if shortcut is not None:
        return ("file", str(shortcut))

    for name in [resolved] + ALIASES.get(resolved, []):
        for env_name, *parts in KNOWN_PATHS.get(name, []):
            base = os.environ.get(env_name)
            if not base:
                continue
            path = Path(base).joinpath(*parts)
            if path.is_file():
                return ("file", str(path))

    # Игры Steam и всё остальное: сначала по тексту, потом «по звучанию»
    items = catalog()
    for name in items:
        if norm(name) == resolved or norm(name).startswith(resolved + " ") or (
            len(resolved) >= 4 and resolved in norm(name)
        ):
            last_found_name = name
            return items[name]

    name = sound_match(resolved, items)
    if name is not None:
        last_found_name = name
        return items[name]

    return None


def launch(kind, target):
    """Отправляет запуск системе. Ошибки приходят как OSError."""
    if kind == "exe":
        subprocess.Popen([target], shell=False)
    elif kind in ("file", "folder", "uri"):
        if not hasattr(os, "startfile"):
            raise OSError("Запуск программ работает только в Windows.")
        os.startfile(target)
    else:
        raise OSError("Неизвестный тип запуска.")
