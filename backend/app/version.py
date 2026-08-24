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

#: The release the user sees, shown next to the wordmark in the sidebar. Sent
#: to the page in `server_info` rather than written into the HTML, so a stale
#: backend cannot leave a fresh-looking version on screen.
#:
#: 0.7.0 — phases 0-6 of the web migration are done; Phase 7 (Docker) is next.
#: This is the version that goes public, so bump it on release, not on commit.
APP_VERSION = "0.7.0"

# Bump together with PROTOCOL_VERSION in frontend/js/app.js.
PROTOCOL_VERSION = 8

# What changed, newest first — so a bump is a deliberate, documented act.
PROTOCOL_HISTORY = {
    8: "server_info carries `app_version`, which the sidebar renders next to "
       "the wordmark.",
    7: "`export_params` / `params_exported`: Download routes through the "
       "server so a downloaded config is stamped exactly like a saved one.",
    6: "params_loaded carries `warnings`; parameter files declare "
       "`_meta.format` (see param_schema.FORMAT_VERSION) and are stamped with "
       "created/modified on save.",
    5: "params_loaded carries `required` / `missing`. Every solver parameter "
       "must come from the file: the code no longer holds default values, and "
       "the page renders an empty field for anything the file omits.",
    4: "Export events and results_list carry `download_url` / `download_urls` "
       "for the new GET /files/{name} endpoint.",
    3: "params_loaded carries `inactive` / `inactive_reasons`; results_list, "
       "dxf_export_ready and wall_export_ready carry `directory`.",
    2: "Parameter files use the English vocabulary (value/unit/description).",
    1: "Initial WebSocket protocol (phases 3-5).",
}
