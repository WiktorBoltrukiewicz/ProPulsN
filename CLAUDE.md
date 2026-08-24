# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ProPulsN is a Python-based rocket engine nozzle flow simulator. It performs compressible flow analysis through a Rao-bell nozzle with optional friction effects, producing results for CFD/Ansys integration. Originally ported from MATLAB.

**Named ProPulsN since 2026-08-24**, renamed from OpenEngine ahead of the
open-source release. The rename is complete in the code, the UI, the shipped
parameter files and the docs. The public repository is
`github.com/WiktorBoltrukiewicz/ProPulsN`; the **local checkout directory is
still `OpenPropulsN`**, which is cosmetic and affects nothing.

**Two versions, and they mean different things.** `version.py` holds both:
`APP_VERSION` (currently `0.7.0`) is the release the user sees, rendered next
to the wordmark in the sidebar — bump it on release. `PROTOCOL_VERSION` is the
WS contract, bumped whenever a change would make an older page misrender. The
sidebar version arrives in `server_info` rather than being written into
`index.html`, for the same reason the handshake exists at all: a stale backend
serves fresh static files, so a hardcoded version would be the one thing on
screen guaranteed to look right while everything behind it was wrong.
`tests/test_version_handshake.py` checks the page has a slot for it and does
not hardcode one.

Authorship is credited in the sidebar's lower-left corner, in
`<meta name="author">`, and in the README — pinned by
`tests/test_version_handshake.py::TestBranding` so a redesign cannot quietly
drop it.

**Migration:** the project moved from a PySide6 desktop GUI to a self-hosted web app, so it runs in a browser with a modern UI (built from Google Stitch mockups) and can be shared as an open-source, easily self-hostable tool. The physics/solver core did not change — only how a user interacts with it. The desktop GUI was deleted in Phase 6; the standalone CLI (`main.py`, `plot_results.py`) stays.

**Architecture decision — one WebSocket, plus exactly one REST route.** The central interaction is a *live streaming* simulation console (subprocess stdout, live L1 residual updates), which fits a single persistent WebSocket rather than a set of discrete REST endpoints. So loading/saving params, running a simulation, listing results, exporting DXF and previewing geometry all go through one `/ws` endpoint using JSON messages.

The **one** exception, agreed 2026-08-24, is `GET /files/{name}` — handing a finished export to the browser. It qualifies under the carve-out that was always in this note: non-realtime, cacheable, and something a browser already knows how to do. Streaming megabytes of `.prof` as base64 inside a JSON frame to trigger a save would be strictly worse. It matters most in a container, where a server-side path like `/app/results/nozzle_01.dxf` is useless to the user. See `backend/app/api/downloads.py`.

**That remains the only REST route.** Anything else still needs asking first.

Asked and answered once, 2026-08-24: **config download/upload needed no
route.** Download sends the config over the WebSocket (`export_params`) and
gets stamped JSON text back; upload reads the file with `FileReader` and goes
through the existing `save_params_as`. See "The file as a shareable unit".

## Migration Plan

- [x] **Phase 0 — generalise the geometry.** The convergent chamber is now
  parametric (`R_chamber`, `L_chamber`, `R_conv_arc`) and `N0` is solved for
  from the geometry instead of being a hand-tuned constant. Any physically
  buildable engine now solves. See "Inlet condition `N0`" below.
- [x] **Phase 1 — Extract core logic.** Move `geometry.py`, `ode_functions.py`, `gas_properties.py`, `compute_qf.py`, `parameters.py`, `param_loader.py`, `convergence_loop.py`, `results_exporter.py`, `plotting.py`, `export_dxf.py`, and `main.py`'s Stage 1 logic into `backend/app/core/`. This is a relocation, not a rewrite — behavior must stay bit-for-bit identical. The standalone CLI (`main.py`) keeps working unchanged.
- [x] **Phase 2 — FastAPI skeleton.** `backend/app/main.py` creates the app, mounts `frontend/` as static files, and includes the WebSocket router. No auth, no database — single-user local/self-hosted tool for now.
- [x] **Phase 3 — WebSocket protocol.** Define the message types (see "WebSocket Protocol" below) as Pydantic models in `backend/app/ws/protocol.py`.
- [x] **Phase 4 — Simulation streaming.** Port the subprocess-streaming mechanism from `SimulationTab`/`_SimWorker` (see below) to an asyncio task that pushes lines and parsed convergence data over the WebSocket.
- [x] **Phase 5 — Frontend.** Turn the Google Stitch HTML/CSS exports into `frontend/`, with one section per old tab (Geometry, Parameters, Simulation, Results) and a small JS WebSocket client.
- [x] **Phase 6 — Feature parity pass.** Every old tab feature confirmed covered by the WS flow (see "Phase 6 parity result" below), then the Qt GUI and its 113 tests deleted and `PySide6` dropped.
- [x] **Phase 7 — Dockerize for self-hosting.** One `Dockerfile`, one container running `uvicorn app.main:app`, serving the API, the static frontend and `/files/` on one port. **Target is self-hosting, not a public deployment** — see "Public hosting" below for why those are different jobs.
- [ ] **Phase 8 — Docs + OSS polish.** README quickstart, LICENSE, CONTRIBUTING, docker-compose.yml.

---

## Current Status (last updated 2026-08-24)

Phases 0–6 are done and verified. The web app runs and is usable end to end:
load a parameter file, design a nozzle, stream a solve, read results, export
DXF / Fluent `.prof`, and download any of them. 242 tests pass in ~35 s
(`python -m pytest tests/ -v`).

Since 2026-08-24 the program carries **no default parameter values**: every
number the solver reads comes from the parameter file, as edited in the UI, and
an incomplete file is refused before anything is computed. See "Required
Parameters" below.

Also 2026-08-24: a config is now a **shareable unit**. Parameters has Download
/ Upload… alongside Save, `_meta` is editable and stamped on save, and
`_meta.format` lets a file say which ProPulsN wrote it. See "The file as a
shareable unit".

**Phase 7 is done** — `Dockerfile`, `docker-compose.yml`, `.dockerignore`, a
README quickstart and `tests/test_container_layout.py`. **Next up: Phase 8**
(docs/OSS polish). See "Next Steps".

The application is English throughout — parameter files, UI, code comments.
Polish parameter files still load through a shim (see "Parameter System").

Phase 0 generalised the geometry: the nozzle is parametric from the injector
face to the exit plane, and the solver picks its own inlet condition. A sweep
of 20 geometries (throat 10–25 mm, chamber 35–70 mm, chamber length 90–250 mm,
expansion ratio 2.5–25) solves 19; the one failure is an unrelated grid
resolution limit (see "Remaining limitation" below).

