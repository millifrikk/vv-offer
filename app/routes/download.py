"""Download routes - serve generated files."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, RedirectResponse

from app.auth import get_current_user
from app.db.models import get_analysis

router = APIRouter()


@router.get("/download/{analysis_id}")
async def download_excel(request: Request, analysis_id: int):
    """Download the enriched Excel file."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    analysis = get_analysis(analysis_id)
    if not analysis or not analysis.get("output_path"):
        return RedirectResponse("/analyses", status_code=302)

    path = Path(analysis["output_path"])
    if not path.exists():
        return {"error": "Output file not found"}

    project_name = analysis.get("project_name", "").strip()
    filename = f"{project_name}_tilbod.xlsx" if project_name else "enriched_tilbod.xlsx"
    # Sanitize filename
    filename = "".join(c for c in filename if c.isalnum() or c in "._- ")

    return FileResponse(
        path=str(path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
