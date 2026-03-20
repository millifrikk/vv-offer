"""Admin routes - user management and cache control."""

import sqlite3

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import require_admin, hash_password
from app.config import settings
from app.db.models import get_all_users, create_user, delete_user

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="app/templates")


def _ensure_cache_table(conn):
    """Create ai_cache table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ai_cache (
            cache_key TEXT PRIMARY KEY,
            response TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


def get_cache_stats() -> dict:
    """Get AI cache statistics."""
    db_path = settings.db_path
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        _ensure_cache_table(conn)
        count = conn.execute("SELECT COUNT(*) FROM ai_cache").fetchone()[0]
        oldest = conn.execute("SELECT MIN(created_at) FROM ai_cache").fetchone()[0]
        newest = conn.execute("SELECT MAX(created_at) FROM ai_cache").fetchone()[0]
        conn.close()
        return {"count": count, "oldest": oldest, "newest": newest}
    except Exception:
        return {"count": 0, "oldest": None, "newest": None}


def flush_ai_cache():
    """Delete all AI cached responses."""
    db_path = settings.db_path
    conn = sqlite3.connect(db_path)
    _ensure_cache_table(conn)
    conn.execute("DELETE FROM ai_cache")
    conn.commit()
    conn.close()


@router.get("/users", response_class=HTMLResponse)
async def users_page(request: Request):
    user = require_admin(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    users = get_all_users()
    cache_stats = get_cache_stats()

    return templates.TemplateResponse("admin_users.html", {
        "request": request,
        "user": user,
        "users": users,
        "cache_stats": cache_stats,
    })


@router.post("/users")
async def add_user(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    is_admin: bool = Form(False),
):
    admin = require_admin(request)
    if not admin:
        return RedirectResponse("/login", status_code=302)

    create_user(
        email=email,
        name=name,
        password_hash=hash_password(password),
        is_admin=is_admin,
    )
    return RedirectResponse("/admin/users", status_code=302)


@router.post("/users/{user_id}/delete")
async def remove_user(request: Request, user_id: int):
    admin = require_admin(request)
    if not admin:
        return RedirectResponse("/login", status_code=302)

    if user_id == admin["id"]:
        return RedirectResponse("/admin/users", status_code=302)

    delete_user(user_id)
    return RedirectResponse("/admin/users", status_code=302)


@router.post("/cache/flush")
async def flush_cache(request: Request):
    admin = require_admin(request)
    if not admin:
        return RedirectResponse("/login", status_code=302)

    flush_ai_cache()
    return RedirectResponse("/admin/users", status_code=302)
