"""
inlet_condition.py — solve for N0 (M^2 at the inlet) by shooting.

Why the area–Mach relation alone is not enough
----------------------------------------------
For continuous isentropic flow N0 follows directly from the ratio of
cross-sectional areas (see isentropic.py). The solver, however, integrates a
*discretised* geometry: A(x) is a PCHIP through the grid points, while dA/dx
is a separate PCHIP through np.gradient(A). Near the throat those two are not
consistent with each other, so the exact isentropic value sits just BELOW the
threshold at which the integration reaches N = 1 — the flow never chokes and
Stage 2 ends in `Bad domain`.

Measured deviation: the critical value lies 0.25%-5% above the isentropic one,
depending on geometry. It is always above, because discretisation error can
only make the sonic transition harder to reach.

What we do instead
------------------
The isentropic value serves as a guaranteed lower bound, and the actual N0 is
found by bisection on the predicate "does the integration reach N = 1?". The
function x_sonic(N0) is monotone (higher N0 -> sonic point further upstream),
so the threshold is sharply defined. A small safety margin is then added: very
close to the threshold the solution is extremely sensitive, and the M = 1
saddle point is only ever reachable in the limit anyway.

The shooting runs on the friction-free ODE (Stage 1). In subsonic flow
friction acts like additional contraction (the Fanno effect), so the threshold
with friction is always lower — an N0 found here is safe for Stage 2 too.
"""

import numpy as np
from scipy.integrate import solve_ivp

from .ode_functions import event_N1, my_nozzle_ode

# Margin over the critical value. At 2% the sonic point for the default engine
# falls ~2.2 mm before the throat, on a 212 mm nozzle — closer than the old
# hand-tuned constant 0.01535 managed (~4.0 mm).
DEFAULT_MARGIN = 0.02

# How many times the upper bracket may be raised while hunting for choking.
_MAX_BRACKET_STEPS = 40
_BRACKET_FACTOR = 1.1
_N0_CEILING = 0.9          # M = 0.95 at the inlet — beyond this it is not a chamber
_REL_TOL = 1e-5


def _reaches_sonic(N0, ode_params, x_span, P0, T0):
    """Does integration from the inlet reach N = 1? Returns (bool, x_sonic|None)."""
    try:
        sol = solve_ivp(
            fun=lambda x, Y: my_nozzle_ode(x, Y, ode_params),
            t_span=x_span,
            y0=[N0, P0, T0],
            method='RK45',
            events=event_N1,
            rtol=1e-8,
            atol=1e-12,
        )
    except Exception:
        # my_nozzle_ode only raises once it lands on the 1 - N singularity,
        # which means N has already reached 1. Count that as reaching sonic.
        return True, None

    if len(sol.t_events[0]) > 0:
        return True, float(sol.t_events[0][0])
    return False, None


def critical_inlet_N0(ode_params, x_span, P0, T0, N0_seed):
    """The smallest N0 at which the discretised nozzle chokes.

    Parameters
    ----------
    ode_params : dict — must contain 'A_func', 'dA_func', 'gamma_interp'
    x_span : (float, float) — integration range (inlet, exit)
    P0, T0 : float — the remaining initial conditions (they do not affect the
        friction-free ODE, but my_nozzle_ode requires them anyway)
    N0_seed : float — the isentropic value; the lower end of the bracket

    Returns
    -------
    (N0_critical, x_sonic) : float, float|None
    """
    if not (0 < N0_seed < 1):
        raise ValueError(f"N0 seed must lie in (0, 1) (got {N0_seed}).")

    lo = N0_seed
    reached, x_sonic = _reaches_sonic(lo, ode_params, x_span, P0, T0)

    if reached:
        # Rare but possible: the isentropic value already suffices. Walk down
        # to find a lower bracket so the answer is not overstated.
        hi = lo
        for _ in range(_MAX_BRACKET_STEPS):
            lo /= _BRACKET_FACTOR
            if not _reaches_sonic(lo, ode_params, x_span, P0, T0)[0]:
                break
        else:
            return hi, x_sonic
    else:
        hi = lo
        for _ in range(_MAX_BRACKET_STEPS):
            hi *= _BRACKET_FACTOR
            if hi > _N0_CEILING:
                break
            reached, x_sonic = _reaches_sonic(hi, ode_params, x_span, P0, T0)
            if reached:
                break
        else:
            reached = False
        if not reached:
            raise ValueError(
                "Could not find an inlet Mach number that chokes this nozzle. "
                "The contraction ratio is probably too small for the flow to "
                "reach sonic conditions at the throat — widen the chamber or "
                "narrow the throat."
            )

    # Bisect on the threshold. The predicate is monotone, so plain interval
    # halving is enough and needs no smoothness in the objective.
    for _ in range(80):
        if hi - lo <= _REL_TOL * hi:
            break
        mid = 0.5 * (lo + hi)
        ok, x_mid = _reaches_sonic(mid, ode_params, x_span, P0, T0)
        if ok:
            hi, x_sonic = mid, x_mid
        else:
            lo = mid

    return hi, x_sonic


def solve_inlet_N0(ode_params, x_span, P0, T0, N0_seed, margin=DEFAULT_MARGIN):
    """The N0 to use: the critical threshold plus a safety margin.

    Returns
    -------
    dict with keys 'N0', 'N0_critical', 'N0_isentropic', 'x_sonic', 'margin'
    """
    if margin < 0:
        raise ValueError(f"N0 margin must not be negative (got {margin}).")

    N0_critical, _ = critical_inlet_N0(ode_params, x_span, P0, T0, N0_seed)
    N0 = N0_critical * (1.0 + margin)

    # Too large an N0 can stop choking again (the integrator steps over the
    # singular region). If the margin causes that, cut it back.
    ok, x_sonic = _reaches_sonic(N0, ode_params, x_span, P0, T0)
    while not ok and margin > 1e-4:
        margin /= 2.0
        N0 = N0_critical * (1.0 + margin)
        ok, x_sonic = _reaches_sonic(N0, ode_params, x_span, P0, T0)
    if not ok:
        N0, x_sonic = N0_critical, None

    return {
        'N0': float(N0),
        'N0_critical': float(N0_critical),
        'N0_isentropic': float(N0_seed),
        'x_sonic': None if x_sonic is None else float(x_sonic),
        'margin': float(margin),
    }
