"""
parameters.py — gas-side physical quantities at a point along the nozzle.

Simplified version (no regenerative cooling). Computes what the Ansys grid
export needs:
  - adiabatic wall temperature (T_aw)
  - Mach number (M)
  - gas-side heat transfer coefficient h_gas (Bartz correlation)
"""

import numpy as np


def compute_gas_parameters(YSol, params, i):
    """
    Compute the gas-side quantities at grid point i.

    Parameters
    ----------
    YSol : np.ndarray, shape (n, 3) — ODE solution [N, P, T]
    params : dict — all engine parameters
    i : int — point index (0-indexed)

    Returns
    -------
    T_aw : float — adiabatic wall temperature [K]
    M : float — Mach number [-]
    """
    gamma = params['gamma_arr'][i]
    Prcg = params['Prcg_arr'][i]

    N = YSol[i, 0]
    Ts = YSol[i, 2]

    # --- Temperatura adiabatyczna scianki ---
    T_aw = Ts * (
        (1 + Prcg ** 0.33 * ((gamma - 1) / 2) * N)
        / (1 + ((gamma - 1) / 2) * N)
    )

    M = np.sqrt(N)

    return T_aw, M


def compute_bartz_htc(YSol, params):
    """
    Bartz correlation: gas-side heat transfer coefficient h_gas(x) [W/(m²·K)].

    h = 0.026 / D_t^0.2 * (mu^0.2 * Cp / Pr^0.6) * (mdot / A_t)^0.8
        * (A_t / A)^0.9 * sigma

    sigma correction (T_w = T_aw approximation — conservative for unknown wall temp):
      sigma = [(T_aw + T_s) / (2 * T_s)]^-0.68
              * [1 + (gamma-1)/2 * M²]^-0.12

    Parameters
    ----------
    YSol   : np.ndarray, shape (n, 3) — final ODE solution [N, P, T]
    params : dict — must contain T_aw, gamma_arr, Cpcg_arr, Prcg_arr,
                    A, At, Dt, eta, mdot_gas

    Returns
    -------
    h_gas : np.ndarray, shape (n,) — gas-side HTC [W/(m²·K)]
    """
    N_arr  = YSol[:, 0]               # M²
    Ts_arr = YSol[:, 2]               # static temperature [K]
    T_aw   = params['T_aw']           # adiabatic wall temperature [K]
    gamma  = params['gamma_arr']
    Cp     = params['Cpcg_arr']       # [J/(kg·K)]
    Pr     = params['Prcg_arr']
    A      = params['A']              # local area [m²]
    At     = params['At']             # throat area [m²]
    Dt     = params['Dt']             # throat diameter [m]
    mu     = params['eta']            # dynamic viscosity [Pa·s]
    mdot   = params['mdot_gas']       # mass flow rate [kg/s]

    G_t = mdot / At                   # mass flux at throat [kg/(m²·s)]

    h_base = (
        (0.026 / Dt ** 0.2)
        * (mu ** 0.2 * Cp / Pr ** 0.6)
        * G_t ** 0.8
        * (At / A) ** 0.9
    )

    sigma = (
        ((T_aw + Ts_arr) / (2.0 * Ts_arr)) ** (-0.68)
        * (1.0 + 0.5 * (gamma - 1.0) * N_arr) ** (-0.12)
    )

    return h_base * sigma
