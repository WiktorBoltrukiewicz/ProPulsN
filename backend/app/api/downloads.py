"""
downloads.py — the single REST endpoint, deliberately.

Why this exists at all
----------------------
Every other client-server interaction goes over the one `/ws` WebSocket (see
CLAUDE.md). Handing a finished file to the browser is the exception the
architecture note carves out: it is not realtime, it is cacheable, and a
browser already knows how to save a URL. Pushing megabytes of `.prof` through
base64 in a JSON frame to trigger a save would be strictly worse.

It matters most in a container. Reporting a server-side path is a reasonable
answer when the server is your own machine; `/app/results/nozzle_01.dxf` is
useless to someone running the image.

Scope, kept narrow on purpose
-----------------------------
* GET only, and only out of `results/`.
* Path traversal is refused by `safe_results_path()`, the same guard the
  WebSocket file commands use.
* Only extensions this program actually produces are served, so an unrelated
  file that happens to land in `results/` is not exposed by accident.

There is no auth, matching the rest of the app: this is a single-user,
self-hosted tool. Anyone who can reach the WebSocket can already read and
write these files, so the endpoint grants nothing new — but do not widen it to
another directory without revisiting that reasoning.
"""

import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..services.results import safe_results_path

router = APIRouter(tags=["files"])

#: Extension -> media type. Extending this is the intended way to serve a new
#: output format; everything else in results/ stays unreachable.
SERVABLE_TYPES = {
    ".csv": "text/csv",
    ".dxf": "application/dxf",
    ".prof": "text/plain",
}


@router.get("/files/{filename}")
def download_result_file(filename: str):
    """Return a file from results/ as an attachment."""
    try:
        path = safe_results_path(filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    extension = os.path.splitext(filename)[1].lower()
    if extension not in SERVABLE_TYPES:
        raise HTTPException(
            status_code=404,
            detail=(
                f"{extension or 'That file type'} is not served. "
                f"Available: {', '.join(sorted(SERVABLE_TYPES))}."
            ),
        )

    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=f"No such file: {filename}")

    # `filename=` sets Content-Disposition: attachment, so the browser saves
    # the file instead of rendering a CSV as a wall of text.
    return FileResponse(
        path,
        media_type=SERVABLE_TYPES[extension],
        filename=filename,
    )


def download_url(filename: str) -> str:
    """The URL a client should use for `filename`. One place owns the route."""
    from urllib.parse import quote
    return f"/files/{quote(filename)}"
