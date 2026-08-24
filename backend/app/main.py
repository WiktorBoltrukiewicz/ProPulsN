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
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from .api.downloads import router as downloads_router
from .core import REPO_ROOT
from .ws.connection import router as ws_router

FRONTEND_DIR = os.path.join(REPO_ROOT, "frontend")


class RevalidatingStaticFiles(StaticFiles):
    """Static files the browser must re-check on every load.

    The page is a set of ES modules. Chrome will happily reuse a cached module
    across an ordinary reload without asking the server, which means an
    upgraded ProPulsN can serve new Python behind a page still running the old
    JavaScript — the mirror image of the stale-backend trap in version.py, and
    with none of its warning. `no-cache` does not mean "do not store": the
    browser keeps the file and revalidates it, so an unchanged file still costs
    one 304 and no transfer.

    This matters most in a container, where upgrading means pulling a new image
    and reloading a tab that has been open for a week.
    """

    def file_response(self, *args, **kwargs) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response

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
    RevalidatingStaticFiles(directory=FRONTEND_DIR, html=True),
    name="frontend",
)
