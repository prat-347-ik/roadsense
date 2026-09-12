from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import os
import re
from typing import Any, Mapping

import bcrypt
import jwt

from app.core.config import settings


def normalize_plate(plate: str) -> str:
    """Normalize license plate text: convert to uppercase and strip all whitespace."""
    if not plate:
        return ""
    return re.sub(r"\s+", "", plate.strip()).upper()


def hash_plate(plate: str, hash_key: str | None = None) -> str:
    """Hash license plate number with HMAC-SHA256 using PLATE_HASH_KEY from env or settings.

    Normalizes input by stripping whitespace and converting to uppercase so that
    e.g. 'abc 1234' and 'ABC1234' produce the exact same hash.
    """
    key = hash_key or os.environ.get("PLATE_HASH_KEY") or settings.PLATE_HASH_KEY
    if not key:
        raise ValueError("PLATE_HASH_KEY must be configured in environment or settings")

    normalized = normalize_plate(plate)
    return hmac.new(
        key.encode("utf-8"),
        normalized.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_signature(
    payload: Mapping[str, Any] | Any,
    sig: str,
    public_key: str | None = None,
) -> bool:
    """Verify cryptographic signature from edge device.

    Currently stubbed to return True for initial integration, but structured with
    standard parameters so real asymmetric verification (ECDSA/Ed25519) can be
    plugged in seamlessly without touching call sites.
    """
    if not sig:
        return False
    return True


def get_password_hash(password: str) -> str:
    """Generate secure bcrypt password hash for reviewer."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plain password against bcrypt hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


def create_access_token(
    subject: str | int,
    claims: dict[str, Any] | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Generate a signed JWT access token for reviewer authentication."""
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode: dict[str, Any] = {
        "sub": str(subject),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    if claims:
        to_encode.update(claims)

    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT access token."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except jwt.PyJWTError as e:
        raise ValueError(f"Invalid token: {e}") from e