The repository is now under git. The commit before Phase 6 holds the complete
PySide6 GUI, so anything overlooked can be recovered from history rather than
rewritten.

### Phase 6 parity result

Every control of every old tab, checked against the web app. Verified live over
the WebSocket, not just by reading code.

| Old desktop feature | Web equivalent |
|---|---|
| **Geometry** — Refresh Geometry | `Rebuild profile` |
| Export to .dxf (native save dialog) | `Export DXF` → always into `results/` |
| Geometry Summary box | `Dimensions` stat list (plus contraction ratio and inlet Mach) |
| 2D profile plot | inline SVG |
| **Parameters** — Config combo, Refresh | `#param-file`, `Refresh` |
| Save / Save As… | `Save` / `Save as…` |
| Gas Properties 3-node group box | `Gas properties` card (`_chamber`/`_throat`/`_exit` suffixes) |
| **Simulation** — Run / Stop / Clear Console | `Run simulation` / `Stop` / `Clear` |
| Solver mode combo (convergence / fixed) | `#sim-mode` |
| n_grid, max_iterations, tol, relax | `#sim-ngrid`, `#sim-maxiter`, `#sim-tol`, `#sim-relax` |
| Console Output | streamed `log_line` events |
| Convergence Monitor | live L1 chart from `convergence_update` |
| **Results** — File combo, Load, Refresh | `#res-file`, `Load`, `Refresh` |
| Plot Creator: X/Y axis, Plot, Clear | `#res-x`, `#res-y`, `Draw`, `Clear` |
| Results Table sub-tab | `Flow field` sub-view (adds pagination the desktop app lacked) |
| Wall Export: Select All / Deselect All | `All` / `None` |
| Export Fluent Profile (.prof) | `Export Fluent profile` |
| Revolve: enable, start/end angle, planes | `#wall-revolve`, `#wall-start`, `#wall-end`, `#wall-planes` |
| Color by, Preview 3D | `#wall-color`, `Preview 3D` |
| Fluent operating pressure | `#wall-op` |
| **Settings** — DXF n_grid, mirror, spline, labels | Geometry section's `DXF export` panel |
| Interface scale (BASE_FONT) | dropped on purpose — browser zoom |
| **About** dialog | sidebar branding |

Two gaps were found and closed:

- **"Open Results Folder"** (three buttons in the desktop app) has no browser
  equivalent. Instead `results_list`, `dxf_export_ready` and
  `wall_export_ready` now carry the absolute server `directory`, and the
  Results section shows it. That is the closest honest substitute and needs no
  REST endpoint.
- **Plot "Clear"** was missing; added.

One capability genuinely did not survive: the matplotlib **navigation toolbar**
(pan, zoom, cursor readout, save-as-PNG) on the plots. The SVG charts are
static. Nothing depends on it — it is listed under Next Steps as optional.

Two things the web app does *better* than what it replaced: the old Geometry
tab was **hardcoded** (`constants.DEFAULT_R_THROAT`, with a label promising a
"geometry builder in a future update"), and the results table now paginates.


### Section ownership (settled — don't re-litigate)

Each value has exactly one owner; the others read it through events.

| Value | Owned by | Notes |
|---|---|---|
| `R_throat`, `E_r`, `R_chamber`, `L_chamber`, `R_conv_arc` | **Geometry (02)** | The whole contour. Hidden from the Parameters cards; seeded from a newly loaded file, then never overwritten by Parameters edits. A file predating Phase 0 has no chamber entries — `applyTo()` creates them in `nozzle_geometry` rather than dropping the user's edit. |
| `n_grid`, `max_iterations`, `tol`, `relax`, `solver_mode` | **Simulation (03)** | The whole solver box, hidden from the Parameters cards and sent as solver overrides. `applyTo()` writes them back so Save persists what the box shows. Geometry has its own separate *preview* `n_grid`. |
| everything else | **Parameters (01)** | Rendered from the file's own nested structure, plus an empty flagged field for any required key the file lacks. |

Wiring: Geometry dispatches `openengine:geometry-changed`; Simulation renders
it as the read-only "Nozzle" card; `app.js` overlays Geometry's values onto the
raw params in `ui.currentParams()`, which is what both **Run** and **Save** use.
Sections never call into each other.

---

## Inlet condition `N0` (Phase 0 — read before touching it)

`N0` is the initial M² at the chamber inlet. It used to be a constant in
`params/*.json`, hand-tuned for `R_throat = 0.01878`; any other throat made the
flow miss sonic and Stage 2 died with `ValueError: Bad domain`. It is now
solved for at run time, in two steps.

**Step 1 — isentropic value (`core/isentropic.py`).** For a choked nozzle
`A* = A_throat`, so the contraction ratio fixes the subsonic inlet Mach
exactly:

```
A/A* = (1/M)·[ (2/(γ+1))·(1 + (γ-1)/2·M²) ]^((γ+1)/(2(γ-1)))
```

inverted with `brentq` on `M ∈ (0, 1)`. Areas come from the **grid**
(`A_grid[0]`, `min(A_grid)`), not from `π·r²`, so the value matches the
discretised geometry the ODE actually integrates.

**Step 2 — shoot for the choking threshold (`core/inlet_condition.py`).** The
isentropic value alone is *not enough*, and this is the subtle part. `A_func`
is a PCHIP through `A_grid` while `dA_func` is a separate PCHIP through
`np.gradient(A_grid)`; near the throat the two disagree badly (measured: 10×
at the area minimum). The consequence is that the exact isentropic value sits
just **below** the threshold at which the discretised integration reaches
N = 1 — the nozzle never chokes. Measured gap: the threshold is 0.25%–5%
above the isentropic value, always above, because discretisation error can
only make choking harder.

So the isentropic value is used as a guaranteed **lower bracket**, and the
threshold is found by bisection on the predicate "does the integration reach
N = 1?". `x_sonic(N0)` is monotone (higher `N0` → sonic further upstream), so
the threshold is sharp and well defined. A small margin (`N0_margin`, default
2%) is added on top, because right at the threshold the solution is very
sensitive.

Shooting runs on the frictionless Stage 1 ODE. Friction in subsonic flow acts
like extra contraction (Fanno), so the threshold *with* friction is always
lower — a value found this way is safe for Stage 2. Cost is ~0.35 s, once per
run.

