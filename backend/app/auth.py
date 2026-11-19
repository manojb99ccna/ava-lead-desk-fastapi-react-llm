"""Admin authentication: Argon2id password hashing, JWT tokens and role checks."""
import hashlib
import hmac
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .core.config import settings
from .database import get_db
from .models import ROLE_ADMIN, ROLE_STAFF, Admin

JWT_ALGORITHM = "HS256"

_hasher = PasswordHasher()  # argon2id with library defaults
bearer = HTTPBearer(auto_error=False)


def _is_legacy_md5(stored: str) -> bool:
    return len(stored) == 32 and all(c in "0123456789abcdef" for c in stored.lower())


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, stored: str) -> bool:
    """Checks a password against an Argon2 hash, or a legacy MD5 digest."""
    if not stored:
        return False
    if _is_legacy_md5(stored):
        digest = hashlib.md5(password.encode()).hexdigest()
        return hmac.compare_digest(digest, stored.lower())
    try:
        return _hasher.verify(stored, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(stored: str) -> bool:
    if _is_legacy_md5(stored):
        return True
    try:
        return _hasher.check_needs_rehash(stored)
    except InvalidHashError:
        return True


def create_token(admin: Admin) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(admin.id),
        "role": admin.role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def current_admin(
    creds: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> Admin:
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Not authenticated", headers={"WWW-Authenticate": "Bearer"}
    )
    if not creds:
        raise unauthorized
    try:
        payload = jwt.decode(
            creds.credentials,
            settings.jwt_secret,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
        admin_id = int(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise unauthorized
    admin = db.get(Admin, admin_id)
    if not admin or not admin.is_active:
        raise unauthorized
    return admin


def require_roles(*roles: str):
    """Dependency factory: allows only users whose role is in `roles`."""

    def checker(admin: Admin = Depends(current_admin)) -> Admin:
        if admin.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission for this action")
        return admin

    return checker


# Staff and admins can work with day-to-day data; only admins change configuration and users.
require_staff = require_roles(ROLE_ADMIN, ROLE_STAFF)
require_admin = require_roles(ROLE_ADMIN)
