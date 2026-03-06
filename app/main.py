from fastapi import FastAPI

app = FastAPI(title="voro-index-guard", version="0.1.0")

@app.get("/health")
def health():
    return {"status": "ok", "service": "voro-index-guard"}
