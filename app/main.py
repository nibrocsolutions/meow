from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api.admin import router as admin_router
from app.api.routes import router
from app.config import settings
from app.database import Base, engine

STATIC_DIR = Path(__file__).resolve().parent / "static"


class FreshStaticFiles(StaticFiles):
    """Ask the phone to recheck scripts and styles after a rebuild."""

    def file_response(self, full_path, stat_result, scope, status_code=200):
        response = super().file_response(full_path, stat_result, scope, status_code)
        response.headers["Cache-Control"] = "no-cache"
        return response


def index_html() -> str:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    for asset in ("css/app.css", "js/app.js"):
        stamp = int((STATIC_DIR / asset).stat().st_mtime)
        html = html.replace(f"/static/{asset}", f"/static/{asset}?v={stamp}", 1)
    return html


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(router)
app.include_router(admin_router)
app.mount("/static", FreshStaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
@app.get("/admin")
@app.get("/admin/")
def index() -> HTMLResponse:
    return HTMLResponse(index_html(), headers={"Cache-Control": "no-cache"})
