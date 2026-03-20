"""Analysis history - list all past analyses."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import get_current_user
from app.db.models import get_all_analyses, get_analysis, get_db

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/analyses", response_class=HTMLResponse)
async def list_analyses(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    analyses = get_all_analyses()

    return templates.TemplateResponse("history.html", {
        "request": request,
        "user": user,
        "analyses": analyses,
    })


@router.post("/analyses/{analysis_id}/delete")
async def delete_analysis(request: Request, analysis_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    analysis = get_analysis(analysis_id)
    if not analysis:
        return RedirectResponse("/analyses", status_code=302)

    # Only allow delete if user owns it or is admin
    if analysis["user_id"] != user["id"] and not user["is_admin"]:
        return RedirectResponse("/analyses", status_code=302)

    conn = get_db()
    conn.execute("DELETE FROM analysis_files WHERE analysis_id = ?", (analysis_id,))
    conn.execute("DELETE FROM analyses WHERE id = ?", (analysis_id,))
    conn.commit()
    conn.close()

    return RedirectResponse("/analyses", status_code=302)
