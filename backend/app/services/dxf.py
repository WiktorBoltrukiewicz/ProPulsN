"""
dxf.py — thin wrapper around core/export_dxf.py for the `export_dxf` command.

The old Geometry tab did this inline around a file dialog; here the options
arrive in the command payload and the file always lands in results/.
"""

import argparse
import os

from ..core import RESULTS_DIR
from ..core.export_dxf import build_dxf, generate_output_filename
from ..core.geometry import (
    build_nozzle_geometry,
    R_CHAMBER_DEFAULT,
    L_CHAMBER_DEFAULT,
    R_CONV_ARC_DEFAULT,
)


def export_dxf(
    R_throat: float,
    E_r: float,
    n_grid: int = 500,
    mirror: bool = False,
    spline: bool = True,
    labels: bool = False,
    filename: str = None,
    R_chamber: float = R_CHAMBER_DEFAULT,
    L_chamber: float = L_CHAMBER_DEFAULT,
    R_conv_arc: float = R_CONV_ARC_DEFAULT,
) -> str:
    """Write a DXF of the nozzle profile. Returns its path relative to results/."""
    if R_throat <= 0:
        raise ValueError("Throat radius must be greater than zero.")
    if E_r <= 1:
        raise ValueError("Expansion ratio must be greater than 1.")
    if n_grid < 2:
        raise ValueError("DXF grid must have at least 2 points.")

    os.makedirs(RESULTS_DIR, exist_ok=True)

    if filename:
        # Never let a client write outside results/.
        if os.path.basename(filename) != filename:
            raise ValueError(f"Invalid filename: {filename!r}")
        if not filename.lower().endswith(".dxf"):
            filename += ".dxf"
        out_path = os.path.join(RESULTS_DIR, filename)
    else:
        out_path = generate_output_filename(R_throat, E_r, output_dir=RESULTS_DIR)

    x_grid, r_grid, *_ = build_nozzle_geometry(
        R_param=R_throat, E_r=E_r, n_grid=n_grid,
        R_chamber=R_chamber, L_chamber=L_chamber, R_conv_arc=R_conv_arc,
    )

    # build_dxf() still takes the CLI's argparse namespace.
    args = argparse.Namespace(spline=spline, no_mirror=not mirror)
    doc = build_dxf(
        x_grid, r_grid, args,
        R_throat_mm=R_throat * 1000, E_r=E_r,
        add_labels=labels,
    )
    doc.saveas(out_path)

    return os.path.basename(out_path)