Why not solve the true frictional eigenvalue? Strictly, with friction the
sonic point sits slightly downstream of the area minimum and `N0` is the
solution of a boundary value problem. `run_stage2` never threads that saddle
point though — it detects M = 1 with a terminal event (`event_N1`) and
restarts supersonically at `N = 1 + delta`. It only needs to *reach* sonic
near the throat, which the threshold-plus-margin value does. For the default
engine it puts the sonic point 2.2 mm before the throat, versus 4.0 mm for the
old hand-tuned 0.01535 — so it is also more accurate than what it replaced.

### Overriding it

| Key (`warunki_poczatkowe`) | Default | Meaning |
|---|---|---|
| `N0_auto` | `true` | Solve for `N0`. Set to `0`/`false` to use the pinned `N0`. |
| `N0_margin` | `0.02` | Safety margin over the choking threshold. |
| `N0` | 0.01535 | Only used when `N0_auto` is false. |

A pinned `N0` below the isentropic value logs a warning — that flow cannot
choke.

## Remaining limitation: Part B grid resolution at large expansion ratios

`E_r = 25` at `n_grid = 100` still fails with `Bad domain` just downstream of
the sonic restart; `n_grid = 200` solves it. The nozzle is much longer at high
`E_r`, so a fixed point count leaves the throat region under-resolved and Part
B's restart at `N = 1 + delta` cannot clear the singularity. This is the
pre-existing coarse-grid fragility already noted under "Testing notes", not an
`N0` problem — no value of `N0` fixes it, and more grid points do.

If this is worth fixing, the fix is in `run_stage2`, not in the inlet
condition: either concentrate grid points near the throat instead of spacing
them by arc length, or make `delta` adaptive to the local grid spacing.

## Next Steps (pick up here)

Ordered. Item 1 is the only one that changes what the tool can do; the rest is
migration cleanup.

1. **Name results after the parameter file.** A run writes its params to
   `params/_run_<token>.json`, and `results_exporter` derives the output name
   from that file, so results land as `_run_9rdasrbi_results_01.csv` — you
   cannot tell runs apart. Carry the original filename through
   `run_simulation` (add an optional `params_name` to the command) and use it
   for the temp file stem, e.g. `default__run_<token>.json` →
   `default__run_<token>_results_01.csv`. The old desktop app had the same
   wart, so this is an improvement, not a regression fix.
2. **Phase 8 — docs/OSS polish.** CONTRIBUTING, and a pass over the README
   now that it is the front page of a public repository. Phase 7 landed the
   container (see "Phase 7 — the container"); the download endpoint went first
   on purpose, because a container that can only report server-side paths
   cannot hand the user their own output.

   **The image is never built on the developer's machine.** Docker Desktop is
   installed there but WSL2 is not, so the Linux engine cannot start. The
   `docker` job in `.github/workflows/tests.yml` is therefore the only thing
   that builds it — and it does more than build: it starts the container,
   solves an engine through the WebSocket and downloads the result, because
   spawning `python main.py` as a subprocess is the part most likely to work
   locally and fail in an image. If you change the Dockerfile, watch that job;
   there is no local signal.
3. *Optional:* give the Results plot pan/zoom and a cursor readout. The old
   matplotlib canvas had a navigation toolbar; the SVG chart does not. Nothing
   depends on it, but it is the one genuine capability the web app lost.
4. *Optional, only if high-`E_r` engines matter:* fix the Part B grid
   resolution limit described above.

## Public hosting (deferred — read before attempting it)

Considered on 2026-08-24 and **deliberately deferred**. The user wants a
publicly reachable instance eventually; the conclusion was that Docker for
self-hosting and a public deployment are different jobs, and only the first
belongs to Phase 7.

### Compute is not the obstacle

Measured on the default engine, on the developer's Windows machine:

| | |
|---|---|
| Idle server (uvicorn + FastAPI + numpy/scipy) | 103 MB RSS |
| One full 100-iteration solve | ~2.9 s, 67 MB peak, one core |
| 10-iteration solve | 1.2 s |
| Output per run | 15 KB CSV |

A 512 MB instance idles at ~110 MB and absorbs roughly 4–5 concurrent solves.
This app is genuinely cheap to run; **no free tier would struggle with the
arithmetic.**

### What actually blocks it: the app is single-tenant by design

Every item below is true of the code as it stands, and each is correct for a
local single-user tool:

1. **`params/` is shared and writable.** `services/params.py:save()` defaults
   to `overwrite=True`, so any visitor can overwrite `default.json` for
   everyone, or fill the disk via `save_params_as`.
2. **`GET /files/{name}` serves any result to anyone.** Visitor A downloads
   visitor B's designs. The "no auth is fine" argument in
   `api/downloads.py` is explicitly conditioned on single-user localhost —
   public hosting is the condition that voids it.
3. **`settings.json` is global.** One visitor's DXF options become everyone's.
4. **Solver inputs are unbounded.** `SolverOverrides.n_grid` and
   `max_iterations` are `Optional[int]` with no `ge`/`le`. At 2.9 s per 100
   iterations, `max_iterations: 100000` pins a core for ~48 minutes. That is
   a one-line denial of service.
5. **Concurrency is capped per connection, not globally.** The guard reads
   "A simulation is already running on this connection", so 30 tabs are 30
   subprocesses (~2 GB) and an OOM kill.
6. **Most free tiers have ephemeral disks**, so results — and therefore the
   download links — vanish on redeploy or idle-restart.

### If it is ever picked up

Roughly a phase of work, in rising order of effort:

- Bound `n_grid` and `max_iterations` with `Field(ge=…, le=…)` — minutes, and
  worth doing regardless of hosting.
- Per-session results directory keyed by a connection token, and scope
  `/files/` to it.
- Disable or session-scope `save_params`, `save_params_as`, `save_settings`.
- A global `asyncio.Semaphore` plus a queue around solves.
- Per-IP connection cap.

A cheaper **read-only demo** — hard caps, all saving disabled, ephemeral
per-session results — is perhaps a third of that and enough for a public "try
it" link.

Hosting shortlist, given the app needs persistent WebSockets, subprocess
spawning and a writable directory: Fly.io (scale-to-zero, good WS, a few
dollars a month), Hetzner (~€4/mo for a real VPS), Oracle Cloud Always Free
(most generous, fussiest signup), Render free (sleeps, ephemeral disk).
Vercel, Netlify and PythonAnywhere's free tier are ruled out — no persistent
WebSockets and no subprocesses. Verify pricing before committing; it moves.

### Testing notes for whoever picks this up

- `python -m pytest tests/ -v` — 242 passing, ~35 s.
- **Do not shrink `n_grid` to speed a test up.** A coarse grid (e.g. 30) makes
  the solver fail with `Bad domain` near the sonic point. Cap
  `max_iterations` instead; that is what the existing tests do.
