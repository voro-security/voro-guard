from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from voro_mcp.config import settings
from voro_mcp.routes.hydration import router as hydration_router
from voro_mcp.routes.index import router as index_router
from voro_mcp.routes.learning import router as learning_router
from voro_mcp.routes.query import router as query_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    poller = None
    if settings.poller_enabled:
        from voro_mcp.core.poller import RepoPoller
        poller = RepoPoller(Path(settings.poller_config))
        await poller.start()
    yield
    if poller:
        poller.stop()


app = FastAPI(title="voro-guard", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "service": "voro-guard"}


app.include_router(hydration_router)
app.include_router(index_router)
app.include_router(learning_router)
app.include_router(query_router)
