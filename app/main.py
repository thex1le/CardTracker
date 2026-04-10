from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.db import Base, engine
from app.core.logging import setup_logging
from app.api.routes.players import router as players_router
from app.api.routes.feed import router as feed_router
from app.api.routes.watchlist import router as watchlist_router
from app.api.routes.alerts import router as alerts_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()

    # Import all models so Base.metadata is populated
    import app.models  # noqa: F401
    from app.name_resolution.variants import PlayerSearchVariant  # noqa: F401

    # Create tables on startup (dev convenience; use alembic in production)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield


app = FastAPI(title="CardEdge", lifespan=lifespan)

# Include routers
app.include_router(players_router)
app.include_router(feed_router)
app.include_router(watchlist_router)
app.include_router(alerts_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "app": "CardEdge"}
