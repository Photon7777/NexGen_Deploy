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


@lru_cache
def get_settings() -> Settings:
    return Settings()
