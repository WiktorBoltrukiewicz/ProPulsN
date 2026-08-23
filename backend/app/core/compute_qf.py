"""
compute_qf.py — friction profile F(x) of the exhaust gas in the nozzle.

Simplified version (no heat transfer). Computes gas friction losses only —
the input to the full ODE (Stage 2).

Corresponds to computeF in the original MATLAB code.
"""

import numpy as np
from scipy.integrate import cumulative_trapezoid


def compute_F(xspan, YSol, params):
    """
    Compute the friction loss profile along the nozzle.

    Evaluates the friction factor at every point and derives the pressure
    gradient due to friction.

    Parameters
    ----------
    xspan : np.ndarray — axial positions [m]
    YSol : np.ndarray, shape (n, 3) — ODE solution [N, P, T]
    params : dict — engine parameters

    Returns
    -------
    Fx : np.ndarray — cumulative friction losses
    f_gas : np.ndarray — Darcy friction factor
    Re_gas : np.ndarray — gas Reynolds number
    V_gas : np.ndarray — gas velocity [m/s]
    dFdx : np.ndarray — derivative of F with respect to x
    """
    N = YSol[:, 0]
    P = YSol[:, 1]
    T = YSol[:, 2]

    M = np.sqrt(N)
    gamma_arr = params['gamma_arr']
    Rs_arr = params['Rs_arr']
    sonvel = np.sqrt(gamma_arr * Rs_arr * T)
    V_gas = M * sonvel
    D = params['D']

    rho = P / (Rs_arr * T)
    mu = params['eta']
    eps = params['epsilon']

    Re_gas = rho * V_gas * D / mu

    f_laminar = 64.0 / Re_gas
    f_turbulent = 0.25 / (np.log10(eps / (3.7 * D) + 5.74 / Re_gas**0.9))**2

    f_gas = np.where(Re_gas < 2300, f_laminar, f_turbulent)

    dFdx = f_gas * V_gas ** 2 / (2 * D)
    Fx = cumulative_trapezoid(dFdx, xspan, initial=0)

    return Fx, f_gas, Re_gas, V_gas, dFdx
