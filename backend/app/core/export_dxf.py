"""
export_dxf.py — export the rocket nozzle geometry to DXF.

Writes a .dxf holding the axial cross-section of the de Laval nozzle. The file
imports straight into SolidWorks or Ansys Discovery as a 2D sketch, ready to
be revolved about the symmetry axis (X).

DXF layers:
  UPPER_PROFILE   — upper nozzle contour (+r)  [the one to revolve]
  LOWER_PROFILE   — lower nozzle contour (-r)  [mirror image]
  SYMMETRY_AXIS   — the X rotation axis        [drawn as a centre line]
  POINTS          — defining points (throat, exit, inlet)
  DIMENSIONS      — text labels

Units: millimetres [mm]

Usage:
    python export_dxf.py                        # default parameters
    python export_dxf.py --params params/Liquid_Ethanol_N2O.json
    python export_dxf.py --R_throat 0.02 --E_r 6 --n_grid 500
    python export_dxf.py --output my_engine.dxf
"""

import argparse
import json
import os
import sys
from datetime import datetime

import numpy as np

try:
    import ezdxf
    from ezdxf import colors
    from ezdxf.enums import TextEntityAlignment
except ImportError:
    print("Error: ezdxf library not found. Install with: pip install ezdxf")
    sys.exit(1)

from .geometry import build_nozzle_geometry
from .param_schema import has_value, normalise_raw


# ---------------------------------------------------------------------------
# Default geometry values (matching default.json)
# ---------------------------------------------------------------------------
DEFAULT_R_THROAT = 0.01878   # [m]
DEFAULT_E_R = 5              # [-]
DEFAULT_N_GRID = 500         # more points -> smoother contour in CAD


def parse_args():
    parser = argparse.ArgumentParser(
        description="Export the rocket nozzle geometry to DXF (SolidWorks / Ansys Discovery)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--params", "-p",
        metavar="FILE.json",
        help="Engine parameter file (e.g. params/default.json). "
             "If given, R_throat and E_r are read from that JSON file.",
    )
    parser.add_argument(
        "--R_throat", type=float, default=None,
        metavar="M",
        help=f"Throat radius [m] (default {DEFAULT_R_THROAT} m = "
             f"{DEFAULT_R_THROAT * 1000:.3f} mm).",
    )
    parser.add_argument(
        "--E_r", type=float, default=None,
        metavar="[-]",
        help=f"Expansion ratio A_exit/A_throat (default {DEFAULT_E_R}).",
    )
    parser.add_argument(
        "--n_grid", type=int, default=DEFAULT_N_GRID,
        metavar="N",
        help=f"Number of contour points (default {DEFAULT_N_GRID}). "
             "More points = smoother contour.",
    )
    parser.add_argument(
        "--output", "-o",
        metavar="FILE.dxf",
        default=None,
        help="Output .dxf path (default: nozzle_<parameters>.dxf).",
    )
    parser.add_argument(
        "--no-mirror", action="store_true",
        help="Export the upper profile (+r) only, without the mirror image.",
    )
    parser.add_argument(
        "--spline", action="store_true",
        help="Use SPLINE entities instead of LWPOLYLINE (smoother contour, "
             "but slower to import in some SolidWorks versions).",
    )
    return parser.parse_args()


def load_params_from_json(filepath):
    """Read R_throat and E_r from an OpenEngine JSON parameter file."""
    with open(filepath, encoding="utf-8") as f:
        raw = normalise_raw(json.load(f))

    flat = {}
    for section in raw.values():
        if not isinstance(section, dict):
            continue
        for key, val in section.items():
            if key.startswith("_"):
                continue
            if has_value(val):
                flat[key] = val["value"]

    R_throat = flat.get("R_throat", DEFAULT_R_THROAT)
    E_r = flat.get("E_r", DEFAULT_E_R)
    return R_throat, E_r


def find_throat_index(r_grid):
    """Return the throat index (minimum radius)."""
    return int(np.argmin(r_grid))


def setup_layers(doc):
    """Define the DXF layers, with colours following CAD convention."""
    lt = doc.layers

    def add(name, color, linetype="Continuous", lineweight=25):
        layer = lt.new(name)
        layer.color = color
        layer.linetype = linetype
        layer.lineweight = lineweight  # 0.25 mm
        return layer

    # Kolory ACI (AutoCAD Color Index)
    add("UPPER_PROFILE",   color=colors.WHITE,   lineweight=50)   # 0.50 mm
    add("LOWER_PROFILE",   color=colors.CYAN,    lineweight=35)   # 0.35 mm
    add("SYMMETRY_AXIS",   color=colors.RED,     linetype="CENTER", lineweight=18)
    add("POINTS",          color=colors.YELLOW,  lineweight=18)
    add("DIMENSIONS",      color=colors.GREEN,   lineweight=18)


def add_profile_polyline(msp, x_mm, r_mm, layer_name):
    """Add the profile as an LWPOLYLINE (2D polyline)."""
    points = list(zip(x_mm, r_mm))
    msp.add_lwpolyline(points, dxfattribs={"layer": layer_name})


