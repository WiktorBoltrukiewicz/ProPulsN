"""
main.py — the FastAPI application.

Serves both the WebSocket API and the static frontend from a single process
on a single port:

    cd backend
    uvicorn app.main:app --reload --port 8000
    # -> http://localhost:8000

There is deliberately no REST API. Every client-server interaction goes over
the one `/ws` WebSocket endpoint (see CLAUDE.md).
"""

import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .core import REPO_ROOT
from .ws.connection import router as ws_router

FRONTEND_DIR = os.path.join(REPO_ROOT, "frontend")

app = FastAPI(
    title="OpenEngine",
    description="Rocket engine nozzle flow simulator",
)

# The WebSocket route must be registered before the catch-all static mount,
# otherwise StaticFiles at "/" would swallow "/ws".
app.include_router(ws_router)

# html=True serves index.html at "/" and falls back to it for unknown paths.
app.mount(
    "/",
    StaticFiles(directory=FRONTEND_DIR, html=True),
    name="frontend",
)
