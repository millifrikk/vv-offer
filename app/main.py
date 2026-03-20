"""VV Offer Tool - FastAPI application."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db.models import init_tables
from app.db.seed import seed_users
from app.routes import auth, upload, process, download, history, admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    settings.ensure_dirs()
    init_tables()
    seed_users()
    yield
    # Shutdown (nothing to do)


app = FastAPI(title=settings.app_title, lifespan=lifespan)

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Register routes
app.include_router(auth.router)
app.include_router(upload.router)
app.include_router(process.router)
app.include_router(download.router)
app.include_router(history.router)
app.include_router(admin.router)


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.app_title}
