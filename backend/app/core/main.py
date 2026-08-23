"""
main.py — Main script for rocket engine nozzle simulation (no regenerative cooling).

Calculates exhaust gas flow through the nozzle (N, P, T) including friction.
Prepares a grid of points for export (e.g. to Ansys).

Stages:
  1. Initial ODE integration (isentropic flow)
  2. Convergence loop: full ODE with friction (dQdx=0) until Y converges

Required libraries: numpy, scipy, matplotlib
Usage:
  python main.py                        — interactive mode (select parameter file)
  python main.py params/default.json   — load a specific file
  python main.py --default             — run with built-in default parameters
"""

import sys
import time
czas_start = time.time()
import numpy as np
from scipy.integrate import solve_ivp

from .geometry import (
    build_nozzle_geometry,
    R_CHAMBER_DEFAULT,
    L_CHAMBER_DEFAULT,
    R_CONV_ARC_DEFAULT,
)
from .isentropic import inlet_N0_from_geometry
from .inlet_condition import DEFAULT_MARGIN as DEFAULT_N0_MARGIN, solve_inlet_N0
from .ode_functions import my_nozzle_ode
from .parameters import compute_gas_parameters, compute_bartz_htc
from .convergence_loop import run_convergence_loop
from .param_loader import load_and_select_params, load_params
from .results_exporter import export_results
from .gas_properties import build_gas_property_arrays, log_property_nodes


