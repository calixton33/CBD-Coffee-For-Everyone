from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.database import SessionLocal, create_db
from app.routers import audit_log, chains, drinks, menus, shops, users
from app.seed import seed_database

APP_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title=settings.app_name,
    description="Coffee price directory and comparison app for CBD outlets.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "X-Editor-Key"],
)

app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
templates = Jinja2Templates(directory=APP_DIR / "templates")

app.include_router(users.router)
app.include_router(drinks.router)
app.include_router(chains.router)
app.include_router(shops.router)
app.include_router(menus.router)
app.include_router(audit_log.router)


@app.on_event("startup")
def on_startup() -> None:
    create_db()
    if settings.auto_seed and not settings.is_production:
        with SessionLocal() as db:
            seed_database(db)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "app_name": settings.app_name,
        },
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
