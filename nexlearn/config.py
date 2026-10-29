"""Settings shared across the app: time zone, model, API key lookup, usage caps."""
from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

# All times in the app are naive datetimes in this zone. Streamlit Cloud runs on UTC,
# so "now" must come from here, never from datetime.now() directly.
TZ = ZoneInfo("America/New_York")

DEFAULT_MODEL = "gpt-4o-mini"

# The deployed app runs on the owner's OpenAI key, so cap how much any one visitor
# (and everyone together) can spend. Set a monthly budget in OpenAI as well.
AI_CALLS_PER_SESSION = 20
AI_CALLS_PER_DAY = 300


def now() -> datetime:
    """Current time in Eastern, without tzinfo."""
    return datetime.now(TZ).replace(tzinfo=None)


def _secret(name: str) -> str | None:
    try:
        import streamlit as st

        value = st.secrets.get(name)
    except Exception:  # no secrets.toml, or not running under Streamlit
        value = None
    return value or os.getenv(name) or None


def openai_api_key() -> str | None:
    """Streamlit secrets first (Streamlit Cloud), then the environment / .env file."""
    return _secret("OPENAI_API_KEY")


def openai_model() -> str:
    return _secret("OPENAI_MODEL") or DEFAULT_MODEL
