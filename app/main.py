"""FastAPI application entrypoint.

This is the minimal backend application for Phase 1.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run startup and shutdown logic around the app lifecycle."""

    print("Argus Backend Starting...")
    print("API Server:     http://127.0.0.1:8000")
    yield


app = FastAPI(
    title="Argus Backend",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/")
def root() -> dict[str, str]:
    """Basic health check for the backend."""

    return {"status": "ok", "message": "Argus backend is running"}
