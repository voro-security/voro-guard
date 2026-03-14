from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.config import settings
from app.routes.index import router as index_router
from app.routes.learning import router as learning_router
from app.routes.query import router as query_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    poller = None
    if settings.poller_enabled:
        from app.core.poller import RepoPoller
        poller = RepoPoller(Path(settings.poller_config))
        await poller.start()
    yield
    if poller:
        poller.stop()


app = FastAPI(title="voro-guard", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "service": "voro-guard"}


app.include_router(index_router)
app.include_router(learning_router)
app.include_router(query_router)
