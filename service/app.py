"""FastAPI entrypoint for DocFlow service."""
from fastapi import FastAPI

from .handlers import events_router, http_router, profiles_router

app = FastAPI(title="DocFlow Service", version="0.2.1")


@app.get("/health")
def health() -> dict:
    return {"ok": True}


app.include_router(http_router)
app.include_router(events_router)
app.include_router(profiles_router)
