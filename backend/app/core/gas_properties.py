"""
gas_properties.py — interpolate gas thermodynamic properties along the nozzle.

gamma, Cpcg, Prcg and the molar mass all vary along the nozzle (combustion
chamber -> throat -> exit). This module builds smooth PCHIP profiles through
the three defining nodes and returns both discrete arrays (for computational
loops) and continuous interpolants (for the ODE solver).

Interpolation method: PCHIP (Piecewise Cubic Hermite Interpolating Polynomial)
  - reproduces the node values EXACTLY (chamber, throat, exit)
  - continuous first derivatives (C1) — no kink at the throat
  - preserves local monotonicity (standard practice in engineering simulation)
  - interpolates over position x [m], nodes at x[0], x[idx_throat], x[-1]

Every value comes from the parameter file. There is no default here and no
"constant along the nozzle" shorthand: all three nodes of every property must
be supplied. `param_schema.require_params()` checks that before the solver
starts, so a missing node is reported by name rather than filled in silently.

Interpolated properties:
  - gamma   (g)     — ratio of specific heats Cp/Cv     [-]
  - Cpcg    (Cp)    — specific heat capacity of the gas [J/(kg*K)]
  - Prcg    (Pr)    — Prandtl number of the gas         [-]
  - combustion_molar_mass (M) — molar mass of the products [kg/mol]

Derived: Rs = Ru / M — specific gas constant [J/(kg*K)], from the molar mass.
"""

import numpy as np
from scipy.interpolate import PchipInterpolator


# Properties interpolated between the three nodes. The parameter file supplies
# every one as {name}_chamber / {name}_throat / {name}_exit.
_PROPS = ('gamma', 'Cpcg', 'Prcg', 'combustion_molar_mass')

_NODES = ('chamber', 'throat', 'exit')

# Universal gas constant [J/(mol*K)]
_Ru = 8.314462618


def _get_3_values(flat, base_key):
    """
    Read the chamber / throat / exit node values for one property.

    Parameters
    ----------
    flat : dict
        The flat {key: value} mapping returned by load_params().
    base_key : str
        Base parameter name (e.g. 'gamma').

    Returns
    -------
    tuple(float, float, float) : (v_chamber, v_throat, v_exit)
    """
    return tuple(float(flat[f'{base_key}_{node}']) for node in _NODES)

def build_gas_property_arrays(flat, xspan, idx_throat):
    """
    Build interpolated gas property profiles over the nozzle grid.

    Interpolation nodes (x position):
      x[0]           -> combustion chamber values (_chamber)
      x[idx_throat]  -> throat values             (_throat)
      x[-1]          -> exit values               (_exit)

    Parameters
    ----------
    flat : dict
        The flat {key: value} mapping returned by load_params(). Every node
        value it needs is guaranteed present by require_params().
    xspan : np.ndarray
        Axial grid x [m], shape (n,).
    idx_throat : int
        Index of the throat point (minimum radius) in the grid.

    Returns
    -------
    dict z kluczami:
        {name}_arr     : np.ndarray (n,) — discrete array for loops
        {name}_interp  : PchipInterpolator — interpolant dla solvera ODE
        {name}_chamber, {name}_throat, {name}_exit : float — node values
        Rs_arr         : np.ndarray (n,) — specific gas constant [J/(kg*K)]
        Rs_interp      : callable(x) → float — Rs(x) dla ODE
    """
    x_nodes = np.array([xspan[0], xspan[idx_throat], xspan[-1]])
    result = {}

    for name in _PROPS:
        v_ch, v_th, v_ex = _get_3_values(flat, name)
        y_nodes = np.array([v_ch, v_th, v_ex])

        interp = PchipInterpolator(x_nodes, y_nodes, extrapolate=True)
        arr = interp(xspan)

        result[f'{name}_arr']     = arr
        result[f'{name}_interp']  = interp
        result[f'{name}_chamber'] = v_ch
        result[f'{name}_throat']  = v_th
        result[f'{name}_exit']    = v_ex

    # Rs = Ru / M_molar — a derived property (the specific gas constant)
    molar_arr    = result['combustion_molar_mass_arr']
    molar_interp = result['combustion_molar_mass_interp']

    result['Rs_arr']    = _Ru / molar_arr
    result['Rs_interp'] = lambda x, _mi=molar_interp: _Ru / float(_mi(x))

    return result


def log_property_nodes(gas_props):
    """
    Print the interpolation node values for every property.
    A diagnostic helper called from main.py.
    """
    print("\n  Gas properties — PCHIP interpolation nodes:")
    print(f"  {'Property':28s} {'Chamber':>12s} {'Throat':>12s} {'Exit':>12s}")
    print("  " + "-" * 68)

    entries = [
        ('gamma [-]',             'gamma'),
        ('Cpcg [J/(kg·K)]',       'Cpcg'),
        ('Prcg [-]',              'Prcg'),
        ('M_molar [kg/mol]',      'combustion_molar_mass'),
        ('Rs [J/(kg·K)]',         None),
    ]

    for label, name in entries:
        if name is not None:
            v_ch = gas_props[f'{name}_chamber']
            v_th = gas_props[f'{name}_throat']
            v_ex = gas_props[f'{name}_exit']
        else:
            # Rs — oblicz z masy molarnej
            v_ch = _Ru / gas_props['combustion_molar_mass_chamber']
            v_th = _Ru / gas_props['combustion_molar_mass_throat']
            v_ex = _Ru / gas_props['combustion_molar_mass_exit']
        print(f"  {label:28s} {v_ch:>12.5g} {v_th:>12.5g} {v_ex:>12.5g}")
    print()
