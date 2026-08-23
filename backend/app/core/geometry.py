"""
geometry.py — builds the de Laval nozzle contour.

Assembles the nozzle profile from circular arcs, straight segments and a
Bezier curve. Returns the grid of (x, r) points, the cross-sectional areas
A(x) and their derivatives dA/dx, plus PCHIP interpolants ready for the ODE
solver.

Corresponds to buildNozzleGeometry() in the original MATLAB code.

The whole contour is parametric: the chamber (R_chamber, L_chamber,
R_conv_arc) as much as the throat (R_param) and the divergent section (E_r).
The defaults reproduce the original MATLAB contour bit for bit.
"""

import numpy as np
from scipy.interpolate import PchipInterpolator

# Chamber defaults — the constants from the original MATLAB code.
R_CHAMBER_DEFAULT = 0.04205    # combustion chamber radius [m]
L_CHAMBER_DEFAULT = 0.14262    # chamber inlet sits at x = -L_CHAMBER [m]
R_CONV_ARC_DEFAULT = 0.07265   # convergent large-arc radius [m]


def build_nozzle_geometry(
    R_param=0.01878,
    E_r=5,
    n_grid=100,
    R_chamber=R_CHAMBER_DEFAULT,
    L_chamber=L_CHAMBER_DEFAULT,
    R_conv_arc=R_CONV_ARC_DEFAULT,
):
    """
    Build the rocket nozzle contour.

    Parameters
    ----------
    R_param : float — throat radius [m] (default 0.01878)
    E_r : float — expansion ratio A_exit/A_throat (default 5)
    n_grid : int — number of grid points (default 100)
    R_chamber : float — combustion chamber radius [m] (default 0.04205)
    L_chamber : float — distance from the chamber inlet to the throat [m]
        (the throat sits at x = 0, the chamber starts at x = -L_chamber)
    R_conv_arc : float — convergent section large-arc radius [m]

    The large arc's centre lies at y = R_chamber - R_conv_arc. That is not a
    parameter but the condition for the arc to meet the chamber wall
    tangentially.

    Returns
    -------
    x_grid : np.ndarray  — axial positions [m]
    r_grid : np.ndarray  — contour radius at each point [m]
    A_grid : np.ndarray  — cross-sectional area A = pi * r^2 [m^2]
    dA_grid_dx : np.ndarray — derivative dA/dx [m]
    A_interp : PchipInterpolator — interpolant for A(x)
    dA_interp : PchipInterpolator — interpolant for dA/dx(x)
    """

    if R_param <= 0:
        raise ValueError(f"R_throat must be > 0 (got {R_param}).")
    if E_r <= 1:
        raise ValueError(f"E_r must be > 1 (got {E_r}).")
    if R_chamber <= R_param:
        raise ValueError(
            f"R_chamber ({R_chamber}) must be larger than the throat radius "
            f"({R_param}); a nozzle cannot converge into a wider throat."
        )
    if R_conv_arc <= 0:
        raise ValueError(f"R_conv_arc must be > 0 (got {R_conv_arc}).")

    # Centre of the convergent large arc — follows from tangency to the wall.
    y_arc = R_chamber - R_conv_arc

    # --- Key contour points (convergent section) ---
    # Coordinates of the defining points, from the fillet radii and angles
    # (TRD / Rao convention).
    X1 = 1.5 * R_param * np.cos(np.radians(-120))
    Y1 = 1.5 * R_param * np.sin(np.radians(-120)) + 2.5 * R_param

    # Tangent slope
    m = X1 / np.sqrt((1.5 * R_param) ** 2 - X1 ** 2)

    Y3 = y_arc + R_conv_arc / np.sqrt(1 + m ** 2)
    X3 = X1 + (Y3 - Y1) / m
    Xc = X3 - (-m * R_conv_arc) / np.sqrt(1 + m ** 2)

    if X3 > X1:
        raise ValueError(
            f"Convergent section is inconsistent: the large arc ends at "
            f"x = {X3:.5f} m, downstream of the pre-throat arc at x = {X1:.5f} m, "
            f"so the contour would fold back on itself. R_conv_arc "
            f"({R_conv_arc}) is too large for a chamber of radius {R_chamber}; "
            f"reduce R_conv_arc or widen the chamber."
        )

    if Xc <= -L_chamber:
        raise ValueError(
            f"Chamber is too short: the convergent arc starts at x = {Xc:.5f} m, "
            f"at or upstream of the chamber inlet at x = {-L_chamber:.5f} m. "
            f"Increase L_chamber or reduce R_conv_arc."
        )

    # --- Point N (start of the Bezier curve — divergent section) ---
    X2 = 0.382 * R_param * np.cos(np.radians(-68))
    Y2 = 0.382 * R_param * np.sin(np.radians(-68)) + 1.382 * R_param

    Nx, Ny = X2, Y2
    m1 = np.tan(np.radians(22))
    m2 = np.tan(np.radians(12))
    c1 = Ny - m1 * Nx

    # Exit point E
    Ey = np.sqrt(E_r) * R_param
    Ex = 0.8 * (((np.sqrt(E_r) - 1) * R_param) / np.tan(np.radians(15)))
    c2 = Ey - m2 * Ex

    # Bezier control point Q
    Qx = (c2 - c1) / (m1 - m2)
    Qy = (m1 * c2 - m2 * c1) / (m1 - m2)

    # --- Build the 6 contour segments ---
    N_pts = 500  # points per segment (dense, for accuracy)

    # Segment 1: combustion chamber (constant radius)
    x1 = np.linspace(-L_chamber, Xc, N_pts)
    y1 = R_chamber * np.ones(N_pts)

    # Segment 2: circular arc (convergent, large R)
    x2 = np.linspace(Xc, X3, N_pts)
    y2 = y_arc + np.sqrt(R_conv_arc ** 2 - (x2 - Xc) ** 2)

    # Segment 3: straight line (convergent)
    x3 = np.linspace(X3, X1, N_pts)
    y3 = m * (x3 - X1) + Y1

    # Segment 4: circular arc just upstream of the throat
    x4 = np.linspace(X1, 0, N_pts)
    y4 = -np.sqrt((1.5 * R_param) ** 2 - x4 ** 2) + 2.5 * R_param

    # Segment 5: circular arc just downstream of the throat
    x5 = np.linspace(0, X2, N_pts)
    y5 = -np.sqrt((0.382 * R_param) ** 2 - x5 ** 2) + 1.382 * R_param

    # Segment 6: Bezier curve (divergent, Rao profile)
    t = np.linspace(0, 1, N_pts)
    x6 = (1 - t) ** 2 * Nx + 2 * (1 - t) * t * Qx + t ** 2 * Ex
    y6 = (1 - t) ** 2 * Ny + 2 * (1 - t) * t * Qy + t ** 2 * Ey

    # --- Concatenate the segments (no duplicate points at the joints) ---
    X_raw = np.concatenate([x1, x2[1:], x3[1:], x4[1:], x5[1:], x6[1:]])
    Y_raw = np.concatenate([y1, y2[1:], y3[1:], y4[1:], y5[1:], y6[1:]])

    # Shift so that x starts at 0
    X_raw = X_raw - X_raw[0]

    # --- Reparametrize by arc length -> evenly spaced grid ---
    S = np.zeros(len(X_raw))
    S[1:] = np.cumsum(np.sqrt(np.diff(X_raw) ** 2 + np.diff(Y_raw) ** 2))
    S_100 = np.linspace(0, S[-1], n_grid)

    x_grid = np.interp(S_100, S, X_raw)
    r_grid = np.interp(S_100, S, Y_raw)

    # --- Cross-sectional area and its derivative ---
    A_grid = np.pi * r_grid ** 2
    dr_dx = np.gradient(r_grid, x_grid)          # dr/dx (numerical)
    dA_grid_dx = 2 * np.pi * r_grid * dr_dx      # dA/dx = 2*pi*r * dr/dx

    # --- PCHIP interpolants (smooth, monotone) ---
    A_interp = PchipInterpolator(x_grid, A_grid, extrapolate=True)
    dA_interp = PchipInterpolator(x_grid, dA_grid_dx, extrapolate=True)

    return x_grid, r_grid, A_grid, dA_grid_dx, A_interp, dA_interp
