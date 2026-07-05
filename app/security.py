from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time


SEED_SOURCE = "seed_v1"
SEED_LOGIN_PASSWORD = "potato123"
PASSWORD_ITERATIONS = 200_000
TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7


def normalize_email(value: str) -> str:
    return (value or "").strip().lower()


def hash_password(password: str, salt: str | None = None) -> str:
    if not password:
        raise ValueError("Password cannot be empty")
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_ITERATIONS,
    )
    encoded = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt}${encoded}"


def _seed_hash_for_email(email: str) -> str:
    digest = hashlib.sha256(f"{SEED_SOURCE}:{normalize_email(email)}:potatohub".encode("utf-8")).hexdigest()
    return f"seeded_sha256${digest}"


def verify_password(password: str, stored_hash: str, email: str = "") -> bool:
    if not stored_hash:
        return False

    if stored_hash.startswith("pbkdf2_sha256$"):
        try:
            parts = stored_hash.split("$", 3)
            if len(parts) == 4:
                _, iterations, salt, encoded = parts
            elif len(parts) == 3:
                _, salt, encoded = parts
                iterations = str(PASSWORD_ITERATIONS)
            else:
                return False
            expected = hash_password(password, salt=salt).split("$", 3)[3]
            return hmac.compare_digest(encoded, expected)
        except ValueError:
            return False

    if stored_hash.startswith("seeded_sha256$"):
        return password == SEED_LOGIN_PASSWORD and hmac.compare_digest(stored_hash, _seed_hash_for_email(email))

    return False


def create_access_token(user_id: str, ttl_seconds: int = TOKEN_TTL_SECONDS) -> str:
    payload = {
        "sub": user_id,
        "exp": int(time.time()) + ttl_seconds,
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    secret = _token_secret().encode("utf-8")
    signature = hmac.new(secret, raw, hashlib.sha256).digest()
    return f"{_b64encode(raw)}.{_b64encode(signature)}"


def decode_access_token(token: str) -> str | None:
    if not token or "." not in token:
        return None
    payload_b64, signature_b64 = token.split(".", 1)
    raw = _b64decode(payload_b64)
    signature = _b64decode(signature_b64)
    if raw is None or signature is None:
        return None
    expected = hmac.new(_token_secret().encode("utf-8"), raw, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if int(payload.get("exp") or 0) <= int(time.time()):
        return None
    subject = str(payload.get("sub") or "").strip()
    return subject or None


def _token_secret() -> str:
    return os.getenv("POTATOHUB_AUTH_SECRET", "potatohub-local-secret")


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(data: str) -> bytes | None:
    padding = "=" * ((4 - len(data) % 4) % 4)
    try:
        return base64.urlsafe_b64decode((data + padding).encode("ascii"))
    except Exception:
        return None
