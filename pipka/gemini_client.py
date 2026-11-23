"""Облачный ИИ Gemini через официальный REST-интерфейс."""

import json

import requests

from pipka.config import GEMINI_MODEL, GEMINI_MAX_TOKENS

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

# Названия, которые не подходят для обычного чата
_SKIP_WORDS = (
    "lite", "image", "tts", "live", "audio", "embedding", "vision",
    "robotics", "computer", "thinking", "learnlm", "gemma",
)
_PREFERRED = (
    "gemini-flash-latest",
    "gemini-3.5-flash",
    "gemini-3-flash",
    "gemini-2.5-flash",
)

_model_cache = {"name": None}


class GeminiError(RuntimeError):
    """Любая проблема с Gemini: тогда ПИПКА переключится на локальную модель."""


def reset_model_cache():
    _model_cache["name"] = None


def _headers(key):
    return {"x-goog-api-key": key, "Content-Type": "application/json"}


def _explain(response):
    """Понятное объяснение ошибки. В конце — текст ответа Google для диагностики."""
    try:
        message = response.json().get("error", {}).get("message", "")
    except ValueError:
        message = ""

    code = response.status_code
    low = message.lower()
    detail = f" (ответ Google: {message[:120]})" if message else ""

    region_block = (
        "location is not supported" in low
        or "not available in your" in low
        or ("country" in low and "not supported" in low)
    )
    if region_block:
        return (
            "Google не даёт доступ к Gemini API в твоём регионе или из текущей сети."
            + detail
        )
    if code == 401 or (code == 400 and "api key" in low):
        return (
            "Ключ Gemini не подошёл. Создай новый на aistudio.google.com "
            "и вставь его в ⚙ Настройках." + detail
        )
    if code == 403:
        return "Google запретил доступ к Gemini для этого ключа или аккаунта." + detail
    if code == 429:
        return "Закончился бесплатный лимит Gemini (на минуту или на день)."
    if code == 404:
        reset_model_cache()
        return "Модель Gemini не найдена." + detail
    if code >= 500:
        return "Сервер Gemini сейчас перегружен. Попробуй позже."
    return f"Ошибка Gemini {code}." + detail


def pick_model(key):
    """Название модели: из настроек или автоматически из списка доступных."""
    if GEMINI_MODEL:
        return GEMINI_MODEL
    if _model_cache["name"]:
        return _model_cache["name"]

    try:
        response = requests.get(
            f"{BASE_URL}/models",
            headers=_headers(key),
            params={"pageSize": 1000},
            timeout=10,
        )
    except requests.Timeout as exc:
        raise GeminiError("Gemini не ответил вовремя.") from exc
    except requests.RequestException as exc:
        raise GeminiError("Нет связи с Gemini (проверь интернет).") from exc

    if response.status_code != 200:
        raise GeminiError(_explain(response))

    try:
        models = response.json().get("models", [])
    except ValueError as exc:
        raise GeminiError("Gemini вернул непонятный ответ.") from exc

    names = []
    for item in models:
        if "generateContent" not in item.get("supportedGenerationMethods", []):
            continue
        name = str(item.get("name", "")).replace("models/", "")
        if name:
            names.append(name)

    chosen = None
    for preferred in _PREFERRED:
        if preferred in names:
            chosen = preferred
            break

    if chosen is None:
        flash = [
            n for n in names
            if "flash" in n and not any(w in n for w in _SKIP_WORDS)
        ]
        stable = [n for n in flash if "preview" not in n and "exp" not in n]
        pool = stable or flash
        if pool:
            chosen = min(pool, key=len)

    if chosen is None:
        raise GeminiError("Не нашла подходящую модель Gemini в списке доступных.")

    _model_cache["name"] = chosen
    return chosen


def to_contents(messages):
    """История чата -> формат Gemini (роли user/model, начинается с user)."""
    contents = []
    for message in messages:
        text = str(message.get("content", "")).strip()
        if not text:
            continue
        role = "user" if message.get("role") == "user" else "model"
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"][0]["text"] += "\n" + text
        else:
            contents.append({"role": role, "parts": [{"text": text}]})

    while contents and contents[0]["role"] != "user":
        contents.pop(0)

    return contents


def ask_stream(messages, on_chunk, key, system_prompt):
    contents = to_contents(messages)
    if not contents:
        raise GeminiError("Нечего отправлять в Gemini.")

    model = pick_model(key)

    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": GEMINI_MAX_TOKENS,
            "temperature": 0.8,
        },
    }

    url = f"{BASE_URL}/models/{model}:streamGenerateContent?alt=sse"
    parts = []

    try:
        with requests.post(
            url,
            headers=_headers(key),
            json=payload,
            stream=True,
            timeout=(10, 60),
        ) as response:
            if response.status_code != 200:
                raise GeminiError(_explain(response))

            for raw in response.iter_lines():
                if not raw:
                    continue

                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue

                data_text = line[5:].strip()
                if not data_text or data_text == "[DONE]":
                    continue

                try:
                    event = json.loads(data_text)
                except ValueError:
                    continue

                if "error" in event:
                    message = event["error"].get("message", "неизвестная ошибка")
                    raise GeminiError(f"Gemini вернул ошибку: {message[:150]}")

                block = event.get("promptFeedback", {}).get("blockReason")
                if block:
                    raise GeminiError("Gemini отклонил запрос фильтром безопасности.")

                for candidate in event.get("candidates", []):
                    for part in candidate.get("content", {}).get("parts", []):
                        text = part.get("text")
                        if text and not part.get("thought"):
                            parts.append(text)
                            on_chunk(text)

    except requests.Timeout as exc:
        raise GeminiError("Gemini не ответил вовремя.") from exc
    except requests.RequestException as exc:
        raise GeminiError("Нет связи с Gemini (проверь интернет).") from exc

    answer = "".join(parts).strip()
    if not answer:
        raise GeminiError("Gemini не вернул текст (возможно, сработал фильтр).")

    return answer
