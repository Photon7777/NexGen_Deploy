"""Verify the Supabase access token the frontend sends as `Authorization: Bearer <jwt>`."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings, get_settings

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class User:
    id: str
    email: str | None
    claims: dict


@lru_cache
def _jwks_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(url, cache_keys=True)


def decode_token(token: str, settings: Settings) -> dict:
    """Newer Supabase projects sign with asymmetric keys published at a JWKS URL;
    older ones use a shared HS256 secret. The algorithm in the token header picks
    the key, but only from algorithms this server is configured to accept."""
    alg = jwt.get_unverified_header(token).get("alg")
    if alg in ("ES256", "RS256") and settings.supabase_url:
        key = _jwks_client(f"{settings.supabase_url}/auth/v1/.well-known/jwks.json").get_signing_key_from_jwt(token).key
    elif alg == "HS256" and settings.supabase_jwt_secret:
        key = settings.supabase_jwt_secret
    else:
        raise jwt.InvalidTokenError(f"Tokens signed with {alg} are not accepted")

    return jwt.decode(
        token,
        key,
        algorithms=[alg],
        audience="authenticated",
        issuer=f"{settings.supabase_url}/auth/v1" if settings.supabase_url else None,
        options={"require": ["exp", "sub"]},
    )


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in required")
    try:
        claims = decode_token(creds.credentials, settings)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session") from None
    return User(id=claims["sub"], email=claims.get("email"), claims=claims)
