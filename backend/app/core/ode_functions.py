"""
ode_functions.py — right-hand sides of the rocket engine ODEs.

Two versions of the ODE system:
  1. my_nozzle_ode       — simplified (nozzle geometry only)
  2. my_nozzle_ode_full2 — full (with friction and heat transfer)

State vector Y = [N, P, T]:
  N — Mach number squared (M^2)
  P — static pressure [Pa]
  T — static temperature [K]

Corresponds to myNozzleODE, myNozzleODEfull2 and eventN1 in the original
MATLAB code.
"""

import numpy as np


def my_nozzle_ode(x, Y, params):
    """
    Simplified ODE: isentropic flow through a nozzle of varying section.

    The equations depend only on A(x) and dA/dx — no friction, no heat.
    Gamma is interpolated locally at x (PCHIP).
    """
    N, P, T = Y
    gamma = float(params['gamma_interp'](x))

    A = params['A_func'](x)
    dA = params['dA_func'](x)

    # Mach number squared
    dNdx = -(N / (1 - N)) * ((2 + (gamma - 1) * N) / A) * dA
    # Pressure
    dPdx = (P / (1 - N)) * ((gamma * N) / A) * dA
    # Temperature
    dTdx = (T / (1 - N)) * (((gamma - 1) * N) / A) * dA

    return [dNdx, dPdx, dTdx]


def my_nozzle_ode_full2(x, Y, params, dQdx_fun, dFdx_fun):
    """
    Full ODE: flow including heat transfer (dQ/dx) and friction (dF/dx).

    dQdx_fun, dFdx_fun — interpolants computed beforehand from the cooling
    profile. Gamma, Cp and Rs are interpolated locally at x (PCHIP).
    """
    N_2, P_2, T_2 = Y
    gamma = float(params['gamma_interp'](x))
    Cp    = float(params['Cpcg_interp'](x))
    Rs    = float(params['Rs_interp'](x))

    A = params['A_func'](x)
    dA = params['dA_func'](x)
    dq = -dQdx_fun(x)       # negative: heat leaves the gas
    df = dFdx_fun(x)

    tolN = 1e-10
    if not (np.isfinite(dq) and np.isfinite(df) and A > 0
            and T_2 > 0 and abs(1 - N_2) > tolN):
        raise ValueError(
            f"Bad domain at x={x}: A={A}, T={T_2}, |1-N2|={abs(1-N_2)}, dq={dq}, df={df}"
        )

    dNdx = (N_2 / (1 - N_2)) * (
        ((1 + gamma * N_2) / (Cp * T_2)) * dq
        + ((2 + (gamma - 1) * N_2) / (Rs * T_2)) * df
        - ((2 + (gamma - 1) * N_2) / A) * dA
    )

    dPdx = (
        -(P_2 / (1 - N_2)) * ((gamma * N_2) / (Cp * T_2)) * dq
        - (P_2 / (1 - N_2)) * ((1 + (gamma - 1) * N_2) / (Rs * T_2)) * df
        + (P_2 / (1 - N_2)) * ((gamma * N_2) / A) * dA
    )

    dTdx = (
        (T_2 / (1 - N_2)) * ((1 - gamma * N_2) / (Cp * T_2)) * dq
        - (T_2 / (1 - N_2)) * (((gamma - 1) * N_2) / (Rs * T_2)) * df
        + (T_2 / (1 - N_2)) * (((gamma - 1) * N_2) / A) * dA
    )

    return [dNdx, dPdx, dTdx]


def event_N1(x, Y, *args):
    """
    Event: N = 1, i.e. Mach = 1 — the sonic barrier.

    The ODE solver stops when this function returns 0.
    """
    return Y[0] - 1.0


# Attributes required by scipy.integrate.solve_ivp
event_N1.terminal = True    # stop the solver on detection
event_N1.direction = 1      # only detect N crossing 1 from below
