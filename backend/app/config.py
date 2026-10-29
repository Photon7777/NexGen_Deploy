from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Supabase Postgres. Use the transaction pooler (port 6543) on Cloud Run.
    database_url: str
    # https://<project-ref>.supabase.co. Used to fetch the JWT signing keys and check the issuer.
    supabase_url: str = ""
    # Only for projects still on the legacy shared-secret (HS256) JWTs, and for tests.
    supabase_jwt_secret: str = ""
    # JSON list, e.g. ["https://nexlearn.vercel.app"]
    allowed_origins: list[str] = ["http://localhost:3000"]

    # AI features are off when no key is set.
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    # The deployed app runs on the owner's OpenAI key. Also set a monthly budget in OpenAI.
    ai_requests_per_user_per_day: int = 30
    ai_requests_per_day: int = 300


@lru_cache
def get_settings() -> Settings:
    return Settings()
