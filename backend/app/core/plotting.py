"""
plotting.py — Final simulation result plots (gas side).

Generates 2 figures:
  1. Gas parameters (N, P, T) — profile along the nozzle
  2. Adiabatic wall temperature (T_aw) + static gas temperature
"""

import matplotlib.pyplot as plt
import numpy as np


def plot_final_results(xspan, YSol2, params, idx_throat):
    """
    Draw final plots after the full computation cycle.

    Parameters
    ----------
    xspan      : np.ndarray — axial grid [m]
    YSol2      : np.ndarray, shape (n, 3) — final ODE solution [N, P, T]
    params     : dict — engine parameters
    idx_throat : int — throat index
    """
    x_throat = xspan[idx_throat]

    # ===================================================================
    # FIGURE 1: Gas parameters (N, pressure, temperature)
    # ===================================================================
    fig1, axes1 = plt.subplots(3, 1, figsize=(10, 10))
    fig1.suptitle('Gas Parameters (Stage 2 — with friction)', fontsize=14)

    # N = M^2
    axes1[0].plot(xspan, YSol2[:, 0], 'b-', linewidth=2)
    axes1[0].axhline(y=1, color='r', linestyle='--', label='Mach = 1')
    axes1[0].axvline(x=x_throat, color='k', linestyle=':', alpha=0.7, label='Throat')
    axes1[0].set_xlabel('x [m]')
    axes1[0].set_ylabel('N (Mach²) [-]')
    axes1[0].set_title('Mach Number Squared Profile (N)')
    axes1[0].legend()
    axes1[0].grid(True)

    # Pressure [bar]
    axes1[1].plot(xspan, YSol2[:, 1] / 1e5, 'g-', linewidth=2)
    axes1[1].axvline(x=x_throat, color='k', linestyle=':', alpha=0.7)
    axes1[1].set_xlabel('x [m]')
    axes1[1].set_ylabel('Pressure P [bar]')
    axes1[1].set_title('Static Pressure Profile')
    axes1[1].grid(True)

    # Temperature [K]
    axes1[2].plot(xspan, YSol2[:, 2], 'r-', linewidth=2)
    axes1[2].axvline(x=x_throat, color='k', linestyle=':', alpha=0.7)
    axes1[2].set_xlabel('x [m]')
    axes1[2].set_ylabel('Temperature T [K]')
    axes1[2].set_title('Exhaust Gas Temperature Profile')
    axes1[2].grid(True)

    fig1.tight_layout()

    # ===================================================================
    # FIGURE 2: T_aw and static temperature
    # ===================================================================
    fig2, ax2 = plt.subplots(figsize=(10, 6))

    ax2.plot(xspan, params['T_aw'], 'r-', linewidth=2,
             label='T_aw (adiabatic wall temperature)')
    ax2.plot(xspan, YSol2[:, 2], 'b--', linewidth=2,
             label='T (static gas temperature)')
    ax2.axvline(x=x_throat, color='k', linestyle=':', alpha=0.7, label='Throat')

    ax2.set_xlabel('Axial position x [m]')
    ax2.set_ylabel('Temperature [K]')
    ax2.set_title('Adiabatic Wall Temperature vs. Static Gas Temperature')
    ax2.legend(loc='best')
    ax2.grid(True)

    fig2.tight_layout()

    plt.show()
