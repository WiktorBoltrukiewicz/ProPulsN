# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OpenEngine is a Python-based rocket engine nozzle flow simulator. It performs compressible flow analysis through a Rao-bell nozzle with optional friction effects, producing results for CFD/Ansys integration. Originally ported from MATLAB.

**Migration:** the project moved from a PySide6 desktop GUI to a self-hosted web app, so it runs in a browser with a modern UI (built from Google Stitch mockups) and can be shared as an open-source, easily self-hostable tool. The physics/solver core did not change — only how a user interacts with it. The desktop GUI was deleted in Phase 6; the standalone CLI (`main.py`, `plot_results.py`) stays.

**Architecture decision — one WebSocket, plus exactly one REST route.** The central interaction is a *live streaming* simulation console (subprocess stdout, live L1 residual updates), which fits a single persistent WebSocket rather than a set of discrete REST endpoints. So loading/saving params, running a simulation, listing results, exporting DXF and previewing geometry all go through one `/ws` endpoint using JSON messages.

The **one** exception, agreed 2026-08-24, is `GET /files/{name}` — handing a finished export to the browser. It qualifies under the carve-out that was always in this note: non-realtime, cacheable, and something a browser already knows how to do. Streaming megabytes of `.prof` as base64 inside a JSON frame to trigger a save would be strictly worse. It matters most in a container, where a server-side path like `/app/results/nozzle_01.dxf` is useless to the user. See `backend/app/api/downloads.py`.

**That remains the only REST route.** Anything else still needs asking first.

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
- [ ] **Phase 7 — Dockerize.** One `Dockerfile`, one container running `uvicorn app.main:app`, serving both the API and the static frontend on one port.
- [ ] **Phase 8 — Docs + OSS polish.** README quickstart, LICENSE, CONTRIBUTING, docker-compose.yml.

---

## Current Status (last updated 2026-08-23)

Phases 0–6 are done and verified. The web app runs and is usable end to end:
load a parameter file, design a nozzle, stream a solve, read results, export
DXF / Fluent `.prof`, and download any of them. 170 tests pass in ~32 s
(`python -m pytest tests/ -v`).

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
| `n_grid` | **Simulation (03)** | Hidden from Parameters; sent as a solver override. Geometry has its own separate *preview* `n_grid`. |
| everything else | **Parameters (01)** | Rendered from the file's own nested structure. |

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
2. **Phase 7 — Dockerize**, then **Phase 8 — docs/OSS polish**. The download
   endpoint (below) was deliberately landed first, because a container that
   can only report server-side paths cannot hand the user their own output.
3. *Optional:* give the Results plot pan/zoom and a cursor readout. The old
   matplotlib canvas had a navigation toolbar; the SVG chart does not. Nothing
   depends on it, but it is the one genuine capability the web app lost.
4. *Optional, only if high-`E_r` engines matter:* fix the Part B grid
   resolution limit described above.

### Testing notes for whoever picks this up

- `python -m pytest tests/ -v` — 170 passing, ~32 s.
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
python main.py --default              # run with built-in defaults

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
`setup_launcher.py`, `OpenEngine.pyw`, and 113 Qt-bound tests. Recoverable from
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

### Gas Properties: Backward Compatibility

`gas_properties.py` reads per-section values:
1. First tries `gamma_chamber`, `gamma_throat`, `gamma_exit` (new format)
2. Falls back to `gamma` (old format — constant along nozzle)

This matters when adding/modifying parameters: new JSON files should use `_chamber`/`_throat`/`_exit` suffixes for spatially varying properties.

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

### Key Default Parameters

| Key | Default | Unit | Meaning |
|-----|---------|------|---------|
| `R_throat` | 0.01878 | m | Throat radius |
| `E_r` | 5 | — | Expansion ratio A_exit/A_throat |
| `n_grid` | 100 | — | Axial grid points |
| `R_chamber` | 0.04205 | m | Combustion chamber radius |
| `L_chamber` | 0.14262 | m | Chamber inlet distance upstream of the throat |
| `R_conv_arc` | 0.07265 | m | Convergent large-arc radius |
| `N0_auto` | `true` | — | Solve for `N0` from the geometry (see "Inlet condition `N0`") |
| `N0_margin` | 0.02 | — | Safety margin over the choking threshold |
| `N0` | 0.01535 | — | Initial M² at inlet — **only used when `N0_auto` is false** |
| `P0` | 6000000 | Pa | Initial static pressure |
| `T0` | 2941.58 | K | Initial static temperature |
| `eta` | 8.67e-5 | Pa·s | Dynamic viscosity |
| `epsilon` | 5e-5 | m | Surface roughness |
| `max_iterations` | 50 | — | Max convergence iterations |
| `tol` | 1e-6 | — | Convergence tolerance (L∞) |
| `relax` | 0.5 | 0–1 | Under-relaxation factor |
| `solver_mode` | `'convergence'` | — | `'convergence'` or `'fixed'` |

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
| `load_params` | `params_loaded` (flat + raw nested structure + the inactive-parameter map) |
| `save_params` | `params_saved` or `error` |
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
| `test_ws_protocol.py`, `test_ws_protocol_schema.py`, `test_ws_commands.py` | WS command/event contract, including the SelectorEventLoop subprocess guard | Keep |
| `test_results_service.py` | Results listing/reading and the wall-export point cloud | Keep |

All nine remaining files are keepers. Phase 6 retired 113 tests across nine
files: `test_qt_update1-6.py` (Qt app startup / tab structure),
`test_font_scaling.py` (no browser equivalent), `test_launcher.py` (Windows
shortcut setup) and `test_wall_export.py`.

`test_wall_export.py` was checked before retiring, not assumed: every one of
its nine non-GUI maths tests has a counterpart in `test_results_service.py`,
which additionally covers gauge-pressure conversion, `T_aw_K` winning the
temperature slot, CSV comment-preamble parsing and path-traversal safety. Its
other 15 tests drove Qt widgets and died with them.