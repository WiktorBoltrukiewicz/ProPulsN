# ProPulsN

A Python-based rocket engine nozzle flow simulator. ProPulsN calculates compressible gas flow through a de Laval (Rao-bell) nozzle including wall friction effects, producing detailed flow field data suitable for CFD post-processing and Ansys import.

Created by **Wiktor Bołtrukiewicz**.

## Features

- **Two-stage numerical solver** — isentropic ODE (Stage 1) followed by a convergence loop with full friction modelling (Stage 2)
- **Rao-bell nozzle geometry** — 6-segment profile (circular arc + straight + Bézier curve), fully parametric from the injector face to the exit plane
- **Variable gas properties** — γ, Cp, Pr, and molar mass specified as 3-node profiles (chamber / throat / exit), PCHIP-interpolated along the nozzle axis
- **Browser interface** — one self-hosted web app with four sections: Geometry, Parameters, Simulation, Results. No build step, no bundler, no separate frontend server
- **Live convergence monitor** — per-variable L1 residual curves streamed over a WebSocket and charted as the solve runs
- **Results export**
  - CSV with full flow field (Mach, pressure, temperature, adiabatic wall temperature, …)
  - DXF nozzle contour for CAD import
  - 3D wall point cloud CSV for Ansys/CFD mesh generation (with optional full or partial revolve)
  - every export downloadable straight from the browser
- **3D preview** — interactive view of the wall point cloud, colour-mapped by any flow property
- **Shareable JSON configs** — one file holds an entire engine; export it, send it, import it back. No values live anywhere but the file

## Requirements

Python 3.10 or newer, plus:

| Package | Minimum version | Needed for |
|---------|----------------|------------|
| fastapi | 0.115 | the web app |
| uvicorn[standard] | 0.30 | the web app |
| numpy   | 2.0 | solver |
| scipy   | 1.10 | solver |
| ezdxf   | 1.1 | DXF export |
| matplotlib | 3.7 | the standalone CLI's plots only |

There are two requirements files, deliberately: `backend/requirements.txt` is
everything the web app needs, and the root `requirements.txt` adds matplotlib
for the CLI.

## Installation

```bash
git clone https://github.com/WiktorBoltrukiewicz/ProPulsN.git
cd ProPulsN
pip install -r backend/requirements.txt
```

## Running

### Web app (recommended)

One process serves the API and the interface:

```bash
cd backend
uvicorn app.main:app --port 8000
```

Then open <http://localhost:8000>.

### CLI / batch mode

```bash
python main.py                        # interactive — select a parameter file
python main.py params/default.json   # load a specific file
# there is no --default: every value comes from a parameter file
```

## Parameter Files

A configuration is one JSON file in `params/`. It is the unit you save, and the
unit you share — everything the solver needs is in it, and nothing the solver
needs is anywhere else. The included files are:

| File | Description |
|------|-------------|
| `default.json` | Baseline rocket engine (6 MPa chamber pressure) |
| `Liquid_Ethanol_N2O.json` | Ethanol / nitrous oxide propellant combination |

Each file has a `_meta` header and sections for initial conditions, nozzle
geometry, gas properties, cooling channels, wall material, coolant properties
and solver settings. Every entry carries its own unit and description, which is
what the web UI renders:

```json
"nozzle_geometry": {
    "R_throat": { "value": 0.01878, "unit": "m", "description": "Throat radius" }
}
```

Gas properties are given at three stations, as `gamma_chamber`, `gamma_throat`
and `gamma_exit` (and the same for `Cpcg`, `Prcg` and
`combustion_molar_mass`). All three are required; ProPulsN interpolates
between them with a PCHIP spline.

**There are no built-in defaults.** Every value the solver reads comes from the
file, so a file missing a parameter is refused before anything is computed, and
the UI shows an empty field marked `required` for each gap. This is deliberate:
a value you can see in the interface is the value that gets solved.

### Saving and sharing a configuration

Four buttons, and the only thing separating them is **where the file goes**:

| Button | Where it puts the config |
|---|---|
| **Save** | over the file you opened, in the app's `params/` library |
| **Save as…** | a new file in that library. Will not overwrite an existing one |
| **Download** | a file on the computer the *browser* is running on |
| **Upload…** | takes a file from that computer and adds it to the library |

The library is what the file picker lists and what a run reads, so a config has
to be in it to be used. Download and Upload move configs between that library
and you — which is the same folder while you run ProPulsN on your own
machine, and two different machines the moment you host it somewhere else.

All four capture the same thing: the file you opened, plus any unsaved edits,
plus the nozzle from the Geometry section and the settings from the Simulation
section. A downloaded config is byte-for-byte what Save would have written, so
one you send to someone else is a config they can open and run unchanged.

Upload will not overwrite a config you already have under that name, and a
`.json` that is not an ProPulsN config is refused rather than half-loaded.

### `_meta`

The header travels with the file, and the Parameters section makes it editable:

| Field | Owner |
|---|---|
| `name`, `description`, `author`, `version` | **You.** Shown to whoever you send the file to; never filled in automatically. |
| `created`, `modified`, `format` | **ProPulsN.** Stamped on every save. |

`format` is the file-format version. If a config arrives from a newer
ProPulsN than yours, it still loads and the Parameters section says so, so a
missing parameter reads as "this file is from a newer build" rather than as a
mystery.

## Output

Simulation results are written to the `results/` directory as CSV files. Each run produces a file named after the parameter file, numbered so runs do not overwrite each other (e.g. `results/default_results_01.csv`).

Column names follow SI units throughout:

| Column | Description |
|--------|-------------|
| `x_m` | Axial position [m] |
| `r_m` | Nozzle wall radius [m] |
| `M` | Mach number [-] |
| `P_Pa` | Static pressure [Pa] |
| `T_K` | Static temperature [K] |
| `T_aw_K` | Adiabatic wall temperature [K] |

The Results tab allows interactive plotting of any two columns and exports the wall geometry as a 3D point cloud for CFD use.

## Author

ProPulsN is written and maintained by **Wiktor Bołtrukiewicz**.

## License

Licensed under the **Apache License 2.0**.

You may use, modify and redistribute ProPulsN, including commercially, provided
you keep the copyright notice, state your changes, and pass on the [LICENSE]
(LICENSE) and [NOTICE](NOTICE) files. The licence also grants an explicit
patent licence from contributors to users.

Copyright 2026 Wiktor Bołtrukiewicz.
