"""
isentropic.py — the area–Mach relation for isentropic flow.

Used to derive the initial condition N0 (M^2 at the inlet) from the geometry,
rather than having it typed into the parameter file by hand.

For choked flow (sonic at the throat) A* = A_throat, so the ratio
A_chamber/A_throat fixes the subsonic inlet Mach number uniquely:

    A/A* = (1/M) * [ (2/(g+1)) * (1 + (g-1)/2 * M^2) ] ^ ((g+1)/(2(g-1)))

This has exactly two roots for A/A* > 1 — one subsonic, one supersonic. The
inlet sits on the subsonic branch, M in (0, 1).

A note on the physics: with friction the choking point shifts slightly
downstream of the area minimum (the Fanno effect), so the isentropic value is
a very good approximation rather than the exact solution of the boundary value
problem. The Stage 2 solver detects the sonic transition with a terminal event
(event_N1) instead of shooting at the saddle point, so the approximation is
more than good enough as a starting bracket. See inlet_condition.py.
"""

import numpy as np
from scipy.optimize import brentq


def area_ratio(M, gamma):
    """A/A* for a given Mach number M and ratio of specific heats gamma."""
    if M <= 0:
        raise ValueError(f"Mach number must be > 0 (got {M}).")
    exponent = (gamma + 1) / (2 * (gamma - 1))
    return (1.0 / M) * ((2 / (gamma + 1)) * (1 + (gamma - 1) / 2 * M ** 2)) ** exponent


def mach_from_area_ratio(ratio, gamma, branch="subsonic"):
    """Invert the area–Mach relation.

    Parameters
    ----------
    ratio : float — A/A*, must be >= 1
    gamma : float — ratio of specific heats, must be > 1
    branch : {'subsonic', 'supersonic'} — which branch to return

    Returns
    -------
    float — Mach number M
    """
    if gamma <= 1:
        raise ValueError(f"gamma must be > 1 (got {gamma}).")
    if not np.isfinite(ratio):
        raise ValueError(f"Area ratio must be finite (got {ratio}).")
    if ratio < 1.0:
        raise ValueError(
            f"Area ratio must be >= 1 (got {ratio}); A* is the smallest area "
            f"a choked flow can pass through."
        )
    if branch not in ("subsonic", "supersonic"):
        raise ValueError(f"Unknown branch {branch!r}.")

    # Degenerate case: the section equals the critical area.
    if np.isclose(ratio, 1.0):
        return 1.0

    def residual(M):
        return area_ratio(M, gamma) - ratio

    if branch == "subsonic":
        # A/A* -> +inf as M -> 0 and -> 1 as M -> 1, so the root is always
        # inside this bracket.
        lo, hi = 1e-9, 1.0 - 1e-12
    else:
        # Grow until the sign flips — A/A* increases monotonically for M > 1.
        lo, hi = 1.0 + 1e-12, 2.0
        while residual(hi) < 0:
            hi *= 2.0
            if hi > 1e4:
                raise ValueError(f"No supersonic solution found for A/A* = {ratio}.")

    return float(brentq(residual, lo, hi, xtol=1e-14, rtol=1e-14))


def inlet_N0_from_geometry(A_inlet, A_throat, gamma):
    """N0 = M_inlet^2, derived from the ratio of cross-sectional areas.

    Pass areas taken from the solver *grid* (A_grid[0] and min(A_grid)) rather
    than pi*r^2 from the parameters, so N0 is consistent with the discretised
    geometry the ODE actually integrates.
    """
    if A_throat <= 0:
        raise ValueError(f"Throat area must be > 0 (got {A_throat}).")
    if A_inlet < A_throat:
        raise ValueError(
            f"Inlet area ({A_inlet:.6e} m^2) is smaller than the throat area "
            f"({A_throat:.6e} m^2) — the nozzle does not converge."
        )
    M = mach_from_area_ratio(A_inlet / A_throat, gamma, branch="subsonic")
    return M ** 2
