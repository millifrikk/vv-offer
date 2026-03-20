"""Authentication routes - login/logout."""

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import verify_password, create_session_cookie, get_current_user, COOKIE_NAME
from app.db.models import get_user_by_email

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse("/analyses", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
async def login(request: Request, email: str = Form(...), password: str = Form(...)):
    user = get_user_by_email(email)
    if not user or not verify_password(password, user["password_hash"]):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Rangt netfang eða lykilorð",
        })

    response = RedirectResponse("/analyses", status_code=302)
    response.set_cookie(
        key=COOKIE_NAME,
        value=create_session_cookie(user["id"]),
        httponly=True,
        samesite="lax",
        max_age=604800,
    )
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    return response
