from __future__ import annotations

from fastapi import Header, HTTPException, status

from app.config import Settings


async def require_api_token(
    settings: Settings,
    authorization: str | None = Header(default=None),
) -> None:
    if not settings.api_token:
        return
    expected = f'Bearer {settings.api_token}'
    if authorization != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Missing or invalid bearer token.',
            headers={'WWW-Authenticate': 'Bearer'},
        )
