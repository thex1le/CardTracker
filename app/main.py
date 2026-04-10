from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

from app.database import init_db
from app.api.prospects import router as prospects_router
from app.api.signals import router as signals_router
from app.api.cards import router as cards_router
from app.api.news import router as news_router
from app.api.scores import router as scores_router
from app.api.watchlist import router as watchlist_router

BASE_DIR = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup
    await init_db()
    yield


app = FastAPI(title="CardScout", lifespan=lifespan)

# Mount static files
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Include routers
app.include_router(prospects_router)
app.include_router(signals_router)
app.include_router(cards_router)
app.include_router(news_router)
app.include_router(scores_router)
app.include_router(watchlist_router)


@app.get("/", response_class=HTMLResponse)
async def index():
    template = BASE_DIR / "templates" / "index.html"
    return HTMLResponse(content=template.read_text())


@app.get("/api/health")
async def health():
    return {"status": "ok", "app": "CardScout"}
