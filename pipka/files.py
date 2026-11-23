"""Поиск файлов и папок по названию: «открой папку папа», «открой горгаз 2025».
Список файлов собирается в фоне при запуске и обновляется раз в несколько минут."""

import difflib
import os
import random
import re
import threading
import time
from pathlib import Path

from pipka import apps

HOME_DEPTH = 5
DRIVE_DEPTH = 3
MAX_ENTRIES = 200_000
REFRESH_AFTER = 600

SKIP_DIRS = {
    "appdata", "node_modules", ".venv", "venv", "env", ".git", "__pycache__", ".idea",
    "steamapps", "windows", "program files", "program files (x86)", "programdata",
    "$recycle.bin", "system volume information", "site-packages", "dist", "build",
    "cache", "temp", "tmp", "libraries", "assets", "versions", "natives", "logs",
    "resourcepacks", "shaderpacks", "crash-reports", "runtime", "jre", "jdk",
}

_index = []
_built_at = 0.0
_building = threading.Event()
_lock = threading.Lock()


def _roots():
    """(папка, глубина, приоритет): сначала рабочий стол и документы, потом диски."""
    home = Path.home()
    roots = []
    for rank, name in enumerate(("Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music")):
        for base in (home, home / "OneDrive"):
            folder = base / name
            if folder.is_dir():
                roots.append((folder, HOME_DEPTH, rank))
    for letter in "DEFG":
        drive = Path(f"{letter}:/")
        if drive.exists():
            roots.append((drive, DRIVE_DEPTH, 10))
    return roots


def _compact(text):
    return re.sub(r"[^0-9a-zа-я]", "", apps.norm(text))


def _walk(root, max_depth, rank, entries, seen):
    stack = [(str(root), 0)]
    while stack and len(entries) < MAX_ENTRIES:
        folder, depth = stack.pop()
        try:
            with os.scandir(folder) as items:
                for item in items:
                    name = item.name
                    if name.startswith(".") or item.path.lower() in seen:
                        continue
                    try:
                        is_dir = item.is_dir(follow_symlinks=False)
                    except OSError:
                        continue
                    seen.add(item.path.lower())
                    stem, ext = (name, "") if is_dir else os.path.splitext(name)
                    # расширение — отдельным словом: «довольно rar» -> Davolash.rar
                    spoken = f"{stem} {ext.lstrip('.')}".strip()
                    keys = apps.sound_key(spoken)
                    entries.append((name, item.path, is_dir, _compact(stem), _compact(spoken),
                                    keys, "".join(keys), rank, depth))
                    if is_dir and depth < max_depth and name.lower() not in SKIP_DIRS:
                        stack.append((item.path, depth + 1))
        except OSError:
            continue


def build_index():
    global _index, _built_at
    if _building.is_set():
        return len(_index)
    _building.set()
    try:
        entries, seen = [], set()
        for root, depth, rank in _roots():
            _walk(root, depth, rank, entries, seen)
        with _lock:
            _index = entries
            _built_at = time.time()
        return len(entries)
    finally:
        _building.clear()


def build_in_background():
    threading.Thread(target=build_index, daemon=True).start()


def ready():
    return bool(_index)


# ---------- числа словами: «две тысячи двадцать пятый» -> 2025 ----------
_CARDINAL = {
    "ноль": 0, "один": 1, "одна": 1, "одно": 1, "одну": 1, "два": 2, "две": 2, "три": 3, "четыре": 4,
    "пять": 5, "шесть": 6, "семь": 7, "восемь": 8, "девять": 9, "десять": 10,
    "одиннадцать": 11, "двенадцать": 12, "тринадцать": 13, "четырнадцать": 14,
    "пятнадцать": 15, "шестнадцать": 16, "семнадцать": 17, "восемнадцать": 18,
    "девятнадцать": 19, "двадцать": 20, "тридцать": 30, "сорок": 40, "пятьдесят": 50,
    "шестьдесят": 60, "семьдесят": 70, "восемьдесят": 80, "девяносто": 90,
    "сто": 100, "двести": 200, "триста": 300, "четыреста": 400, "пятьсот": 500,
    "шестьсот": 600, "семьсот": 700, "восемьсот": 800, "девятьсот": 900,
}
_ORDINAL_STEMS = sorted({
    "перв": 1, "втор": 2, "трет": 3, "четверт": 4, "пят": 5, "шест": 6, "седьм": 7,
    "восьм": 8, "девят": 9, "десят": 10, "одиннадцат": 11, "двенадцат": 12,
    "тринадцат": 13, "четырнадцат": 14, "пятнадцат": 15, "шестнадцат": 16,
    "семнадцат": 17, "восемнадцат": 18, "девятнадцат": 19, "двадцат": 20,
    "тридцат": 30, "сороков": 40, "пятидесят": 50, "шестидесят": 60,
    "семидесят": 70, "восьмидесят": 80, "девяност": 90, "сот": 100,
    "двухсот": 200, "трехсот": 300,
}.items(), key=lambda item: -len(item[0]))
_ORDINAL_END = re.compile(r"ый|ой|ий|ая|ое|ые|ого|ому|ом|ую|ых|ым|ья|ье|ьего|ьей")


def _number_word(word):
    if word in _CARDINAL:
        return _CARDINAL[word]
    if word.startswith("тысяч"):
        return 1000
    for stem, value in _ORDINAL_STEMS:
        if word.startswith(stem) and _ORDINAL_END.fullmatch(word[len(stem):]):
            return value
    return None


