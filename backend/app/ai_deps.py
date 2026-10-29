"""The chat model dependency and the database-enforced AI usage caps."""
from fastapi import Depends, HTTPException
from langchain_core.language_models import BaseChatModel
from psycopg import Connection

from nexlearn import ai

from .config import Settings, get_settings
from .materials import Embedder, openai_embedder


def get_chat_model(settings: Settings = Depends(get_settings)) -> BaseChatModel:
    """Tests override this dependency with a scripted model."""
    if not settings.openai_api_key:
        raise HTTPException(503, "AI features are not configured on this server.")
    return ai.make_llm(settings.openai_api_key, settings.openai_model)


def get_extraction_model(settings: Settings = Depends(get_settings)) -> BaseChatModel:
    """Temperature 0 for reading documents: the same PDF should give the same answer."""
    if not settings.openai_api_key:
        raise HTTPException(503, "AI features are not configured on this server.")
    return ai.make_llm(settings.openai_api_key, settings.openai_model, temperature=0)


def get_embedder(settings: Settings = Depends(get_settings)) -> Embedder:
    """Tests override this dependency with a deterministic stand-in."""
    if not settings.openai_api_key:
        raise HTTPException(503, "AI features are not configured on this server.")
    return openai_embedder(settings.openai_api_key)


def take_ai_request(conn: Connection, kind: str, settings: Settings) -> None:
    """Record one AI request, or refuse with 429 when the student or the app is over its daily cap."""
    refusal = conn.execute(
        "select private.take_ai_request(%s, %s, %s) as refusal",
        (kind, settings.ai_requests_per_user_per_day, settings.ai_requests_per_day),
    ).fetchone()["refusal"]
    if refusal:
        raise HTTPException(429, refusal)


def ai_failure(e: Exception) -> HTTPException:
    return HTTPException(502, ai.friendly_error(e))
