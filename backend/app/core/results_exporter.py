"""
results_exporter.py — export the simulation results (gas side) to CSV.

Simplified version: writes what the Ansys grid needs — geometry, gas
properties, the gas flow state and T_aw.
"""

import os
import csv
import numpy as np
from datetime import datetime


from . import RESULTS_DIR


def _next_result_index(params_name):
    """Find the next free index XX for {params_name}_results_XX.csv."""
    os.makedirs(RESULTS_DIR, exist_ok=True)
    for i in range(1, 1000):
        filename = f"{params_name}_results_{i:02d}.csv"
        if not os.path.exists(os.path.join(RESULTS_DIR, filename)):
            return i
    raise RuntimeError("Reached limit of 999 result files.")


def _safe_float(val, fmt='.8g'):
    """Zwroc sformatowany float lub pusty string dla NaN/Inf."""
    if isinstance(val, (float, np.floating, np.integer)):
        if not np.isfinite(float(val)):
            return ''
        return format(float(val), fmt)
    return str(val)


def export_results(xspan, YSol_final, params,
                   convergence_history, params_name='default',
                   converged=True):
    """
    Zapisuje wyniki symulacji (strona gazowa) do pliku CSV.

    Parameters
    ----------
    xspan : np.ndarray — siatka osiowa x [m], ksztalt (n,)
    YSol_final : np.ndarray — koncowe rozwiazanie ODE [N, P, T], ksztalt (n, 3)
    params : dict — parameters and results
    convergence_history : list[float]
    params_name : str
    converged : bool
    """
    os.makedirs(RESULTS_DIR, exist_ok=True)

    idx = _next_result_index(params_name)
    filename = f"{params_name}_results_{idx:02d}.csv"
    filepath = os.path.join(RESULTS_DIR, filename)

    n = len(xspan)
    now = datetime.now()
    iterations_done = len(convergence_history)
    final_conv = convergence_history[-1] if convergence_history else float('nan')

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------
    meta = [
        "# ProPulsN — Simulation results (gas side, no regenerative cooling)",
        "# " + "=" * 60,
        f"# date:               {now.strftime('%Y-%m-%d %H:%M:%S')}",
        f"# params_name:        {params_name}",
        f"# converged:          {converged}",
        f"# iterations:         {iterations_done}",
        f"# final_conv_value:   {_safe_float(final_conv, '.6e')}",
        f"# n_grid_points:      {n}",
        "# ---",
        f"# mdot_gas_kg_s:      {_safe_float(params.get('mdot_gas', float('nan')), '.6g')}",
        f"# R_throat_m:         {_safe_float(params.get('Dt', float('nan')) / 2, '.6g')}",
        f"# A_throat_m2:        {_safe_float(params.get('At', float('nan')), '.6g')}",
        f"# gamma_chamber:      {_safe_float(params.get('gamma', float('nan')), '.6g')}",
        f"# c_star_m_s:         {_safe_float(params.get('c_star', float('nan')), '.6g')}",
        f"# P0_Pa:              {_safe_float(YSol_final[0, 1], '.6g')}",
        f"# T0_K:               {_safe_float(YSol_final[0, 2], '.6g')}",
        f"# eta_Pa_s:           {_safe_float(params.get('eta', float('nan')), '.6g')}",
        f"# epsilon_roughness_m:{_safe_float(params.get('epsilon', float('nan')), '.6g')}",
        "# " + "=" * 60,
        "#",
        "# Load in pandas:",
        f"#   df = pd.read_csv('results/{filename}', comment='#')",
        "#",
    ]

    # ------------------------------------------------------------------
    # Column definitions
    # ------------------------------------------------------------------
    M_arr = np.sqrt(np.abs(YSol_final[:, 0]))

    columns = [
        # ---- Geometry ------------------------------------------------
        ("x_m",             xspan),
        ("r_m",             params['R']),
        ("A_m2",            params['A']),

        # ---- Gas properties (PCHIP interpolated) ---------------------
        ("gamma",           params['gamma_arr']),
        ("Cpcg_J_kgK",     params['Cpcg_arr']),
        ("Prcg_gas",        params['Prcg_arr']),
        ("molar_mass_kg_mol", params['molar_mass_arr']),
        ("Rs_J_kgK",        params['Rs_arr']),

        # ---- Gas flow state ------------------------------------------
        ("M",               M_arr),
        ("N_M2",            YSol_final[:, 0]),
        ("P_Pa",            YSol_final[:, 1]),
        ("T_K",             YSol_final[:, 2]),
        ("T_aw_K",          params['T_aw']),

        # ---- Heat transfer coefficient (Bartz) -----------------------
        ("h_gas_W_m2K",     params['h_gas']),

        # ---- Extra (dynamic viscosity) -------------------------------
        ("eta_Pa_s",        np.full(n, params['eta'])),
    ]

    # ------------------------------------------------------------------
    # Write the file
    # ------------------------------------------------------------------
    with open(filepath, 'w', newline='', encoding='utf-8') as fh:
        for line in meta:
            fh.write(line + '\n')
        fh.write('\n')

        writer = csv.writer(fh)
        writer.writerow([col[0] for col in columns])

        for i in range(n):
            row = []
            for _, arr in columns:
                if hasattr(arr, '__len__'):
                    row.append(_safe_float(arr[i]))
                else:
                    row.append(_safe_float(arr))
            writer.writerow(row)

    print(f"\n  Results saved: {filepath}")
    print(f"  Grid: {n} points  |  Columns: {len(columns)}")
    print(f"  Load: pd.read_csv('results/{filename}', comment='#')")

    return filepath