def words_to_digits(text):
    out, total, current, active = [], 0, 0, False

    def flush():
        nonlocal total, current, active
        if active:
            out.append(str(total + current))
        total, current, active = 0, 0, False

    for word in text.split():
        value = _number_word(word)
        if value is None:
            flush()
            out.append(word)
            continue
        active = True
        if value == 1000:
            total += (current or 1) * 1000
            current = 0
        else:
            current += value
    flush()
    return " ".join(out)


# ---------- поиск ----------
_LOCATIONS = [
    (r"(?:на|с|со)\s+рабоч(?:ем|его)\s+стол[ае]?", ["Desktop"]),
    (r"(?:в|из)\s+загрузк(?:ах|ами|и)", ["Downloads"]),
    (r"(?:в|из)\s+документ(?:ах|ов)", ["Documents"]),
    (r"(?:в|из)\s+(?:картинк(?:ах|и)|изображени(?:ях|й)|фото)", ["Pictures"]),
    (r"(?:в|из)\s+видео", ["Videos"]),
    (r"(?:в|из)\s+музык(?:е|и)", ["Music"]),
]
_DRIVE_RE = re.compile(r"(?:на|с)\s+диск[еа]?\s+([a-zа-я])\b")
_DRIVE_LETTERS = {"д": "D", "е": "E", "э": "E", "ф": "F", "г": "G", "ц": "C", "с": "C"}
# Что считать «нормальным» файлом, когда просят «любой»
DOCUMENT_EXT = {".docx", ".doc", ".pdf", ".pptx", ".ppt", ".xlsx", ".xls", ".txt", ".odt",
                ".rtf", ".jpg", ".jpeg", ".png", ".mp4", ".mp3", ".rar", ".zip"}
ANY_RE = re.compile(r"\b(?:любой|любую|любое|какой нибудь|какую нибудь|какое нибудь|"
                    r"какой-нибудь|какую-нибудь|какое-нибудь|случайный|случайную|рандомный)\b")


def parse_query(text):
    """«любой реферат на рабочем столе» -> ("реферат", [папки], любой=True)."""
    text = apps.norm(text)
    roots = []
    for pattern, names in _LOCATIONS:
        if re.search(pattern, text):
            text = re.sub(pattern, " ", text)
            home = Path.home()
            for name in names:
                roots += [str(home / name), str(home / "OneDrive" / name)]
    drive = _DRIVE_RE.search(text)
    if drive:
        letter = _DRIVE_LETTERS.get(drive.group(1), drive.group(1).upper())
        roots.append(f"{letter}:\\")
        text = _DRIVE_RE.sub(" ", text)
    any_one = bool(ANY_RE.search(text))
    text = ANY_RE.sub(" ", text)
    return " ".join(text.split()), [r.lower() for r in roots], any_one


def _score(query_compact, query_keys, query_joined, entry, use_sound):
    compact, full, keys, joined = entry[3], entry[4], entry[5], entry[6]
    if not compact:
        return 0.0
    if query_compact in (compact, full):
        return 1.0

    score = 0.0
    matcher = difflib.SequenceMatcher(None, query_compact, compact)
    if matcher.real_quick_ratio() >= 0.6 and matcher.quick_ratio() >= 0.6:
        score = matcher.ratio()
    if len(query_compact) >= 4 and query_compact in full:
        score = max(score, 0.8 + 0.15 * len(query_compact) / len(full))

    # «по звучанию» — только если звуковые ключи заметно похожи (это быстро отсеивает лишнее)
    if use_sound and len(query_joined) >= 3 and joined and joined[0] == query_joined[0]:
        sound = difflib.SequenceMatcher(None, query_joined, joined)
        if sound.real_quick_ratio() >= 0.8 and sound.quick_ratio() >= 0.8:
            score = max(score, apps._sound_score(query_keys, keys) - 0.06)
    return score


def search(query, kind="", cutoff=0.8):
    """Ищет файл или папку. kind: "папку", "файл" или "".
    Понимает «на рабочем столе», «в загрузках», «на диске д» и «любой».
    Возвращает (путь, это_папка) или None."""
    query, roots, any_one = parse_query(query)
    query = words_to_digits(query)
    query_compact = _compact(query)
    if len(query_compact) < 2:
        return None
    if time.time() - _built_at > REFRESH_AFTER:
        build_in_background()

    query_keys = apps.sound_key(query)
    query_joined = "".join(query_keys)
    with _lock:
        entries = _index

    # Сначала по тексту, и только если ничего нет — «по звучанию»
    for use_sound in (False, True):
        found = []
        for entry in entries:
            is_dir = entry[2]
            if (kind == "папку" and not is_dir) or (kind == "файл" and is_dir):
                continue
            if roots and not entry[1].lower().startswith(tuple(roots)):
                continue
            score = _score(query_compact, query_keys, query_joined, entry, use_sound)
            if score >= cutoff:
                found.append((score, entry))
        if not found:
            continue
        if any_one:
            # «открой любой реферат» — случайный подходящий файл (файлы важнее папок)
            only_files = [e for _, e in found if not e[2]] if kind != "папку" else []
            documents = [e for e in only_files
                         if os.path.splitext(e[0])[1].lower() in DOCUMENT_EXT]
            entry = random.choice(documents or only_files or [e for _, e in found])
        else:
            entry = min(found, key=lambda item: (-round(item[0], 3), item[1][7], item[1][8]))[1]
        return entry[1], entry[2]
    return None
