"""
version.py — the protocol version the backend and the page must agree on.

Why this exists
---------------
On Windows a second uvicorn can bind port 8000 while the first is still
listening, and the stale process keeps answering. Static files are read from
disk on every request, so the page looks up to date while the Python behind it
is old — new fields silently go missing and the UI quietly renders the wrong
thing. That trap has cost real debugging time on this project (see CLAUDE.md
"Testing notes").

The page sends its own version on connect; the server compares and, on a
mismatch, tells the page to show a banner instead of failing silently.

Bump PROTOCOL_VERSION whenever a change to `ws/protocol.py` would make an
older page misrender — a new field the UI depends on, a renamed event, a
changed payload shape. `frontend/js/app.js` carries the matching constant, and
`tests/test_version_handshake.py` fails if the two ever drift apart.
"""

# Bump together with PROTOCOL_VERSION in frontend/js/app.js.
PROTOCOL_VERSION = 4

# What changed, newest first — so a bump is a deliberate, documented act.
PROTOCOL_HISTORY = {
    4: "Export events and results_list carry `download_url` / `download_urls` "
       "for the new GET /files/{name} endpoint.",
    3: "params_loaded carries `inactive` / `inactive_reasons`; results_list, "
       "dxf_export_ready and wall_export_ready carry `directory`.",
    2: "Parameter files use the English vocabulary (value/unit/description).",
    1: "Initial WebSocket protocol (phases 3-5).",
}
