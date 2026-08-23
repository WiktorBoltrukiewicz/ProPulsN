"""
geometry.py — nozzle profile preview for the Geometry section.

Replaces the old Geometry tab's matplotlib plot + stats box: the same numbers,
returned as data for the frontend to draw as SVG.
"""

import numpy as np

from ..core.geometry import (
    build_nozzle_geometry,
    R_CHAMBER_DEFAULT,
    L_CHAMBER_DEFAULT,
    R_CONV_ARC_DEFAULT,
)
from ..core.isentropic import inlet_N0_from_geometry


def preview_geometry(
    R_throat: float,
    E_r: float,
    n_grid: int = 100,
    R_chamber: float = R_CHAMBER_DEFAULT,
    L_chamber: float = L_CHAMBER_DEFAULT,
    R_conv_arc: float = R_CONV_ARC_DEFAULT,
    gamma: float = 1.1869,
) -> dict:
    """Build the profile and its summary stats.

    Lengths are returned in millimetres, the unit the old stats box displayed.
    """
    if R_throat <= 0:
        raise ValueError("Throat radius must be greater than zero.")
    if E_r <= 1:
        raise ValueError("Expansion ratio must be greater than 1.")
    if n_grid < 2:
        raise ValueError("Grid must have at least 2 points.")

    x_grid, r_grid, *_ = build_nozzle_geometry(
        R_param=R_throat, E_r=E_r, n_grid=n_grid,
        R_chamber=R_chamber, L_chamber=L_chamber, R_conv_arc=R_conv_arc,
    )

    idx_throat = int(np.argmin(r_grid))
    # Contraction ratio and the isentropic inlet Mach it implies, on the same
    # discretised grid the solver integrates. The solve itself shoots for a
    # value a few percent above this; running that here would cost ~0.3 s per
    # keystroke, and the isentropic value already answers the question the
    # preview is for — is this geometry able to choke at all?
    contraction = float((r_grid[0] / r_grid[idx_throat]) ** 2)
    N0 = inlet_N0_from_geometry(
        A_inlet=float(np.pi * r_grid[0] ** 2),
        A_throat=float(np.pi * r_grid[idx_throat] ** 2),
        gamma=gamma,
    )
    r_throat = float(r_grid[idx_throat])
    x_throat = float(x_grid[idx_throat])
    r_exit = float(r_grid[-1])
    length = float(x_grid[-1] - x_grid[0])

    return {
        "x_mm": (x_grid * 1000.0).tolist(),
        "r_mm": (r_grid * 1000.0).tolist(),
        "throat_index": idx_throat,
        "stats": {
            "total_length_mm": length * 1000.0,
            "throat_radius_mm": r_throat * 1000.0,
            "exit_radius_mm": r_exit * 1000.0,
            "E_r_actual": (r_exit / r_throat) ** 2,
            "throat_position_mm": x_throat * 1000.0,
            "chamber_radius_mm": float(r_grid[0]) * 1000.0,
            "contraction_ratio": contraction,
            "inlet_mach": float(np.sqrt(N0)),
            "N0_isentropic": float(N0),
        },
    }
