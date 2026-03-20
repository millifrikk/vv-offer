"""Authentication utilities - password hashing, cookie signing, auth dependencies."""

from fastapi import Request
from fastapi.responses import RedirectResponse
import bcrypt as _bcrypt
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from app.config import settings
from app.db.models import get_user_by_id

_serializer = URLSafeTimedSerializer(settings.secret_key)
COOKIE_NAME = "vv_session"


def hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())


def create_session_cookie(user_id: int) -> str:
    return _serializer.dumps({"uid": user_id})


def read_session_cookie(cookie_value: str) -> int | None:
    try:
        data = _serializer.loads(cookie_value, max_age=settings.session_max_age)
        return data.get("uid")
    except (BadSignature, SignatureExpired):
        return None


def get_current_user(request: Request) -> dict | None:
    """Read session cookie and return user dict, or None."""
    cookie = request.cookies.get(COOKIE_NAME)
    if not cookie:
        return None
    user_id = read_session_cookie(cookie)
    if user_id is None:
        return None
    return get_user_by_id(user_id)


def require_user(request: Request) -> dict | RedirectResponse:
    """Return current user or redirect to login."""
    user = get_current_user(request)
    if user is None:
        return None  # Caller checks and redirects
    return user


def require_admin(request: Request) -> dict | None:
    """Return current user if admin, or None."""
    user = get_current_user(request)
    if user is None or not user.get("is_admin"):
        return None
    return user
