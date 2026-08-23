# OpenEngine

A Python-based rocket engine nozzle flow simulator. OpenEngine calculates compressible gas flow through a de Laval (Rao-bell) nozzle including wall friction effects, producing detailed flow field data suitable for CFD post-processing and Ansys import.

## Features

- **Two-stage numerical solver** — isentropic ODE (Stage 1) followed by a convergence loop with full friction modelling (Stage 2)
- **Rao-bell nozzle geometry** — 6-segment profile (circular arc + straight + Bézier curve) parameterised by throat radius and expansion ratio
- **Variable gas properties** — γ, Cp, Pr, and molar mass specified as 3-node profiles (chamber / throat / exit), PCHIP-interpolated along the nozzle axis
- **Interactive GUI** — PySide6 dark-themed interface with four tabs: Geometry, Parameters, Simulation, Results
- **Live convergence monitor** — per-variable L1 residual curves updated in real time during the solve
- **Results export**
  - CSV with full flow field (Mach, pressure, temperature, adiabatic wall temperature, …)
  - DXF nozzle contour for CAD import
  - 3D wall point cloud CSV for Ansys/CFD mesh generation (with optional full or partial revolve)
- **3D preview** — interactive matplotlib 3D scatter plot of the wall point cloud, colour-mapped by any flow property
- **JSON parameter files** — human-readable configs in `params/`, editable from the GUI or any text editor
- **Desktop launcher** — `setup_launcher.py` creates a Windows shortcut with a custom icon (no console window)

## Requirements

| Package | Minimum version |
|---------|----------------|
| Python  | 3.10 |
| numpy   | 2.0 |
| scipy   | 1.10 |
| matplotlib | 3.7 |
| PySide6 | 6.5 |
| ezdxf   | 1.1 |
| Pillow  | 10.0 (setup_launcher.py only) |

## Installation

```bash
git clone https://github.com/WiktorBoltrukiewicz/OpenEngine.git
cd OpenEngine
pip install -r requirements.txt
```

> **Windows desktop shortcut (optional)**
> ```bash
> python setup_launcher.py
> ```
> This converts `icon.png` to `icon.ico` and creates `OpenEngine.lnk` on your Desktop.
> Requires Pillow (`pip install Pillow`).

## Running

### GUI (recommended)

```bash
python ui.py
```

### CLI / batch mode

```bash
python main.py                        # interactive — select a parameter file
python main.py params/default.json   # load a specific file
python main.py --default             # run with built-in defaults
```

## Parameter Files

Configuration is stored as JSON files in the `params/` directory. The included files are:

| File | Description |
|------|-------------|
| `default.json` | Baseline rocket engine (hydrogen fuel, 6 MPa chamber pressure) |
| `Liquid_Ethanol_N2O.json` | Ethanol / nitrous oxide propellant combination |

Each file contains sections for initial conditions, nozzle geometry, gas properties, cooling channels, wall material, coolant properties, and solver settings. Gas properties accept either a scalar (constant along the nozzle) or a 3-element array `[chamber, throat, exit]` for spatially-varying profiles.

To create a new configuration, copy an existing file and edit the values. The GUI Parameters tab provides an inline editor with units and descriptions for every field.

## Output

Simulation results are written to the `results/` directory as CSV files. Each run produces a file named after the parameter file (e.g. `results/default_results.csv`).

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

## License

This project is licensed under the **PolyForm Noncommercial License 1.0.0**.  
Free for personal, educational, research, and non-profit use.  
Commercial use requires a separate written agreement.  
See [LICENSE](LICENSE) for full terms.
