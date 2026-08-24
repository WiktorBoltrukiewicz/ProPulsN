"""
main.py — the FastAPI application.

Serves both the WebSocket API and the static frontend from a single process
on a single port:

    cd backend
    uvicorn app.main:app --reload --port 8000
    # -> http://localhost:8000

Almost everything goes over the one `/ws` WebSocket endpoint (see CLAUDE.md).
The single exception is `GET /files/{name}`, which hands a finished export to
the browser — see api/downloads.py for why that one earns a REST route.
"""

import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api.downloads import router as downloads_router
from .core import REPO_ROOT
from .ws.connection import router as ws_router

FRONTEND_DIR = os.path.join(REPO_ROOT, "frontend")

app = FastAPI(
    title="ProPulsN",
    description="Rocket engine nozzle flow simulator",
)

# Both routes must be registered before the catch-all static mount, otherwise
# StaticFiles at "/" would swallow "/ws" and "/files/...".
app.include_router(ws_router)
app.include_router(downloads_router)

# html=True serves index.html at "/" and falls back to it for unknown paths.
app.mount(
    "/",
    StaticFiles(directory=FRONTEND_DIR, html=True),
    name="frontend",
)
