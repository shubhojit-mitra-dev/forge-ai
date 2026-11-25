"""Supabase HS256 JWT authentication middleware and FastAPI dependency."""

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings, get_settings

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(slots=True, frozen=True)
class UserContext:
    """Authenticated user identity extracted from a verified Supabase JWT."""

    user_id: UUID
    email: str | None = None


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UserContext:
    """Verify a Supabase HS256 Bearer JWT and return the authenticated UserContext."""
    if credentials is None or not credentials.credentials:
        raise _unauthorized("Missing authentication token")

    if not settings.supabase_jwt_secret:
        raise _unauthorized("JWT verification secret is not configured")

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
    except jwt.ExpiredSignatureError as exc:
        raise _unauthorized("Authentication token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise _unauthorized("Invalid authentication token") from exc

    sub = payload.get("sub")
    if not isinstance(sub, str) or not sub:
        raise _unauthorized("Token missing subject claim")

    try:
        user_id = UUID(sub)
    except ValueError as exc:
        raise _unauthorized("Invalid token subject") from exc

    raw_email = payload.get("email")
    email = str(raw_email) if raw_email is not None else None
    return UserContext(user_id=user_id, email=email)


CurrentUser = Annotated[UserContext, Depends(get_current_user)]
