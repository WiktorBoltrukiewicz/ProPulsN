"""
convergence_loop.py — Convergence loop Stage 2 (full ODE with friction, no heat exchange).

Simplified version: no regenerative cooling (Stage 3).
Repeats the full ODE computation (Stage 2) with an updated friction profile dFdx
until the solution Y=[N, P, T] converges.
"""

import numpy as np
from scipy.integrate import solve_ivp
from scipy.interpolate import PchipInterpolator

from .ode_functions import my_nozzle_ode_full2, event_N1
from .compute_qf import compute_F


def run_stage2(xspan, Y0, params, YSol_prev, dx, iteration):
    """Stage 2: Full ODE with friction (dQdx=0, dFdx from previous iteration)."""
    n = len(xspan)

    # Compute friction profile from the previous solution
    Fx, f_gas, Re_gas, V_gas, dFdx = compute_F(xspan, YSol_prev, params)

    # dQdx = 0 (no heat exchange)
    dQdx_fun = lambda x: 0.0
    dFdx_fun = PchipInterpolator(xspan, dFdx, extrapolate=True)

    # Part A: from inlet to the sonic barrier (N=1)
    sol_a = solve_ivp(
        fun=lambda x, Y: my_nozzle_ode_full2(x, Y, params, dQdx_fun, dFdx_fun),
        t_span=(xspan[0], xspan[-1]),
        y0=Y0,
        method='RK45',
        t_eval=xspan,
        events=event_N1,
        rtol=1e-7,
        atol=1e-10
    )

    x1 = sol_a.t
    Y1 = sol_a.y.T

    if len(sol_a.t_events[0]) == 0:
        print(f"    [Iteration {iteration}] WARNING: Sonic point not reached!")
        Y0b = Y1[-1, :].copy()
        xe_val = xspan[0]
    else:
        xe_val = sol_a.t_events[0][-1]
        Y0b = sol_a.y_events[0][-1, :].copy()

    dA_at_throat = abs(params['dA_func'](xe_val))
    A_at_throat = params['A_func'](xe_val)

    relative_slope = dA_at_throat / (A_at_throat + 1e-12)
    delta = np.clip(0.02 + 0.5 * relative_slope, 0.02, 0.3)

    target_N_start = 1.0 + delta
    Y0b[0] = target_N_start

    # Part B: from sonic barrier to exit
    k_indices = np.where(xspan < xe_val)[0]
    if len(k_indices) == 0:
        k = 0
    else:
        k = k_indices[-1]
    xspan2 = xspan[k + 1:]

    sol_b = solve_ivp(
        fun=lambda x, Y: my_nozzle_ode_full2(x, Y, params, dQdx_fun, dFdx_fun),
        t_span=(xspan2[0], xspan2[-1]),
        y0=Y0b,
        method='RK45',
        t_eval=xspan2,
        rtol=1e-7,
        atol=1e-10,
        max_step=0.5 * dx,
        first_step=0.05 * dx,
    )

    if not sol_b.success:
        raise RuntimeError(
            f"[Iteration {iteration}] Stage B did not converge!\n"
            f"Reason: {sol_b.message}\n"
            f"Last point: x={sol_b.t[-1]:.4f}, N={sol_b.y[0, -1]:.4f}"
        )
    Y2 = sol_b.y.T

    YSol2 = np.vstack([Y1[:k + 1, :], Y2])
    YSol2 = np.real(YSol2)

    if YSol2.shape[0] != n:
        print(
            f" [Iteration {iteration}] WARNING: grid dimension mismatch!\n"
            f" Expected {n} points, got {YSol2.shape[0]}.\n"
            f" Throat detected at x={xe_val:.4f} m, N={Y0b[0]:.4f}, index k={k}.\n"
            f" Applying PCHIP interpolation — consider increasing grid density."
        )
        x_combined = np.concatenate([x1[:k + 1], sol_b.t])
        YSol2_interp = np.zeros((n, 3))
        for col in range(3):
            interp_func = PchipInterpolator(x_combined[:YSol2.shape[0]], YSol2[:, col],
                                            extrapolate=True)
            YSol2_interp[:, col] = interp_func(xspan)
        YSol2 = YSol2_interp

    return YSol2, dFdx


