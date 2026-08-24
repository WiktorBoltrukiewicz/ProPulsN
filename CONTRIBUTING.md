# Contributing to ProPulsN

Thanks for considering it. This is a small, single-maintainer project, so the
process is lightweight — but a few architectural decisions are deliberate and
PRs are expected to respect them. Read "Ground rules" below before starting
anything non-trivial.

## Getting started

```bash
git clone https://github.com/WiktorBoltrukiewicz/ProPulsN.git
cd ProPulsN
pip install -r requirements.txt -r backend/requirements.txt
```

Run the web app with auto-reload while you work on it:

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

Then open <http://localhost:8000>. The CLI (`python main.py`,
`plot_results.py`) needs no server and is useful for isolating a solver change
from the web layer.

## Running the tests

```bash
python -m pytest tests/ -v
```

248 tests, about 40 seconds. **Do not shrink `n_grid` to speed a test up** — a
coarse grid makes the solver fail with `Bad domain` near the sonic point; cap
`max_iterations` instead, which is what the existing tests do.

## Testing the Docker image

If you have Docker with a working Linux engine (Docker Desktop + WSL2 on
Windows, or Docker Engine directly on Linux/macOS):

```bash
docker compose build
docker compose up -d
python scripts/smoke_container.py
docker compose down
```

The smoke test proves the things a unit test can't reach: the frontend is
actually in the image, the WebSocket greets and streams, a real solve spawns
`python main.py` as a subprocess *inside* the container, and the bind-mounted
`results/` directory is writable. CI runs the same script on every push
(`.github/workflows/tests.yml`, job `docker`) and is the final word — if your
local Docker setup differs from CI's, trust CI.

## Ground rules

These aren't style preferences; they're decisions written up with their
reasoning in `CLAUDE.md`, and a PR that quietly works around one will likely
be asked to change. Read the relevant section there before touching:

- **One WebSocket, one REST route.** Every interactive feature — loading and
  saving params, running a simulation, listing results, exporting DXF,
  previewing geometry — goes through the single `/ws` endpoint as a JSON
  message. The only exception is `GET /files/{name}` for downloading a
  finished result. A new feature almost never needs a new REST route; if you
  think yours does, open an issue first and make the case. See "Architecture
  decision" in `CLAUDE.md`.
- **No default parameter values, anywhere.** The solver, the CLI and the web
  UI all refuse to run with a value they invented. If you add a parameter the
  solver reads, add it to `param_schema.REQUIRED_PARAMS` too, or
  `tests/test_required_params.py` fails on purpose. See "Required Parameters"
  in `CLAUDE.md`.
- **The two-stage solver pipeline is load-bearing.** `core/main.py` (Stage 1)
  and `core/convergence_loop.py` (Stage 2) implement specific numerics ported
  from the original MATLAB code. `tests/test_geometry_parametric.py` pins the
  default nozzle contour against a pre-refactor oracle to ~1e-17 — if you
  touch geometry, gas properties, or the ODE systems, that test is the one
  that has to keep passing, not just "the suite is green."
- **Bump `PROTOCOL_VERSION` (`backend/app/version.py`) whenever a WebSocket
  message shape changes** in a way that would make an older frontend
  misrender. Bump `APP_VERSION` on release. `tests/test_version_handshake.py`
  checks the two don't drift from what the frontend expects.
- **Sections in the frontend don't call each other directly.** They
  communicate only through events on the shared WebSocket connection (e.g.
  `simulation_complete` triggers the Results section to refresh itself). See
  "Section communication" in `CLAUDE.md`.

## Where things live

| Area | Path |
|---|---|
| Solver core (geometry, ODEs, gas properties, convergence loop) | `backend/app/core/` |
| WebSocket protocol and message router | `backend/app/ws/` |
| The one REST route (file downloads) | `backend/app/api/downloads.py` |
| Services (simulation runner, results, DXF) | `backend/app/services/` |
| Frontend (plain HTML/CSS/JS, no build step) | `frontend/` |
| Tests | `tests/` |
| Example parameter files | `params/` |

`CLAUDE.md` has the full picture, including the parameter-file format, the
inlet-condition (`N0`) shooting method, and the reasoning behind what's
deliberately *not* in the app yet (see "Public hosting" — the project targets
self-hosting, not a public multi-tenant deployment, and that's on purpose for
now).

## Submitting a PR

- Keep `python -m pytest tests/ -v` green, and run the Docker smoke test too
  if you touched the Dockerfile, `docker-compose.yml`, or anything the
  container's startup path depends on.
- If your change affects one of the "Ground rules" above, say so in the PR
  description and update the matching part of `CLAUDE.md` in the same PR —
  it's the project's living design log, not just onboarding material.
- Small, focused PRs are easier to review than large ones bundling unrelated
  changes.

## Reporting bugs / requesting features

Open a GitHub issue. For a bug, include the parameter file (or a minimal one
that reproduces it) and, if the solver failed, the console output — the error
messages are usually specific (`Bad domain`, `MissingParameters: ...`) and
save a round trip.
