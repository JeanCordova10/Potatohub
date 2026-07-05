from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, status

from app import database
from app.auth_context import require_current_user
from app.models import AuthSessionResponse, LoginRequest, PublicUser, RegisterRequest
from app.security import create_access_token, hash_password, normalize_email, verify_password


router = APIRouter()


@router.post("/register", response_model=AuthSessionResponse)
async def register(payload: RegisterRequest, request: Request):
    name = (payload.name or "").strip()
    email = normalize_email(payload.email)
    password = payload.password or ""

    if len(name) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Name must have at least 2 characters")
    if "@" not in email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A valid email is required")
    if len(password) < 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password must have at least 6 characters")
    if await database.get_user_by_email(email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user_doc = database.build_user_document(
        name=name,
        email=email,
        password_hash=hash_password(password),
        source="app_auth",
    )
    await database.get_users().insert_one(user_doc)

    neo4j_service = getattr(request.app.state, "neo4j_service", None)
    if neo4j_service is not None:
        await neo4j_service.write_user(user_doc)

    token = create_access_token(user_doc["user_id"])
    return AuthSessionResponse(token=token, user=PublicUser(**database.user_to_public(user_doc)))


@router.post("/login", response_model=AuthSessionResponse)
async def login(payload: LoginRequest, request: Request):
    email = normalize_email(payload.email)
    user_doc = await database.get_user_by_email(email)
    if user_doc is None or not verify_password(payload.password or "", str(user_doc.get("password_hash") or ""), email=email):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if str(user_doc.get("status") or "active").lower() != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not active")

    now = datetime.now(timezone.utc)
    await database.get_users().update_one(
        {"_id": user_doc["_id"]},
        {"$set": {"last_login_at": now, "updated_at": now}},
    )
    user_doc["last_login_at"] = now
    user_doc["updated_at"] = now

    neo4j_service = getattr(request.app.state, "neo4j_service", None)
    if neo4j_service is not None:
        await neo4j_service.write_user(user_doc)

    token = create_access_token(user_doc["user_id"])
    return AuthSessionResponse(token=token, user=PublicUser(**database.user_to_public(user_doc)))


@router.get("/me", response_model=PublicUser)
async def me(request: Request):
    user = await require_current_user(request)
    return PublicUser(**database.user_to_public(user))
