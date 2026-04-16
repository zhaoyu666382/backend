from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
import base64
import hashlib
import hmac
import os

from jose import jwt, JWTError

from config import settings

# -----------------------------
# Password hashing (portable)
# -----------------------------
# Why:
# - Some environments (esp. Windows without build tools) may fail to install bcrypt.
# - For Software Copyright delivery, a portable demo should run out-of-the-box.
#
# Hash format (PBKDF2-HMAC-SHA256):
#   pbkdf2$<iterations>$<salt_b64>$<dk_b64>
#
# We also try to verify legacy bcrypt hashes if passlib/bcrypt is available.

_PBKDF2_ITERATIONS = 180_000
_SALT_BYTES = 16
_DK_BYTES = 32

def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("utf-8").rstrip("=")

def _b64d(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("utf-8"))

def hash_password(password: str) -> str:
    if not isinstance(password, str) or len(password) < 1:
        raise ValueError("password is empty")
    salt = os.urandom(_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS, dklen=_DK_BYTES)
    return f"pbkdf2${_PBKDF2_ITERATIONS}${_b64e(salt)}${_b64e(dk)}"

def _verify_pbkdf2(password: str, password_hash: str) -> bool:
    try:
        _, iters_s, salt_b64, dk_b64 = password_hash.split("$", 3)
        iters = int(iters_s)
        salt = _b64d(salt_b64)
        dk_expected = _b64d(dk_b64)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iters, dklen=len(dk_expected))
        return hmac.compare_digest(dk, dk_expected)
    except Exception:
        return False

def _looks_like_bcrypt(password_hash: str) -> bool:
    # Common bcrypt prefixes: $2a$, $2b$, $2y$
    return isinstance(password_hash, str) and password_hash.startswith("$2")

def _verify_bcrypt_if_available(password: str, password_hash: str) -> Optional[bool]:
    try:
        from passlib.context import CryptContext  # type: ignore
        ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
        return bool(ctx.verify(password, password_hash))
    except Exception:
        return None

def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    if password_hash.startswith("pbkdf2$"):
        return _verify_pbkdf2(password, password_hash)
    if _looks_like_bcrypt(password_hash):
        ok = _verify_bcrypt_if_available(password, password_hash)
        # If bcrypt is not available, we cannot verify legacy hashes reliably.
        return bool(ok)
    # Unknown scheme
    return False


# -----------------------------
# JWT
# -----------------------------
def create_access_token(subject: str, extra: Optional[Dict[str, Any]] = None, expires_minutes: Optional[int] = None) -> str:
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: Dict[str, Any] = {"sub": subject, "exp": expire}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> Dict[str, Any]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError as e:
        raise ValueError("Invalid token") from e
