from __future__ import annotations

from fastapi import HTTPException, Request, status

from app import database
from app.security import decode_access_token


def extract_bearer_token(header_value: str | None) -> str | None:
    if not header_value:
        return None
    parts = header_value.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


async def current_user_from_request(request: Request) -> dict | None:
    token = extract_bearer_token(request.headers.get("Authorization"))
    if not token:
        return None
    subject = decode_access_token(token)
    if not subject:
        return None
    return await database.get_user_by_id(subject)


async def require_current_user(request: Request) -> dict:
    user = await current_user_from_request(request)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return user
