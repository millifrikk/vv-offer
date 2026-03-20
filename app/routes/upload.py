"""Upload routes - file upload and analysis creation."""

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import get_current_user
from app.config import settings
from app.db.models import (
    create_analysis,
    get_analysis,
    get_analysis_files,
    add_analysis_file,
    get_analysis_file,
    update_analysis,
    get_db,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Temporary upload sessions - maps temp_id to user_id + uploaded file info
# Analysis DB row is only created when user starts processing or saves draft
_pending: dict[str, dict] = {}


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    return RedirectResponse("/analyses", status_code=302)


@router.get("/new", response_class=HTMLResponse)
async def new_analysis(request: Request):
    """Show upload page without creating a DB row yet."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    temp_id = str(uuid.uuid4())[:8]
    _pending[temp_id] = {"user_id": user["id"], "files": {}}

    return templates.TemplateResponse("upload.html", {
        "request": request,
        "user": user,
        "analysis_id": temp_id,
        "is_new": True,
        "uploaded_types": set(),
    })


@router.get("/upload/{analysis_id}", response_class=HTMLResponse)
async def upload_page(request: Request, analysis_id: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    # Check if it's a pending (not yet saved) analysis
    if analysis_id in _pending:
        uploaded_types = set(_pending[analysis_id]["files"].keys())
        return templates.TemplateResponse("upload.html", {
            "request": request,
            "user": user,
            "analysis_id": analysis_id,
            "is_new": True,
            "uploaded_types": uploaded_types,
        })

    # Otherwise it's an existing DB analysis
    try:
        aid = int(analysis_id)
    except ValueError:
        return RedirectResponse("/analyses", status_code=302)

    analysis = get_analysis(aid)
    if not analysis:
        return RedirectResponse("/analyses", status_code=302)

    files = get_analysis_files(aid)
    uploaded_types = {f["file_type"] for f in files}

    return templates.TemplateResponse("upload.html", {
        "request": request,
        "user": user,
        "analysis_id": analysis_id,
        "is_new": False,
        "uploaded_types": uploaded_types,
    })


@router.post("/upload/{analysis_id}")
async def upload_file(
    request: Request,
    analysis_id: str,
    file_type: str,
    file: UploadFile = File(...),
):
    """Upload a single file. Works for both pending and existing analyses."""
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    # Save file to disk
    upload_dir = settings.upload_dir / analysis_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_path = upload_dir / file.filename
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    file_size = file_path.stat().st_size

    if analysis_id in _pending:
        # Track in pending session
        _pending[analysis_id]["files"][file_type] = {
            "filename": file.filename,
            "file_path": str(file_path),
            "file_size": file_size,
        }
    else:
        # Existing DB analysis - update file
        try:
            aid = int(analysis_id)
        except ValueError:
            return JSONResponse({"error": "Invalid analysis ID"}, status_code=400)

        existing = get_analysis_file(aid, file_type)
        if existing:
            conn = get_db()
            conn.execute("DELETE FROM analysis_files WHERE id = ?", (existing["id"],))
            conn.commit()
            conn.close()

        add_analysis_file(aid, file_type, file.filename, str(file_path), file_size)

    return JSONResponse({
        "status": "ok",
        "file_type": file_type,
        "filename": file.filename,
        "size": file_size,
    })


@router.post("/upload/{analysis_id}/name")
async def set_project_name(request: Request, analysis_id: str, project_name: str = Form("")):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    if analysis_id in _pending:
        _pending[analysis_id]["project_name"] = project_name
    else:
        try:
            aid = int(analysis_id)
            update_analysis(aid, project_name=project_name)
        except ValueError:
            pass

    return JSONResponse({"status": "ok"})


@router.post("/upload/{analysis_id}/save")
async def save_to_db(request: Request, analysis_id: str):
    """Materialize a pending upload into a DB analysis row. Returns the real analysis_id."""
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    if analysis_id not in _pending:
        # Already saved
        return JSONResponse({"analysis_id": analysis_id})

    pending = _pending[analysis_id]
    project_name = pending.get("project_name", "")

    # Create DB row
    aid = create_analysis(project_name=project_name, user_id=pending["user_id"])

    # Move files to DB
    for file_type, file_info in pending["files"].items():
        # Rename upload dir from temp_id to real analysis_id
        old_dir = settings.upload_dir / analysis_id
        new_dir = settings.upload_dir / str(aid)
        if old_dir.exists() and not new_dir.exists():
            old_dir.rename(new_dir)

        # Update file path
        new_path = str(Path(file_info["file_path"]).parent.parent / str(aid) / Path(file_info["file_path"]).name)
        add_analysis_file(aid, file_type, file_info["filename"], new_path, file_info["file_size"])

    # Clean up pending
    del _pending[analysis_id]

    return JSONResponse({"analysis_id": aid})


@router.get("/review/{analysis_id}", response_class=HTMLResponse)
async def review(request: Request, analysis_id: str):
    """Review parsed data before processing."""
    from app.parsers import MagnaskraParser, VerklysingParser, BCCatalogParser

    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    # If pending, save to DB first
    if analysis_id in _pending:
        pending = _pending[analysis_id]
        project_name = pending.get("project_name", "")
        aid = create_analysis(project_name=project_name, user_id=pending["user_id"])

        old_dir = settings.upload_dir / analysis_id
        new_dir = settings.upload_dir / str(aid)
        if old_dir.exists() and not new_dir.exists():
            old_dir.rename(new_dir)

        for file_type, file_info in pending["files"].items():
            new_path = str(Path(file_info["file_path"]).parent.parent / str(aid) / Path(file_info["file_path"]).name)
            add_analysis_file(aid, file_type, file_info["filename"], new_path, file_info["file_size"])

        del _pending[analysis_id]
        return RedirectResponse(f"/review/{aid}", status_code=302)

    try:
        aid = int(analysis_id)
    except ValueError:
        return RedirectResponse("/analyses", status_code=302)

    analysis = get_analysis(aid)
    if not analysis:
        return RedirectResponse("/analyses", status_code=302)

    files = {f["file_type"]: f for f in get_analysis_files(aid)}
    parse_results = {}

    if "magnaskra" in files:
        parser = MagnaskraParser()
        items = parser.parse(files["magnaskra"]["file_path"])
        line_items = [i for i in items if not i.is_header]
        sheets = sorted(set(i.sheet_name for i in items))
        parse_results["magnaskra"] = {
            "total": len(items),
            "line_items": len(line_items),
            "sheets": sheets,
            "sample": [i.model_dump() for i in line_items[:15]],
        }

    if "verklysing" in files:
        parser = VerklysingParser()
        sections = parser.parse(files["verklysing"]["file_path"])
        parse_results["verklysing"] = {
            "total": len(sections),
            "sections": [{"nr": s.section_nr, "title": s.title, "pages": s.page_numbers}
                        for s in sections],
        }

    if "bc_catalog" in files:
        parser = BCCatalogParser()
        products = parser.parse(files["bc_catalog"]["file_path"])
        vara_count = sum(1 for p in products if p.product_type.value == "Vara")
        parse_results["bc_catalog"] = {
            "total": len(products),
            "vara": vara_count,
            "sample": [p.model_dump() for p in products[:15]],
        }

    return templates.TemplateResponse("review.html", {
        "request": request,
        "user": user,
        "analysis_id": aid,
        "analysis": analysis,
        "files": files,
        "parse_results": parse_results,
    })