def add_profile_spline(msp, x_mm, r_mm, layer_name):
    """Add the profile as a SPLINE (smooth interpolating curve)."""
    points = [(float(x), float(r), 0.0) for x, r in zip(x_mm, r_mm)]
    msp.add_spline(points, dxfattribs={"layer": layer_name})


def add_centerline(msp, x_start, x_end):
    """Add the symmetry axis as a line."""
    msp.add_line(
        (x_start, 0), (x_end, 0),
        dxfattribs={"layer": "SYMMETRY_AXIS"},
    )


def add_marker_cross(msp, x, y, size_mm=0.5, layer="POINTS"):
    """Draw a cross at (x, y) marking a defining point."""
    msp.add_line((x - size_mm, y), (x + size_mm, y), dxfattribs={"layer": layer})
    msp.add_line((x, y - size_mm), (x, y + size_mm), dxfattribs={"layer": layer})


def add_label(msp, x, y, text, height_mm=1.5, layer="DIMENSIONS"):
    """Add a text label."""
    msp.add_text(
        text,
        dxfattribs={
            "layer": layer,
            "height": height_mm,
            "insert": (x, y),
        },
    )


def add_dimension_line(msp, x, r_top, r_bot, layer="DIMENSIONS"):
    """Draw a vertical dimension line labelled with the diameter."""
    # Linia wymiarowa od -r do +r
    msp.add_line((x, r_bot), (x, r_top), dxfattribs={"layer": layer})
    # Arrowheads (short horizontal ticks)
    tick = 0.5
    msp.add_line((x - tick, r_top), (x + tick, r_top), dxfattribs={"layer": layer})
    msp.add_line((x - tick, r_bot), (x + tick, r_bot), dxfattribs={"layer": layer})


def build_dxf(x_grid, r_grid, args, R_throat_mm, E_r, add_labels=True):
    """Buduje dokument DXF i zwraca go."""

    # --- Przeliczenie jednostek: m → mm ---
    x_mm = x_grid * 1000.0
    r_mm = r_grid * 1000.0

    x_start = float(x_mm[0])
    x_end = float(x_mm[-1])

    # Indices of the key sections
    idx_throat = find_throat_index(r_grid)
    idx_exit = -1   # ostatni punkt
    idx_inlet = 0   # pierwszy punkt

    r_throat_mm = float(r_mm[idx_throat])
    x_throat_mm = float(x_mm[idx_throat])
    r_exit_mm = float(r_mm[idx_exit])
    x_exit_mm = float(x_mm[idx_exit])
    r_inlet_mm = float(r_mm[idx_inlet])
    x_inlet_mm = float(x_mm[idx_inlet])

    # --- Tworzenie dokumentu DXF ---
    doc = ezdxf.new(dxfversion="R2010")
    doc.header["$INSUNITS"] = 4          # jednostki: mm (4 = milimetry)
    doc.header["$MEASUREMENT"] = 1       # metryczny
    doc.header["$LUNITS"] = 4            # display lengths in decimal notation

    # Load the CENTER linetype (for the symmetry axis) if it is missing
    if "CENTER" not in doc.linetypes:
        doc.linetypes.new("CENTER", dxfattribs={"description": "Center ----", "pattern": [1.25, 0.25, -0.25]})

    setup_layers(doc)
    msp = doc.modelspace()

    # --- Upper profile (+r) ---
    if args.spline:
        add_profile_spline(msp, x_mm, r_mm, "UPPER_PROFILE")
    else:
        add_profile_polyline(msp, x_mm, r_mm, "UPPER_PROFILE")

    # --- Lower profile (-r) ---
    if not args.no_mirror:
        if args.spline:
            add_profile_spline(msp, x_mm, -r_mm, "LOWER_PROFILE")
        else:
            add_profile_polyline(msp, x_mm, -r_mm, "LOWER_PROFILE")

    # --- Symmetry axis ---
    margin = max(5.0, (x_end - x_start) * 0.05)
    add_centerline(msp, x_start - margin, x_end + margin)

    # --- Vertical lines closing the inlet and exit sections ---
    msp.add_line(
        (x_inlet_mm, -r_inlet_mm if not args.no_mirror else 0),
        (x_inlet_mm, r_inlet_mm),
        dxfattribs={"layer": "UPPER_PROFILE"},
    )
    msp.add_line(
        (x_exit_mm, -r_exit_mm if not args.no_mirror else 0),
        (x_exit_mm, r_exit_mm),
        dxfattribs={"layer": "UPPER_PROFILE"},
    )

    # --- Markers at the defining points ---
    cross_size = R_throat_mm * 0.15

    # Throat
    add_marker_cross(msp, x_throat_mm, r_throat_mm, size_mm=cross_size)
    if not args.no_mirror:
        add_marker_cross(msp, x_throat_mm, -r_throat_mm, size_mm=cross_size)

    if add_labels:
        # Throat line (vertical, dashed)
        msp.add_line(
            (x_throat_mm, -r_inlet_mm * 1.1 if not args.no_mirror else 0),
            (x_throat_mm, r_inlet_mm * 1.1),
            dxfattribs={"layer": "DIMENSIONS"},
        )

        # --- Etykiety tekstowe ---
        label_height = max(1.0, R_throat_mm * 0.2)
        offset_y = r_inlet_mm * 1.15

        add_label(msp, x_inlet_mm, offset_y + label_height,
                  f"INLET  Ø{r_inlet_mm * 2:.2f} mm", height_mm=label_height)

        add_label(msp, x_throat_mm, offset_y + label_height,
                  f"THROAT  Ø{r_throat_mm * 2:.2f} mm", height_mm=label_height)

        add_label(msp, x_exit_mm - (x_exit_mm - x_throat_mm) * 0.5, offset_y + label_height,
                  f"EXIT  Ø{r_exit_mm * 2:.2f} mm  Er={E_r:.1f}", height_mm=label_height)

        # Total length
        length_mm = x_end - x_start
        add_label(msp, (x_start + x_end) / 2, -offset_y - label_height * 2,
                  f"Total_Length = {length_mm:.2f} mm", height_mm=label_height)

        # Date and parameters in the footer
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        add_label(msp, x_start, -offset_y - label_height * 4,
                  f"OpenEngine | R_t={R_throat_mm:.3f} mm | Er={E_r:.1f} | {now}",
                  height_mm=label_height * 0.8)

    return doc