def compute_convergence(YSol_new, YSol_prev, dFdx_new=None, dFdx_prev=None):
    """
    Compute convergence metrics on solution Y=[N, P, T] and friction dFdx.

    Two norm families are computed:
      L∞  — maximum relative change; used as stopping criterion (unchanged behaviour)
      L1  — mean relative change;    used for plotting (smooth, Ansys-style curves)

    Returns
    -------
    conv_stop : float        — L∞ metric (stopping criterion)
    r_n, r_p, r_t : float   — L1 residuals per variable (M², Pressure, Temperature)
    r_f : float | None       — L1 friction residual (None on first iteration)
    relax : float            — adaptive under-relaxation factor
    """
    # ── L∞ stopping criterion (existing behaviour) ────────────────────────────
    diff_Y  = np.abs(YSol_new - YSol_prev)
    scale_Y = np.abs(YSol_prev) + 1e-10
    conv_stop = np.max(diff_Y / scale_Y)

    # ── L1 per-variable residuals (smooth, for plotting) ──────────────────────
    r_n = (np.sum(np.abs(YSol_new[:, 0] - YSol_prev[:, 0]))
           / (np.sum(np.abs(YSol_prev[:, 0])) + 1e-10))
    r_p = (np.sum(np.abs(YSol_new[:, 1] - YSol_prev[:, 1]))
           / (np.sum(np.abs(YSol_prev[:, 1])) + 1e-10))
    r_t = (np.sum(np.abs(YSol_new[:, 2] - YSol_prev[:, 2]))
           / (np.sum(np.abs(YSol_prev[:, 2])) + 1e-10))

    r_f = None
    if dFdx_new is not None and dFdx_prev is not None:
        r_f = (np.sum(np.abs(dFdx_new - dFdx_prev))
               / (np.sum(np.abs(dFdx_prev)) + 1e-10))

    # ── Adaptive relaxation (based on L∞, unchanged) ──────────────────────────
    if conv_stop > 1e-2:
        relax = 0.2
    elif conv_stop > 1e-4:
        relax = 0.4
    else:
        relax = 0.6

    return conv_stop, r_n, r_p, r_t, r_f, relax


def run_convergence_loop(xspan, Y0, params, YSol_init, dx, relax,
                         max_iterations=50, tol=1e-6, mode='convergence'):
    """
    Convergence loop: repeats Stage 2 (full ODE with friction) until Y converges
    or for a fixed number of iterations.

    Parameters
    ----------
    xspan           : axial grid
    Y0              : ODE initial condition
    params          : parameter dictionary
    YSol_init       : ODE solution from Stage 1 (isentropic)
    dx              : grid step
    max_iterations  : maximum / exact number of iterations
    tol             : convergence tolerance (used only when mode='convergence')
    relax           : under-relaxation factor (0-1)
    mode            : 'convergence' — stop when conv_Y < tol (default)
                      'fixed'       — always run all max_iterations

    Returns
    -------
    YSol_final          : final ODE solution
    convergence_history : list of convergence values per iteration
    """

    print("\n" + "=" * 70)
    print("  CONVERGENCE LOOP (Stage 2: ODE with friction)")
    print("=" * 70)
    if mode == 'fixed':
        print(f"  Mode: Fixed iterations ({max_iterations}),  Relaxation: {relax}")
    else:
        print(f"  Mode: Convergence (tol={tol:.1e}),  Max iterations: {max_iterations},  Relaxation: {relax}")
    print("-" * 70)

    YSol_prev = YSol_init.copy()
    dFdx_prev = None
    convergence_history = []                        # L∞ values (stopping criterion)
    res_hist = {'N': [], 'P': [], 'T': [], 'F': []} # L1 per-variable (plotting)

    for iteration in range(1, max_iterations + 1):
        print(f"\n>>> Iteration {iteration}/{max_iterations} <<<")

        print(f"  [Iteration {iteration}] Stage 2: ODE integration with friction...")
        YSol_new, dFdx_new = run_stage2(xspan, Y0, params, YSol_prev, dx, iteration)
        print(f"  [Iteration {iteration}] Stage 2 complete. Points: {YSol_new.shape[0]}")

        # Under-relaxation
        YSol_blended = relax * YSol_new + (1 - relax) * YSol_prev

        # Convergence metrics
        conv_stop, r_n, r_p, r_t, r_f, relax = compute_convergence(
            YSol_new, YSol_prev, dFdx_new, dFdx_prev
        )
        convergence_history.append(conv_stop)
        res_hist['N'].append(r_n)
        res_hist['P'].append(r_p)
        res_hist['T'].append(r_t)
        res_hist['F'].append(r_f if r_f is not None else float('nan'))

        r_f_part = f" R_F={r_f:.3e}" if r_f is not None else ""
        print(f"  [Iteration {iteration}] R_N={r_n:.3e} R_P={r_p:.3e} R_T={r_t:.3e}{r_f_part}"
              f"  stop={conv_stop:.3e} (target: < {tol:.1e})")

        if mode == 'convergence' and conv_stop < tol:
            print(f"\n{'=' * 70}")
            print(f"  CONVERGENCE ACHIEVED after {iteration} iterations!")
            print(f"  Final stop value: {conv_stop:.3e}")
            print(f"{'=' * 70}")
            return YSol_new, convergence_history, res_hist

        YSol_prev = YSol_blended.copy()
        dFdx_prev = dFdx_new.copy()

    print(f"\n{'=' * 70}")
    if mode == 'fixed':
        print(f"  Completed {max_iterations} fixed iterations.")
        print(f"  Final stop value: {convergence_history[-1]:.3e}")
    else:
        print(f"  WARNING: Reached {max_iterations} iterations without convergence!")
        print(f"  Last stop value: {convergence_history[-1]:.3e}")
    print(f"{'=' * 70}")

    return YSol_prev, convergence_history, res_hist
