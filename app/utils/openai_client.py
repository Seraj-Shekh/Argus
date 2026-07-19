"""GPT-4o mini alert generator for fire risk predictions.

Generates plain-language alert messages in English and Finnish based on the
model's risk output and weather conditions. Falls back to pre-written templates
if the OpenAI API is unreachable, rate-limited, or returns an unexpected response.
"""
from __future__ import annotations

import json
import time
from typing import Optional

from app.config.settings import settings

# Lazy-initialised so the import doesn't fail if the key is missing at startup
_client = None


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(api_key=settings.openai_api_key, timeout=15.0)
    return _client


# ---------------------------------------------------------------------------
# Fallback templates — used when OpenAI is unreachable
# ---------------------------------------------------------------------------

_FALLBACK: dict[str, dict[str, str]] = {
    "high": {
        "en": (
            "HIGH FIRE RISK detected at this location. Current conditions — "
            "{temp}°C, {humidity}% humidity, {wind} m/s wind — are highly "
            "favourable for forest fire ignition and spread. "
            "Avoid any open flames and report smoke immediately to 112."
        ),
        "fi": (
            "KORKEA PALOVAARA havaittu tällä alueella. Nykyiset olosuhteet — "
            "{temp}°C, {humidity}% kosteus, {wind} m/s tuuli — ovat erittäin "
            "otolliset metsäpalojen syttymiselle ja leviämiselle. "
            "Vältä avotulen tekemistä ja ilmoita savusta välittömästi numeroon 112."
        ),
    },
    "medium": {
        "en": (
            "MEDIUM FIRE RISK detected at this location. Conditions — "
            "{temp}°C, {humidity}% humidity, {wind} m/s wind — show elevated "
            "fire danger. Exercise caution with any fire-related activities "
            "and monitor local conditions closely."
        ),
        "fi": (
            "KOHTALAINEN PALOVAARA havaittu tällä alueella. Olosuhteet — "
            "{temp}°C, {humidity}% kosteus, {wind} m/s tuuli — osoittavat "
            "kohonnutta paloriski. Ole varovainen kaikkien tuleen liittyvien "
            "toimien suhteen ja seuraa paikallisia olosuhteita."
        ),
    },
}


def _fallback(risk_level: str, features: dict) -> dict:
    tmpl = _FALLBACK.get(risk_level, _FALLBACK["medium"])
    fmt = {
        "temp":     features.get("temperature", "N/A"),
        "humidity": features.get("humidity", "N/A"),
        "wind":     features.get("wind_speed", "N/A"),
    }
    return {
        "message_en":  tmpl["en"].format(**fmt),
        "message_fi":  tmpl["fi"].format(**fmt),
        "ai_metadata": None,
    }


# ---------------------------------------------------------------------------
# Main generation function
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are an automated fire risk monitoring system for Finland. "
    "You generate concise, factual fire risk alerts based on weather data and "
    "a machine learning model's output. Keep messages to 2–3 sentences. "
    "Do not use emojis. Do not speculate beyond the provided data."
)


def generate_alert(
    risk_level: str,
    location_name: str,
    features: dict,
    fire_probability: float,
) -> dict:
    """
    Call GPT-4o mini to generate an alert in English and Finnish.

    Args:
        risk_level:        'medium' or 'high'
        lat, lon:          location coordinates
        features:          dict with temperature, humidity, wind_speed, precipitation etc.
        fire_probability:  model output probability (0–1)

    Returns:
        {
            "message_en":  str,
            "message_fi":  str,
            "ai_metadata": {model, prompt_tokens, completion_tokens, total_tokens, latency_ms} | None
        }
    """
    if not settings.openai_api_key:
        return _fallback(risk_level, features)

    temp    = features.get("temperature")
    humidity = features.get("humidity")
    wind    = features.get("wind_speed")
    precip  = features.get("precipitation")

    user_prompt = (
        f"Fire risk level: {risk_level.upper()}\n"
        f"Model fire probability: {fire_probability:.1%}\n"
        f"Location: {location_name}, Finland\n"
        f"Temperature: {temp}°C\n"
        f"Relative humidity: {humidity}%\n"
        f"Wind speed: {wind} m/s\n"
        f"24h forecast precipitation: {precip} mm\n\n"
        "Generate a fire risk alert. Respond with a JSON object with exactly "
        "two keys: \"en\" (English alert) and \"fi\" (Finnish alert). "
        "Each value must be a plain string of 2–3 sentences."
    )

    t0 = time.monotonic()
    try:
        client = _get_client()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=300,
        )
        latency_ms = int((time.monotonic() - t0) * 1000)

        content = response.choices[0].message.content
        parsed  = json.loads(content)

        message_en = parsed.get("en", "").strip()
        message_fi = parsed.get("fi", "").strip()

        if not message_en or not message_fi:
            raise ValueError("OpenAI response missing 'en' or 'fi' field")

        return {
            "message_en": message_en,
            "message_fi": message_fi,
            "ai_metadata": {
                "model":             response.model,
                "prompt_tokens":     response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens":      response.usage.total_tokens,
                "latency_ms":        latency_ms,
            },
        }

    except Exception:
        # Any failure — timeout, rate limit, parse error — falls back to template
        return _fallback(risk_level, features)
