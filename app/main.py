from fastapi import FastAPI
from app.routes.index import router as index_router
from app.routes.query import router as query_router

app = FastAPI(title="voro-index-guard", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok", "service": "voro-index-guard"}


app.include_router(index_router)
app.include_router(query_router)
