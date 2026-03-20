"""Processing routes - AI cross-referencing pipeline."""

import json
import time
import threading

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import get_current_user
from app.config import settings
from app.db.models import (
    get_analysis,
    get_analysis_files,
    update_analysis,
    complete_analysis,
    fail_analysis,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# In-memory progress tracking (ephemeral, only during processing)
progress_store: dict[int, dict] = {}


def run_pipeline(analysis_id: int):
    """Run the full processing pipeline in a background thread."""
    from app.parsers import MagnaskraParser, VerklysingParser, BCCatalogParser
    from app.engine.section_matcher import SectionMatcher
    from app.engine.bc_matcher import BCMatcher
    from app.engine.gap_analyzer import GapAnalyzer
    from app.engine.ai_client import AIClient
    from app.output.excel_writer import ExcelWriter

    files_list = get_analysis_files(analysis_id)
    files = {f["file_type"]: f for f in files_list}
    t_start = time.time()

    try:
        # Step 1: Parse
        progress_store[analysis_id] = {"step": 1, "label": "Parsing documents...", "percent": 10}

        mag_items = MagnaskraParser().parse(files["magnaskra"]["file_path"])
        verk_sections = VerklysingParser().parse(files["verklysing"]["file_path"])
        bc_products = BCCatalogParser().parse(files["bc_catalog"]["file_path"]) if "bc_catalog" in files else []

        # Step 2: Section matching
        progress_store[analysis_id] = {"step": 2, "label": "Matching sections...", "percent": 25}

        section_matcher = SectionMatcher()
        lagnir_items = [i for i in mag_items if i.sheet_name == "3 Lagnir"]
        enriched_items = section_matcher.match_items(lagnir_items, verk_sections)

        matched_count = sum(
            1 for e in enriched_items
            if e.match_status.value == "matched" and not e.magnaskra_item.is_header
        )

        # Step 3: BC matching
        progress_store[analysis_id] = {"step": 3, "label": "Matching BC products...", "percent": 40}

        ai_client = None
        if bc_products:
            ai_client = AIClient()
            bc_matcher = BCMatcher(ai_client)
            enriched_items = bc_matcher.match_items(enriched_items, bc_products)

        bc_matched = sum(1 for e in enriched_items if e.bc_product is not None)
        progress_store[analysis_id] = {"step": 3, "label": f"BC matches: {bc_matched}", "percent": 65}

        # Step 4: Gap analysis
        progress_store[analysis_id] = {"step": 4, "label": "Analyzing gaps...", "percent": 70}

        gaps = []
        if ai_client:
            gap_analyzer = GapAnalyzer(ai_client)
            gaps = gap_analyzer.analyze(lagnir_items, verk_sections)

        progress_store[analysis_id] = {"step": 4, "label": f"Gaps found: {len(gaps)}", "percent": 90}

        # Step 5: Generate Excel
        progress_store[analysis_id] = {"step": 5, "label": "Generating Excel...", "percent": 95}

        output_dir = settings.output_dir / str(analysis_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "enriched_tilbod.xlsx"

        writer = ExcelWriter()
        writer.write(enriched_items, gaps, str(output_path))

        # Done - collect results
        elapsed = time.time() - t_start
        line_items = [e for e in enriched_items if not e.magnaskra_item.is_header]
        high_gaps = sum(1 for g in gaps if g.severity.value == "high")

        api_stats = {
            "api_calls": 0, "cache_hits": 0,
            "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
        }
        if ai_client:
            api_stats = {
                "api_calls": ai_client.api_calls,
                "cache_hits": ai_client.cache_hits,
                "input_tokens": ai_client.total_input_tokens,
                "output_tokens": ai_client.total_output_tokens,
                "cost_usd": round(ai_client.total_cost_usd, 4),
            }

        results = {
            "output_path": str(output_path),
            "total_items": len(line_items),
            "verklysing_matches": matched_count,
            "bc_matches": bc_matched,
            "gaps_total": len(gaps),
            "gaps_high": high_gaps,
            "gaps_medium": sum(1 for g in gaps if g.severity.value == "medium"),
            "gaps_low": sum(1 for g in gaps if g.severity.value == "low"),
            "enriched_items": [e.model_dump() for e in line_items[:50]],
            "all_gaps": [g.model_dump() for g in gaps],
            "elapsed_seconds": round(elapsed, 1),
            "api_stats": api_stats,
        }

        # Persist to DB
        complete_analysis(analysis_id, results)
        progress_store[analysis_id] = {"step": 5, "label": "Complete!", "percent": 100}

    except Exception as e:
        fail_analysis(analysis_id, str(e))
        progress_store[analysis_id] = {"step": 0, "label": f"Error: {str(e)}", "percent": 0}


@router.post("/process/{analysis_id}")
async def start_processing(request: Request, analysis_id: int):
    """Start the processing pipeline in a background thread."""
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    files = get_analysis_files(analysis_id)
    file_types = {f["file_type"] for f in files}

    if "magnaskra" not in file_types or "verklysing" not in file_types:
        return JSONResponse(
            {"error": "Both magnskrá and verklýsing files are required"},
            status_code=400,
        )

    update_analysis(analysis_id, status="processing")
    progress_store[analysis_id] = {"step": 0, "label": "Starting...", "percent": 0}

    thread = threading.Thread(target=run_pipeline, args=(analysis_id,), daemon=True)
    thread.start()

    return JSONResponse({"status": "started"})


@router.get("/progress/{analysis_id}")
async def get_progress(request: Request, analysis_id: int):
    """Poll for processing progress."""
    progress = progress_store.get(analysis_id, {})

    # Check DB status if not in progress store
    if not progress:
        analysis = get_analysis(analysis_id)
        if analysis and analysis["status"] == "done":
            return JSONResponse({"status": "done", "progress": {"step": 5, "label": "Complete!", "percent": 100}})
        elif analysis and analysis["status"] == "error":
            return JSONResponse({"status": "error", "progress": {"step": 0, "label": analysis.get("error_message", "Unknown error"), "percent": 0}})

    status = "processing"
    if progress.get("percent") == 100:
        status = "done"
    elif progress.get("step") == 0 and "Error" in progress.get("label", ""):
        status = "error"

    return JSONResponse({"status": status, "progress": progress})


@router.get("/results/{analysis_id}", response_class=HTMLResponse)
async def results(request: Request, analysis_id: int):
    """Show processing results."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    analysis = get_analysis(analysis_id)
    if not analysis:
        return RedirectResponse("/analyses", status_code=302)

    if analysis["status"] != "done":
        return templates.TemplateResponse("processing.html", {
            "request": request,
            "user": user,
            "analysis_id": analysis_id,
        })

    # Load results from DB
    results_data = json.loads(analysis["results_json"]) if analysis["results_json"] else {}

    return templates.TemplateResponse("results.html", {
        "request": request,
        "user": user,
        "analysis_id": analysis_id,
        "analysis": analysis,
        "results": results_data,
    })