- Phase 0's tests: `test_geometry_parametric.py` (the default contour must stay
  bit-for-bit identical — it keeps a copy of the pre-Phase-0 implementation as
  an oracle), `test_isentropic.py` (area–Mach inversion),
  `test_inlet_condition.py` (the choking threshold and the shooting), and
  `test_phase0_regression.py` (end-to-end CLI solves of engines that used to
  fail, including the `R_throat = 0.020` case).
- `tests/test_ws_protocol.py::TestRunsOnSelectorEventLoop` exists because
  uvicorn runs a **SelectorEventLoop** on Windows, which cannot spawn
  subprocesses. `TestClient` uses a ProactorEventLoop, so the ordinary WS
  tests passed while the real server could not solve at all. The runner
  therefore uses blocking `subprocess.Popen` + `asyncio.to_thread`, never
  `asyncio.create_subprocess_exec`. Keep it that way.
- If a fix "doesn't take", check for a **second uvicorn bound to port 8000** —
  Windows allows the double bind and the stale process keeps answering. Static
  files are re-read from disk on every request, so the page looks current
  while the Python behind it is old. `netstat -ano | grep :8000`, then kill
  every PID listed.

  **The page now detects this itself.** The backend greets every connection
  with `server_info` carrying `PROTOCOL_VERSION`, and the page replies with
  `client_hello`. A mismatch — or no greeting at all, which is what a backend
  predating the handshake does — puts a red banner across the top of the app.
  The version lives in `backend/app/version.py` and `frontend/js/app.js`;
  `tests/test_version_handshake.py` fails if the two drift apart. Bump it
  whenever a protocol change would make an older page misrender.

## Phase 7 — the container

One image, one process, one port. `uvicorn` serves the WebSocket, the static
frontend and `GET /files/` on 8000, and spawns `python main.py <config>` per
solve exactly as it does outside a container.

**The layout is load-bearing.** `core/__init__.py` finds `REPO_ROOT` by walking
four directories up from itself, so `backend/`, `frontend/`, `params/` and
`results/` must sit side by side under `/app`. Move any of them and the image
still builds, still starts, and serves an empty page while writing results
where nobody mounted anything. `tests/test_container_layout.py` pins that
shape, along with the COPY sources, the compose mounts, and the flags below —
none of it needs Docker to run. The image itself is built and exercised by the
`docker` job in CI (`scripts/smoke_container.py`), which is the only place it
is ever built: see "Next Steps".

| Decision | Why |
|---|---|
| `python:3.12-slim` | numpy/scipy wheels dominate the image; the base is noise next to them |
| Only `backend/requirements.txt` | matplotlib is the largest thing the web app can do without — it draws its own charts |
| `PYTHONUNBUFFERED=1` | **Load-bearing, not hygiene.** The solver's stdout is streamed to the browser line by line; a buffered pipe stalls the live convergence chart until the run ends |
| `--host 0.0.0.0` | without it the published port reaches nothing |
| no `--reload` | it watches the filesystem and doubles the process count for no benefit in an image |
| `USER propulsn` (UID 1000) | not root, for the usual reasons. A bind mount brings its own ownership, so Linux hosts whose user is not 1000 need `--user "$(id -u):$(id -g)"` — the README says so |
| `127.0.0.1:8000:8000` in compose | the app has no auth and no bound on solver inputs. Publishing it by default would hand a stranger a one-line denial of service. See "Public hosting" |
| bind mounts, not named volumes | the point is that configs and results are ordinary files next to the checkout, reachable from the host. A named volume survives `docker rm` but hides the CSVs |

**What the container does not keep.** `settings.json` (the DXF export options)
lives inside the image and resets when the container is recreated; it is one
small file and mounting it would break `docker compose up` on a fresh clone,
which is the worse trade. The CLI's matplotlib plots are not installed.

### Static files revalidate now

Found while driving the UI in a browser: Chrome reuses a cached ES module
across an ordinary reload without asking the server. New Python can therefore
serve a page still running last week's JavaScript — the mirror image of the
stale-backend trap `version.py` exists for, with none of its warning, and the
`PROTOCOL_VERSION` handshake only catches it when the protocol itself changed.

A container makes this the normal case: upgrading means pulling an image and
reloading a tab that has been open for days. `RevalidatingStaticFiles` in
`backend/app/main.py` sends `Cache-Control: no-cache` on every static file.
That is not "do not store" — the browser keeps the file and revalidates it, so
an unchanged module costs one 304 and no transfer.

### Not done here, on purpose

The image is for **self-hosting**. It has no authentication, no per-IP limits
and no bound on `n_grid` or `max_iterations`, because the app has none. Every
item under "Public hosting" still applies and still needs doing before this is
reachable from anywhere you do not control.

---

## Running the Project

```bash
# Backend (serves the API AND the frontend — one process)
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
# → open http://localhost:8000 in a browser

# CLI/batch mode — unchanged, independent of the web app
python main.py                        # interactive — select a parameter file
python main.py params/default.json    # load a specific file
# there is no --default: the solver carries no built-in values

# Run tests
python -m pytest tests/ -v
```

No build step for the frontend (plain HTML/CSS/JS, no bundler). No separate frontend server; the only REST route is `GET /files/{name}` for downloads.

Two dependency files, deliberately: `backend/requirements.txt` is what the web app (and the Phase 7 container) needs — `fastapi`, `uvicorn[standard]`, `numpy`, `scipy`, `ezdxf`. The root `requirements.txt` adds `matplotlib` for the standalone CLI plots. `PySide6` and `Pillow` were dropped in Phase 6 with the desktop GUI.

## Architecture

### Two-Stage Solver Pipeline (do not modify)

The core simulation runs two sequential stages:

1. **Stage 1 — Isentropic ODE** (`backend/app/core/main.py`): Solves simplified ODEs (no friction, no heat transfer) using `scipy.integrate.solve_ivp` (RK45). State vector is `Y = [N, P, T]` (Mach², pressure, temperature). Provides an initial solution for Stage 2.
2. **Stage 2 — Convergence Loop** (`backend/app/core/convergence_loop.py`): Iteratively solves full ODEs with friction. Each iteration recomputes the friction profile (`dFdx`) from the previous solution and updates until `Y` converges within tolerance. Supports two modes: convergence-based and fixed-iteration count.

### Key Modules

**Core solver (relocated as-is to `backend/app/core/`):**

