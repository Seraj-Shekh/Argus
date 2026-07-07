"""FastAPI application entrypoint.

This is the minimal backend application for Phase 1.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import joblib
from fastapi import FastAPI

from app.api.predictions import router as predictions_router, set_model

MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "fire_risk_model.pkl"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run startup and shutdown logic around the app lifecycle."""

    print("Argus Backend Starting...")
    print("API Server:     http://127.0.0.1:8000")

    if MODEL_PATH.exists():
        set_model(joblib.load(MODEL_PATH))
        print(f"Fire risk model loaded from {MODEL_PATH}")
    else:
        print(f"WARNING: {MODEL_PATH} not found — /predict will return 500 "
              "until the model is trained (python scripts/train_model.py)")

    yield


app = FastAPI(
    title="Argus Backend",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(predictions_router, prefix="/api")


@app.get("/")
def root() -> dict[str, str]:
    """Basic health check for the backend."""

    return {"status": "ok", "message": "Argus backend is running"}