def generate_output_filename(R_throat_m, E_r, output_dir="results"):
    """Generate an automatic name for the output file."""
    os.makedirs(output_dir, exist_ok=True)
    R_mm = R_throat_m * 1000
    base = f"nozzle_Rt{R_mm:.2f}mm_Er{E_r:.1f}"
    # Auto-increment the index if the file already exists
    for i in range(1, 100):
        fname = os.path.join(output_dir, f"{base}_{i:02d}.dxf")
        if not os.path.exists(fname):
            return fname
    return os.path.join(output_dir, f"{base}_99.dxf")


def print_summary(x_grid, r_grid, R_throat_m, E_r, output_path, args):
    """Print a summary of the export."""
    x_mm = x_grid * 1000
    r_mm = r_grid * 1000
    idx_t = find_throat_index(r_grid)

    print("\n" + "=" * 60)
    print("  NOZZLE GEOMETRY EXPORT → DXF")
    print("=" * 60)
    print(f"  Throat radius        : {R_throat_m * 1000:.3f} mm")
    print(f"  Expansion ratio      : {E_r:.2f}")
    print(f"  Ø throat             : {r_mm[idx_t] * 2:.3f} mm")
    print(f"  Ø inlet (chamber)    : {r_mm[0] * 2:.3f} mm")
    print(f"  Ø exit               : {r_mm[-1] * 2:.3f} mm")
    print(f"  Nozzle length        : {x_mm[-1] - x_mm[0]:.2f} mm")
    print(f"  Throat X position    : {x_mm[idx_t]:.2f} mm")
    print(f"  Number of points     : {len(x_grid)}")
    print(f"  Profile format       : {'SPLINE' if args.spline else 'LWPOLYLINE'}")
    print(f"  Lower profile        : {'no' if args.no_mirror else 'yes (mirror -r)'}")
    print(f"  Units                : millimeters [mm]")
    print("-" * 60)
    print(f"  DXF file             : {output_path}")
    print("=" * 60)
    print()
    print("  How to open in SolidWorks:")
    print("  1. File → Open → select the .dxf file")
    print("  2. Import as 2D sketch")
    print("  3. Use 'Revolve' around the X axis (SYMMETRY_AXIS) to get a 3D solid")
    print()
    print("  How to open in Ansys Discovery:")
    print("  1. File → Import → select the .dxf file")
    print("  2. Select the XY plane as the sketch plane")
    print("  3. Revolve the UPPER_PROFILE around the X axis")
    print()


def main():
    args = parse_args()

    # --- Read parameters ---
    R_throat = DEFAULT_R_THROAT
    E_r = DEFAULT_E_R

    if args.params:
        if not os.path.isfile(args.params):
            print(f"Error: parameter file not found: {args.params}")
            sys.exit(1)
        R_throat, E_r = load_params_from_json(args.params)
        print(f"  Parameters loaded from: {args.params}")

    # CLI arguments override JSON values
    if args.R_throat is not None:
        R_throat = args.R_throat
    if args.E_r is not None:
        E_r = args.E_r

    # --- Generate geometry ---
    print(f"\n  Generating geometry ({args.n_grid} points)...", end=" ", flush=True)
    x_grid, r_grid, *_ = build_nozzle_geometry(
        R_param=R_throat,
        E_r=E_r,
        n_grid=args.n_grid,
    )
    print("OK")

    # --- Budowanie DXF ---
    print("  Building DXF file...", end=" ", flush=True)
    doc = build_dxf(x_grid, r_grid, args, R_throat_mm=R_throat * 1000, E_r=E_r)
    print("OK")

    # --- Write the file ---
    if args.output:
        output_path = args.output
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    else:
        output_path = generate_output_filename(R_throat, E_r)

    doc.saveas(output_path)

    print_summary(x_grid, r_grid, R_throat, E_r, output_path, args)


if __name__ == "__main__":
    main()