| Module | Role |
|--------|------|
| `geometry.py` | Builds Rao-bell nozzle profile (6 segments), PCHIP-interpolated `A(x)` and `dA/dx`. Fully parametric since Phase 0 |
| `ode_functions.py` | Two ODE systems: simplified (`my_nozzle_ode`) and full (`my_nozzle_ode_full2`) with friction/heat; sonic event detection |
| `gas_properties.py` | PCHIP-interpolated gas property profiles (γ, Cp, Pr, molar mass) across 3 nodes: chamber → throat → exit |
| `compute_qf.py` | Friction profile: Darcy-Weisbach equation, Reynolds number, velocity |
| `parameters.py` | Computes T_aw (adiabatic wall temperature) and Mach number at each grid point |
| `param_loader.py` | JSON parameter file loading, interactive selection, saving |
| `param_schema.py` | **New.** The English key vocabulary plus the Polish-file shim, and the list of parameters the solver does not read |
| `convergence_loop.py` | Outer convergence iteration with L1 residual tracking (Ansys-style per-variable curves) |
| `results_exporter.py` | CSV export of geometry, gas state, convergence history |
| `plotting.py` | Final result plots (gas parameters, adiabatic wall temperature) — used for standalone CLI plots only; web results plotting happens in the frontend |
| `export_dxf.py` | Nozzle profile → DXF export for SolidWorks/Ansys Discovery |
| `main.py` | Stage 1 entry point |
| `isentropic.py` | **New (Phase 0).** Area–Mach relation and its inversion; gives the isentropic inlet Mach from the contraction ratio |
| `inlet_condition.py` | **New (Phase 0).** Shoots for the `N0` that actually chokes the discretised nozzle, bracketed from below by the isentropic value |

**Deleted in Phase 6 (PySide6 GUI):**

`ui.py`, `app.py`, `settings_window.py`, `tabs/`, `constants.py`,
`setup_launcher.py`, `ProPulsN.pyw`, and 113 Qt-bound tests. Recoverable from
the commit before Phase 6 if something turns out to be missing.

**New (backend web layer):**

| Module | Role |
|--------|------|
| `backend/app/main.py` | FastAPI app: mounts `frontend/` as static files, includes the WS router and the download route |
| `backend/app/api/downloads.py` | The only REST route: `GET /files/{name}`, serving `.csv`/`.dxf`/`.prof` out of `results/` |
| `backend/app/version.py` | `PROTOCOL_VERSION` for the stale-backend handshake |
| `backend/app/ws/connection.py` | The single `/ws` endpoint — receives JSON commands, dispatches to services, sends JSON events back |
| `backend/app/ws/protocol.py` | Pydantic models for every WS message type (commands in, events out) |
| `backend/app/services/simulation_runner.py` | Replaces `_SimWorker`: spawns `python main.py <temp.json>` as a subprocess, streams stdout as WS events, parses convergence lines with the same regex logic as the old `_CONV_RE` |
| `backend/app/services/results.py` | Lists/reads `results/*.csv`, computes the 3D wall-export point cloud |
| `backend/app/services/dxf.py` | Thin wrapper around `export_dxf.py` |

**New (frontend, from Google Stitch mockups):**

| Path | Role |
|------|------|
| `frontend/index.html` + section markup | One section per old tab: Geometry, Parameters, Simulation, Results |
| `frontend/js/ws-client.js` | Thin WebSocket wrapper: send a command object, dispatch incoming events by `type` |
| `frontend/js/*.js` | One small module per section, mirroring the old tab's responsibilities |
| `frontend/css/theme.css` | Catppuccin Mocha palette as CSS custom properties (see Theme below) |

---

## Critical Implementation Details

*(Unchanged from the desktop version — this is the physics/numerics core and must not drift during migration.)*

### ODE State Vector

`Y = [N, P, T]` where:
- `N` = **M²** (Mach number squared, not Mach number itself). `M = sqrt(N)`.
- `P` = static pressure [Pa]
- `T` = static temperature [K]

The simplified ODE (`my_nozzle_ode`) uses only geometry; the full ODE (`my_nozzle_ode_full2`) adds friction (`dFdx`) and heat transfer (`dQdx`, currently zero — no regenerative cooling).

### Sonic Singularity Handling

The denominator `(1 - N)` in the ODE goes to zero at M=1 (N=1). Stage 2 (`run_stage2` in `convergence_loop.py`) splits each iteration into two sub-integrations:
- **Part A**: inlet → sonic point, detected by `event_N1` (terminal event when N crosses 1 from below)
- **Part B**: starts at `N = 1 + delta` (supersonic) with adaptive delta `delta = clip(0.02 + 0.5 * |dA/A|, 0.02, 0.3)` to skip past the singularity

### Convergence Metrics

Two norm families:
- **L∞** (`conv_stop`): max relative change per element — used as the stopping criterion
- **L1** (`r_n`, `r_p`, `r_t`, `r_f`): mean relative change per variable — used for the live convergence chart (this is what streams over the WebSocket now, instead of into a Qt plot widget)

Adaptive under-relaxation:
- `conv_stop > 1e-2` → relax = 0.2
- `conv_stop > 1e-4` → relax = 0.4
- otherwise → relax = 0.6

Blend: `YSol_blended = relax * YSol_new + (1 - relax) * YSol_prev`

### Friction Model (`compute_qf.py`)

Uses Darcy-Weisbach: `dFdx = f * V² / (2 * D)`

Friction factor:
- Laminar (Re < 2300): `f = 64 / Re`
- Turbulent: `f = 0.25 / (log10(ε/(3.7·D) + 5.74/Re^0.9))²` (Swamee-Jain approximation)

### Gas Properties: all three nodes, always

`gas_properties.py` reads `gamma_chamber`, `gamma_throat`, `gamma_exit` and the
same triple for `Cpcg`, `Prcg` and `combustion_molar_mass`. All three are
required; there is no bare-`gamma` shorthand and no default value any more.