def main(param_file=None):
    # =====================================================================
    # 0. LOAD PARAMETERS
    # =====================================================================
    loaded = None
    selected_filepath = None

    if param_file == '--default':
        loaded = None
        selected_filepath = None
    elif param_file is not None:
        print(f"Loading parameters from: {param_file}")
        loaded, _ = load_params(param_file)
        selected_filepath = param_file
        print(f"  Loaded {len(loaded)} parameters.")
    else:
        loaded, selected_filepath = load_and_select_params()

    if selected_filepath is not None:
        import os as _os
        params_name = _os.path.splitext(_os.path.basename(selected_filepath))[0]
    else:
        params_name = 'default'

    def p(key, default):
        if loaded and key in loaded:
            return loaded[key]
        return default

    # =====================================================================
    # 1. NOZZLE GEOMETRY
    # =====================================================================
    print("Building nozzle geometry...")
    R_throat = p('R_throat', 0.01878)
    E_r = p('E_r', 5)
    n_grid = int(p('n_grid', 100))
    R_chamber = p('R_chamber', R_CHAMBER_DEFAULT)
    L_chamber = p('L_chamber', L_CHAMBER_DEFAULT)
    R_conv_arc = p('R_conv_arc', R_CONV_ARC_DEFAULT)

    xspan, R_grid, A_grid, dA_grid_dx, A_interp, dA_interp = build_nozzle_geometry(
        R_param=R_throat, E_r=E_r, n_grid=n_grid,
        R_chamber=R_chamber, L_chamber=L_chamber, R_conv_arc=R_conv_arc,
    )

    n = len(xspan)
    dx = np.mean(np.diff(xspan))

    # Warunek poczatkowy ODE: [N, P, T]. N0 rozwiazujemy nizej, gdy juz
    # istnieja interpolanty A(x) i gamma(x) potrzebne do strzelania.
    P0 = p('P0', 6000000.0)
    T0 = p('T0', 2941.58)

    # =====================================================================
    # 2. PARAMETER DICTIONARY
    # =====================================================================
    params = {}
    params['A'] = A_grid.copy()
    params['R'] = R_grid.copy()

    idx_throat = int(np.argmin(params['R']))

    # --- Physical constants ---
    params['eta'] = p('eta', 0.000086742)
    params['epsilon'] = p('epsilon', 0.00005)
    params['D'] = params['R'] * 2
    params['At'] = np.min(params['A'])
    params['Dt'] = 2 * np.min(params['R'])

    # --- Metadata (CSV export) ---
    params['c_star'] = p('c_star', 2416.8)
    params['mdot_gas'] = p('mdot_gas', 1.06)

    # =====================================================================
    # GAS PROPERTY INTERPOLATION (PCHIP: chamber -> throat -> exit)
    # =====================================================================
    print("Building gas property profiles (PCHIP)...")
    gas_props = build_gas_property_arrays(p, xspan, idx_throat)
    log_property_nodes(gas_props)

    params['gamma_arr'] = gas_props['gamma_arr']
    params['Cpcg_arr'] = gas_props['Cpcg_arr']
    params['Prcg_arr'] = gas_props['Prcg_arr']
    params['molar_mass_arr'] = gas_props['combustion_molar_mass_arr']
    params['Rs_arr'] = gas_props['Rs_arr']

    params['gamma_interp'] = gas_props['gamma_interp']
    params['Cpcg_interp'] = gas_props['Cpcg_interp']
    params['Prcg_interp'] = gas_props['Prcg_interp']
    params['Rs_interp'] = gas_props['Rs_interp']

    params['gamma'] = gas_props['gamma_chamber']

    # Funkcje interpolujace A(x) i dA/dx(x) dla solvera ODE
    params['A_func'] = A_interp
    params['dA_func'] = dA_interp

    # =====================================================================
    # WARUNEK POCZATKOWY N0 (M^2 na wlocie)
    # =====================================================================
    # N0 is no longer a hand-tuned constant valid for one geometry only.
    # It is resolved in two steps:
    #   1. the area-Mach relation gives the isentropic value -- exact for
    #      continuous flow, and a guaranteed lower bound for the discretised one;
    #   2. bisection on the choking threshold finds the smallest N0 at which
    #      the integration actually reaches N = 1, plus a small margin.
    # Step 2 is necessary: discretisation error in A(x) / dA(x) near the throat
    # puts the threshold 0.25%-5% above the isentropic value, so the isentropic
    # value on its own does not choke the nozzle. See core/inlet_condition.py.
    N0_auto = bool(p('N0_auto', True))
    N0_manual = p('N0', None)
    N0_margin = float(p('N0_margin', DEFAULT_N0_MARGIN))

    N0_isentropic = inlet_N0_from_geometry(
        A_inlet=float(A_grid[0]), A_throat=float(np.min(A_grid)), gamma=params['gamma']
    )
    contraction = float(A_grid[0] / np.min(A_grid))

    if N0_auto or N0_manual is None:
        print("Solving for the inlet condition N0...")
        info = solve_inlet_N0(
            ode_params=params,
            x_span=(xspan[0], xspan[-1]),
            P0=P0, T0=T0,
            N0_seed=N0_isentropic,
            margin=N0_margin,
        )
        N0 = info['N0']
        print(f"  Contraction ratio A_inlet/A_throat = {contraction:.5f} "
              f"(gamma = {params['gamma']:.4f})")
        print(f"  Isentropic N0 = {info['N0_isentropic']:.6f}  |  "
              f"choking threshold = {info['N0_critical']:.6f}  |  "
              f"used = {N0:.6f} (+{100 * info['margin']:.1f}% margin)")
        if info['x_sonic'] is not None:
            offset_mm = 1000.0 * (info['x_sonic'] - xspan[int(np.argmin(A_grid))])
            print(f"  Sonic point at x = {info['x_sonic']:.5f} m "
                  f"({offset_mm:+.2f} mm relative to the throat), "
                  f"M_inlet = {np.sqrt(N0):.6f}")
        if N0_manual is not None and not np.isclose(N0_manual, N0, rtol=0.05):
            print(f"  NOTE: the parameter file pins N0 = {N0_manual:.6f}, which does "
                  f"not match this geometry. Set N0_auto = 0 to force it anyway.")
    else:
        N0 = N0_manual
        print(f"  N0 = {N0:.6f} taken from the parameter file (N0_auto = 0). "
              f"Isentropic value for this geometry is {N0_isentropic:.6f}.")
        if N0 < N0_isentropic:
            print("  WARNING: the pinned N0 is below the isentropic value for this "
                  "contraction ratio. The flow cannot reach sonic conditions.")

    Y0 = np.array([N0, P0, T0])

    # Pre-allocate the result vectors
    params['T_aw'] = np.full(n, np.nan)
    params['M'] = np.full(n, np.nan)

    # =====================================================================
    # STAGE 1: INITIAL ODE INTEGRATION (isentropic flow)
    # =====================================================================
    print("Stage 1: ODE integration (isentropic flow)...")

    sol1 = solve_ivp(
        fun=lambda x, Y: my_nozzle_ode(x, Y, params),
        t_span=(xspan[0], xspan[-1]),
        y0=Y0,
        method='RK45',
        t_eval=xspan,
        rtol=1e-3,
        atol=1e-6
    )

    YSol = sol1.y.T
    print(f"  ODE1 complete. Points: {YSol.shape[0]}")

    # Oblicz T_aw i M z rozwiazania izoentropowego
    for i in range(n):
        T_aw_i, M_i = compute_gas_parameters(YSol, params, i)
        params['T_aw'][i] = T_aw_i
        params['M'][i] = M_i

    print("  Stage 1 complete.")

    # =====================================================================
    # CONVERGENCE LOOP: STAGE 2 repeated until Y converges
    # =====================================================================
    solver_max_iter = int(p('max_iterations', 50))
    solver_tol = p('tol', 1e-6)
    solver_relax = p('relax', 0.5)
    solver_mode = str(p('solver_mode', 'convergence'))   # 'convergence' or 'fixed'

    YSol_final, convergence_history, residual_histories = run_convergence_loop(
        xspan=xspan,
        Y0=Y0,
        params=params,
        YSol_init=YSol,
        dx=dx,
        max_iterations=solver_max_iter,
        tol=solver_tol,
        relax=solver_relax,
        mode=solver_mode,
    )

    # Przelicz T_aw i M z koncowego rozwiazania
    for i in range(n):
        T_aw_i, M_i = compute_gas_parameters(YSol_final, params, i)
        params['T_aw'][i] = T_aw_i
        params['M'][i] = M_i

    # Wspolczynnik wnikania ciepla strony gazowej (korelacja Bartza)
    params['h_gas'] = compute_bartz_htc(YSol_final, params)
    print(f"  Bartz HTC [W/(m2*K)]: throat={params['h_gas'][int(np.argmin(params['R']))]:.1f}"
          f"  inlet={params['h_gas'][0]:.1f}  exit={params['h_gas'][-1]:.1f}")

    czas_koniec = time.time()
    czas_wykonania = czas_koniec - czas_start
    print(f"Execution time: {czas_wykonania:.2f} seconds")

    # =====================================================================
    # EXPORT RESULTS TO CSV
    # =====================================================================
    converged = (len(convergence_history) == 0
                 or convergence_history[-1] < solver_tol)
    export_results(
        xspan=xspan,
        YSol_final=YSol_final,
        params=params,
        convergence_history=convergence_history,
        params_name=params_name,
        converged=converged,
    )

    print("Simulation completed successfully!")


if __name__ == '__main__':
    if len(sys.argv) > 1:
        main(param_file=sys.argv[1])
    else:
        main()
