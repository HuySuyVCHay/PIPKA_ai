"""ИИ ПИПКИ — Gemini через интернет."""

from pipka import gemini_client, keystore
from pipka.config import SYSTEM_PROMPT

NO_KEY = "Чтобы я могла отвечать на вопросы, добавь ключ Gemini: ⚙ Настройки → Ввести ключ Gemini."


def has_key():
    return bool(keystore.get_gemini_key())


def build_system_prompt(facts=None, extra=""):
    prompt = SYSTEM_PROMPT
    if extra:
        prompt += "\n" + extra
    if facts:
        lines = "\n".join("- " + str(f) for f in facts)
        prompt += "\nТы знаешь о пользователе (используй, только когда это уместно):\n" + lines
    return prompt


def ask_stream(messages, on_chunk, facts=None, extra=""):
    """Возвращает текст ответа Gemini, кусочки текста по мере готовности отдаёт в on_chunk."""
    key = keystore.get_gemini_key()
    if not key:
        raise RuntimeError(NO_KEY)
    try:
        return gemini_client.ask_stream(messages, on_chunk, key, build_system_prompt(facts, extra))
    except gemini_client.GeminiError as exc:
        raise RuntimeError(str(exc)) from exc


def ask(messages, facts=None, extra=""):
    return ask_stream(messages, lambda chunk: None, facts, extra)


PICK_PROMPT = (
    "Пользователь сказал голосом, какую программу или игру открыть. Русское "
    "распознавание речи пишет английские слова русскими буквами и с ошибками "
    "(например «зе байндинг оф айзек» = The Binding of Isaac). Выбери из списка "
    "одно название, которое он имел в виду. Ответь ТОЛЬКО этим названием, точно "
    "как в списке, без кавычек. Если ничего не подходит, ответь: НЕТ"
)


def pick_program(heard, names):
    """Спрашивает Gemini, какую программу из списка имел в виду пользователь.
    Возвращает название из списка или None (в том числе, если нет ключа)."""
    key = keystore.get_gemini_key()
    if not key or not names:
        return None

    text = f"Сказал: «{heard}»\nСписок:\n" + "\n".join(names)
    try:
        answer = gemini_client.ask_stream(
            [{"role": "user", "content": text}], lambda chunk: None, key, PICK_PROMPT
        )
    except gemini_client.GeminiError:
        return None

    answer = answer.strip().strip("\"'«»").strip()
    by_lower = {name.lower(): name for name in names}
    return by_lower.get(answer.lower())