That shorthand used to exist (a single `gamma` meant "constant along the
nozzle", and a missing node was copied from its neighbour). It went with the
rest of the fallbacks — a node the file does not carry is now reported by name
and rendered as an empty field, rather than being invented. A file written in
the old style opens fine; it just asks for the two missing nodes before it will
solve.

### Nozzle Geometry (`geometry.py`)

Six segments concatenated and reparametrized by arc length to `n_grid` equally-spaced points:
1. Chamber: constant radius `R_chamber` from `x = -L_chamber` to `Xc`
2. Large-radius arc (convergent): radius `R_conv_arc`
3. Straight line (convergent)
4. Pre-throat arc: radius `1.5 * R_throat`
5. Post-throat arc: radius `0.382 * R_throat`
6. Quadratic Bézier (divergent, Rao bell profile): from throat tangent at 22° to exit tangent at 12°

Exit radius = `sqrt(E_r) * R_throat`. Exit length = `0.8 * ((sqrt(E_r) - 1) * R_throat) / tan(15°)`.

Every segment is parametric (Phase 0). Defaults — `R_chamber = 0.04205`,
`L_chamber = 0.14262`, `R_conv_arc = 0.07265` — reproduce the original MATLAB
contour to ~1e-17, guarded by `tests/test_geometry_parametric.py`, which keeps
a copy of the pre-Phase-0 implementation as an oracle.

**The convergent arc's centre offset is derived, not a parameter.** It is
`R_chamber - R_conv_arc` (which is exactly the old `-0.0306`), and that is what
keeps the arc tangent to the chamber wall. Do not turn it back into an input —
an independent value produces a discontinuous contour.

Three combinations are rejected up front with a specific message rather than
being handed to the solver:

| Condition | Why |
|---|---|
| `R_chamber <= R_throat` | Nothing to converge into |
| `X3 > X1` | The convergent arc ends downstream of the pre-throat arc — the contour folds back on itself and `A(x)` is no longer single-valued. Happens when `R_conv_arc` is too large for the chamber, e.g. `R_throat = 0.030` with the default chamber. |
| `Xc <= -L_chamber` | The arc starts upstream of the inlet — the chamber is too short |


---

## Parameter System

### JSON File Format

Files live in `params/`. Keys and descriptions are English throughout:

```json
{
  "_meta": { "name": "...", "description": "...", "author": "",
             "created": "2026-03-08", "version": "1.0" },
  "section_name": {
    "_description": "section description",
    "param_key": {
      "value": 0.01878,
      "unit": "m",
      "description": "Throat radius"
    }
  }
}
```

Sections: `initial_conditions`, `nozzle_geometry`, `cooling_channels`,
`wall_properties`, `gas_properties`, `coolant_fuel`, `solver`.

`load_params()` returns a flat dict `{param_key: value}`. The nested raw
structure is needed for the Parameters section (frontend cards) and for saving.

### The file as a shareable unit (`_meta`, format version, download/upload)

A parameter file is the thing users pass around, so it has to identify itself
and survive the trip between two copies of ProPulsN.

**`_meta` has two owners.** `name`, `description`, `author` and `version`
belong to the user and are editable in the Parameters section's "File info"
card; nothing fills them in automatically, least of all `author` — the app has
no idea who the user is. `created`, `modified` and `format` belong to the
program and are stamped by `param_schema.stamp_meta()` on every save.

**`_meta.format` is the file-format version** (`param_schema.FORMAT_VERSION`,
currently 1; `FORMAT_HISTORY` records what each one means). It is *not*
`_meta.version`, which stays the user's own revision tag. Bump `FORMAT_VERSION`
when a change would make an older build misread a file — a renamed section, a
new required parameter, a changed entry layout. Adding an optional key does not
need a bump.

A file declaring a *newer* format still loads: `format_warnings()` returns a
sentence, `params_loaded` carries it as `warnings`, and the Parameters section
shows it above the cards. That way an unfamiliar gap reads as "this came from a
newer ProPulsN" instead of as a mystery. An *older* or unmarked file is not
nagged about — saving migrates it silently, which is the same rule the
Polish→English shim follows.

**Four buttons, one distinction: where the file lands.** Save and Save as…
write into the app's `params/` library — what the picker lists and what a run
reads. Download and Upload… move a config between that library and the machine
the browser is on. They are deliberately *not* called Import/Export: the format
is identical, so those words would imply a conversion that does not happen.

While the app runs on localhost the two destinations are the same disk, which
is why this looks redundant. It stops being redundant the moment the server is
not the user's own computer — which is the point of Phase 7.

**Neither adds a REST route.** This was the question the architecture note asks
to be asked, and the answer is no:

- **Upload** reads the file with `FileReader`, parses it, and sends it through
  the existing `save_params_as`. An upload *is* a save: `overwrite=False` means
  it can never clobber an existing config, and `looks_like_params()` refuses an
  unrelated `.json` before it reaches `params/`.
- **Download** sends the assembled config over the WebSocket (`export_params`)
  and gets back stamped JSON text, which the page hands to the browser as a
  Blob. A config is ~10 KB, so the round trip is free.

`GET /files/{name}` therefore remains the only REST route, and it still serves
`results/` only.

**Why Download goes to the server at all.** It could build the JSON in the page
— it holds the whole config. It must not: that would be a *second* place that
writes `_meta`, and the stamping rule would then live in both Python and JS.
Instead `params_service._prepare()` vets, migrates and stamps, and both
`save()` and `export()` call it, so a downloaded file is byte-identical to a
saved one. `tests/test_param_file_format.py::TestDownloadMatchesSave` pins
that; it fails the moment the two paths diverge.

The first version of Download did build the file client-side, and was worse in
exactly the two ways that predicts: it skipped the invalid-input guard (so it
would hand over a config quietly disagreeing with the screen, because
`collect()` keeps the old value for a field it cannot parse) and it skipped
`stamp_meta()` (so `modified` was stale). Both are gone.

**`_prepare()` normalises before either destination.** Loading normalises too,
but an upload reaches the service without having been loaded first, so a shared
legacy Polish file would otherwise be written back with a mix of both
vocabularies. `sanitize_name()` also strips leading `._-`, which is what stops
an upload from landing in the runner's `_run_*` namespace.

### Legacy Polish files (compatibility shim)

The application used to use Polish keys (`wartosc`, `jednostka`, `opis`,
`geometria_dyszy`, ...). `backend/app/core/param_schema.py` holds the mapping
and `normalise_raw()` rewrites an old file on the way in, so anything written
before the switch still loads. Saving always writes English, so a file
migrates the first time it is saved.

| Old | New |
|---|---|
| `wartosc` | `value` |
| `jednostka` | `unit` |
| `opis` / `_opis` | `description` / `_description` |
| `nazwa`, `autor`, `data_utworzenia`, `wersja` | `name`, `author`, `created`, `version` |
| `warunki_poczatkowe` | `initial_conditions` |
| `geometria_dyszy` | `nozzle_geometry` |
| `kanaly_chlodzace` | `cooling_channels` |
| `wlasciwosci_scianki` | `wall_properties` |
| `wlasciwosci_gazu` | `gas_properties` |
| `chlodziwo_fuel` | `coolant_fuel` |

Unknown sections and keys pass through untouched — a file may carry things
this program does not know about, and dropping them on save would be worse
than leaving them alone.

**Read parameter entries through `has_value()` / the `value` key, never
`wartosc`.** Everything downstream of `load_params()` sees the English shape.

### Inactive parameters (regenerative cooling)

The solver models gas flow with wall friction only. The parameter files still
carry the regenerative-cooling inputs from the earlier version of the program,
but nothing reads them. `param_schema.INACTIVE_PARAMS` lists them, and
`params_loaded` ships that map to the frontend, which renders those fields
dimmed, read-only and tagged `not used`, with one explanatory note per card.

They are **greyed, not hidden** — the values still round-trip through save, so
they survive until cooling lands.

| Section | Inactive | Note |
|---|---|---|
| `cooling_channels` | all 10 | whole card dimmed |
| `wall_properties` | 4 of 5 (6 of 7 in `Liquid_Ethanol_N2O.json`) | `epsilon` stays live — the friction model uses it |
| `gas_properties` | `sonvel`, `Ru_bartz` | superseded: computed internally |
| `coolant_fuel` | all 4 | whole card dimmed |

`tests/test_param_schema.py::TestInactiveParams::test_matches_what_the_solver_actually_reads`
traces a real run and compares the keys the solver touched against this list,
in both directions. **When regenerative cooling lands, that test fails until
the list is updated** — which is the point.

### Required Parameters (there are no defaults)

**Nothing in the program supplies a value.** The code used to carry a fallback
next to every read — `p('tol', 1e-6)` — so the same number lived in the JSON,
in the Python and in the HTML `value=` attribute. They had already drifted:
`default.json` said `relax = 0.3` while the code and the page said `0.5`, so
the web app and `python main.py --default` solved the same engine differently.
Those fallbacks are gone.

`param_schema.REQUIRED_PARAMS` is the single list, and it holds **names, units
and labels only — never values**:

| Section | Required keys |
|---|---|
| `nozzle_geometry` | `R_throat`, `E_r`, `R_chamber`, `L_chamber`, `R_conv_arc`, `n_grid` |
| `initial_conditions` | `P0`, `T0`, `N0_auto`, `N0_margin` |
| `gas_properties` | `gamma_*`, `Cpcg_*`, `Prcg_*`, `combustion_molar_mass_*` (all three nodes each), `eta`, `c_star` |
| `wall_properties` | `epsilon` |
| `solver` | `max_iterations`, `tol`, `relax`, `solver_mode`, `mdot_gas` |

`N0` is the one conditional entry (`CONDITIONAL_PARAMS`): the solver shoots for
it, and only reads the file's value when `N0_auto` is off.

For the actual values, read `params/default.json` — it is the only place they
exist.

**How a gap behaves.** `require_params()` runs in `core/main.py` before any
geometry is built and raises `MissingParameters`, naming **every** gap at once
rather than stopping at the first. In the browser the same check runs in
`SimulationRun.missing_parameters()` before a subprocess is spawned, so the
user gets an error event instead of a traceback in the console. The page keeps
it from getting that far: `params_loaded` carries `required` (the table) and
`missing` (what this file omits), the Parameters section renders an empty
flagged field for each gap, and Run refuses while any required field is blank.

Adding a parameter the solver reads means adding it here too, or
`tests/test_required_params.py::TestMatchesWhatTheSolverReads` fails — the
mirror of the `INACTIVE_PARAMS` guard.

---

## WebSocket Protocol

One endpoint, `/ws`. Every message is JSON with a `type` field used to dispatch it. Commands flow client → server; events flow server → client.

### Simulation streaming

The old `SimulationTab` did **not** run the solver in-process. That design is kept, only the transport changes:
1. Frontend sends `{"type": "run_simulation", "params": {...}}`
2. Backend serializes params to a temp JSON file in `params/` (prefix `_run_`)
3. Backend spawns `python main.py <temp.json>` as a subprocess and reads its stdout line-by-line via an asyncio task (replaces `_SimWorker(QThread)`)
4. Each stdout line is sent as `{"type": "log_line", "text": "..."}`
5. Lines matching the convergence regex (same pattern as the old `_CONV_RE`) additionally send `{"type": "convergence_update", "r_n": ..., "r_p": ..., "r_t": ..., "r_f": ...}` — this drives the live chart in the Simulation section
6. On completion: `{"type": "simulation_complete", "results_file": "..."}`

### Other commands (illustrative — finalize exact shape in Phase 3)

| Command (client → server) | Event(s) back (server → client) |
|---|---|
| `list_params` | `params_list` |
| `load_params` | `params_loaded` (flat + raw nested + the inactive map + `required`/`missing` + `warnings`) |
| `save_params` | `params_saved` or `error` |
| `save_params_as` | `params_saved` or `error` (refuses to overwrite; also the upload path) |
| `export_params` | `params_exported` (stamped JSON text for the browser to save; writes nothing) |
| `run_simulation` | `log_line`* , `convergence_update`* , `simulation_complete` |
| `list_results` | `results_list` |
| `get_results_table` | `results_table` |
| `export_wall` | `wall_export_ready` |
| `export_dxf` | `dxf_export_ready` (carries `download_url`) |
| `preview_geometry` | `geometry_preview` (points for the nozzle profile canvas) |

### Section communication

Old: `SimulationTab` called `self._app.results_tab.refresh_file_list()` directly after a run.
New: backend sends `simulation_complete`; the frontend's Results section listens for that event and re-sends `list_results` — sections communicate only through events on the shared WS connection, never by calling into each other directly.

### Theme

Google Stitch palette, as CSS custom properties in `frontend/css/theme.css` instead of a hardcoded Qt stylesheet:
- Neutrals: page `#0B0E11`, panels `#111417`, console/wells `#07090B`, hover `#1D2023`
- Borders: `#262B31`, strong `#41474F`
- Text: `#E1E2E7`, muted `#C1C7D1`, faint `#8B919A`
- Primary `#005288`, secondary `#00D1FF`, tertiary `#FFB800`, error `#FFB4AB`

**Primary is fill-only.** `#005288` sits at ~2.4:1 against the background, so it may only fill surfaces (primary buttons, the active nav row). Anything that has to be legible on a dark surface uses the light tint `#9CCAFF` (`--accent`) — the same primary / on-primary-container split the Stitch mockups use. Every other foreground/background pair in the app clears WCAG AA.

Console text is neutral (`--fg-muted`), with colour reserved for warning and error lines.

### Settings File (`settings.json`)

At repo root. Keeps `dxf_n_grid` (int), `dxf_mirror` (bool), `dxf_spline` (bool), `dxf_labels` (bool). Drop `base_font` (Qt font-scaling concept doesn't map to the browser — use normal browser zoom / a CSS root font-size variable if this is still wanted). Never stores simulation parameters — those stay in `params/*.json`. Read/written via WS commands (`get_settings` / `save_settings`), not a REST endpoint.

---

## File Downloads (`GET /files/{name}`)

The only REST route in the app. Added 2026-08-24 because Phase 7 puts the
server in a container, where telling the user a path inside the image is
useless.

- **Serves out of `results/` only**, through the same `safe_results_path()`
  guard the WebSocket file commands use. Verified against raw, un-normalised
  requests — `../`, `..%2f`, `..%252f`, `%2e%2e`, `....//` and backslash
  variants are all refused, and nothing outside `results/` leaks.
- **Extension whitelist** (`SERVABLE_TYPES`): `.csv`, `.dxf`, `.prof`. An
  unrelated file that happens to sit in `results/` stays unreachable. Adding a
  new output format means adding it here too.
- **GET only.** A POST returns 405; this route must never accept an upload.
- `Content-Disposition: attachment`, so a CSV saves instead of rendering as a
  wall of text in the tab.
- **No auth**, matching the rest of the app — a single-user self-hosted tool.
  Anyone who can reach the WebSocket can already read and write these files,
  so the route grants nothing new. That reasoning is what makes it safe, and
  it stops holding if the app ever gains multiple users or is exposed beyond
  localhost. Revisit it before widening the route to another directory.

Clients should use the `download_url` the server sends rather than building
the path themselves — `download_url()` in `api/downloads.py` owns the route
shape. It arrives on `dxf_export_ready`, `wall_export_ready`, and as a
`download_urls` map on `results_list`.

Covered by `tests/test_downloads.py`; most of it is about what the route
refuses, not what it serves.

## Results CSV Format

Saved to `results/{params_name}_results_{NN:02d}.csv`. Comment lines start with `#` (metadata). Data starts at the first non-comment line (column headers).

Load with: `pd.read_csv('results/....csv', comment='#')`

Columns exported (in order):
`x_m`, `r_m`, `A_m2`, `gamma`, `Cpcg_J_kgK`, `Prcg_gas`, `molar_mass_kg_mol`, `Rs_J_kgK`, `M`, `N_M2`, `P_Pa`, `T_K`, `T_aw_K`, `eta_Pa_s`

## DXF Export (`export_dxf.py`)

Called from `backend/app/services/dxf.py` in response to an `export_dxf` WS command. Units: millimeters. DXF layers:
- `UPPER_PROFILE` — upper contour (+r), white, 0.50 mm lineweight
- `LOWER_PROFILE` — lower contour (−r, mirror), cyan
- `SYMMETRY_AXIS` — center line, red, CENTER linetype
- `POINTS` — throat/inlet/exit markers, yellow
- `DIMENSIONS` — text labels, green

Options (n_grid, mirror, spline vs polyline, labels) come from the frontend's Geometry section via the `export_dxf` command payload.

## Wall Export (3D point cloud for CFD)

Revolves the 2D nozzle profile around the X axis (engine axis) to generate a 3D point cloud for CFD boundary conditions:
- `X = x_m`, `Y = r_m * cos(θ)`, `Z = r_m * sin(θ)`
- Default: 0°–360°, 36 planes (every 10°)
- Exports CSV with columns: `X, Y, Z, [selected properties]`
- 3D preview: computed in `backend/app/services/results.py`, rendered in the frontend (e.g. with a JS 3D library) instead of matplotlib's `mpl_toolkits.mplot3d`

---

## Data Flow

```
params/*.json
    → param_loader.py  (flat dict: key→value)
    → geometry.py  +  gas_properties.py
    → main.py (Stage 1 ODE, isentropic)
    → convergence_loop.py (Stage 2, iterative with friction)
    → parameters.py (T_aw, M at each point)
    → results_exporter.py → results/*.csv
    → export_dxf.py → results/*.dxf
```

Web path:
```
Browser (frontend/, static files served by FastAPI)
    ↔ WebSocket /ws
        → backend/app/ws/connection.py   (message router)
        → backend/app/services/simulation_runner.py  (spawns subprocess: python main.py _run_*.json)
        → backend/app/services/results.py   (reads results/*.csv, wall export)
        → backend/app/services/dxf.py       (export_dxf.py)
```

---

## Test Suite

Tests live in `tests/`, use `unittest`. Run with `python -m pytest tests/ -v`.

| File | What it tests | Status |
|------|--------------|--------|
| `test_geometry_parametric.py` | Phase 0: default contour unchanged vs. a pre-Phase-0 oracle; chamber args reshape the convergent; invalid contours rejected | Keep |
| `test_isentropic.py` | Phase 0: area–Mach relation and its inversion on both branches | Keep |
| `test_inlet_condition.py` | Phase 0: the choking threshold is sharp and monotone; shooting yields a usable `N0` for every geometry | Keep |
| `test_phase0_regression.py` | Phase 0 end-to-end: engines that used to die with `Bad domain` now solve via the real CLI | Keep |
| `test_param_schema.py` | The Polish→English shim, and a drift guard tying `INACTIVE_PARAMS` to what a real run actually reads | Keep |
| `test_param_file_format.py` | The file as a shareable unit: `_meta` stamping, the format version and its warning, upload shape-checking, the legacy migration on save, and that a downloaded config is byte-identical to a saved one | Keep |
| `test_container_layout.py` | Phase 7: the layout, COPY sources, compose mounts and image flags the container depends on, plus that static files revalidate | Keep |
| `test_required_params.py` | `REQUIRED_PARAMS` holds no values; the shipped files are complete; an incomplete file is refused by the CLI and over the WS; a drift guard tying the table to what a real run reads | Keep |
| `test_ws_protocol.py`, `test_ws_protocol_schema.py`, `test_ws_commands.py` | WS command/event contract, including the SelectorEventLoop subprocess guard | Keep |
| `test_results_service.py` | Results listing/reading and the wall-export point cloud | Keep |

All twelve remaining files are keepers. Phase 6 retired 113 tests across nine
files: `test_qt_update1-6.py` (Qt app startup / tab structure),
`test_font_scaling.py` (no browser equivalent), `test_launcher.py` (Windows
shortcut setup) and `test_wall_export.py`.

`test_wall_export.py` was checked before retiring, not assumed: every one of
its nine non-GUI maths tests has a counterpart in `test_results_service.py`,
which additionally covers gauge-pressure conversion, `T_aw_K` winning the
temperature slot, CSV comment-preamble parsing and path-traversal safety. Its
other 15 tests drove Qt widgets and died with them.