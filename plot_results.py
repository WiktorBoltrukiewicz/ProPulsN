#!/usr/bin/env python3
"""
plot_results.py — interactive chart builder for simulation result files.

Usage:
    python plot_results.py

Flow:
  1. Pick a result file from results/
  2. Pick the X axis column  (default: x_m, displayed in mm)
  3. Pick the Y axis columns (one or more, e.g. "7,8,9" or "7-9")
  4. The chart opens in a window
  5. After closing it: offer to save, then offer another chart
"""

import os
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')

# ---------------------------------------------------------------------------
# Columns in [m] that are converted to mm for plotting
# (plain lengths only, not areas _m2 or velocities _m_s)
# ---------------------------------------------------------------------------
_MM_COLUMNS = {'x_m', 'r_m'}

# ---------------------------------------------------------------------------
# Readable axis labels for each column
# ---------------------------------------------------------------------------
_LABELS = {
    'x_m':              'x [mm]',
    'r_m':              'r [mm]',
    'A_m2':             'A [m²]',
    'gamma':            'Ratio of specific heats \u03b3 [-]',
    'Cpcg_J_kgK':      'Gas Cp [J/(kg\u00b7K)]',
    'Prcg_gas':         'Gas Pr [-]',
    'molar_mass_kg_mol':'Gas molar mass [kg/mol]',
    'Rs_J_kgK':         'Specific gas constant Rs [J/(kg\u00b7K)]',
    'M':                'Mach number M [-]',
    'N_M2':             'N = M² [-]',
    'P_Pa':             'Gas pressure p [Pa]',
    'T_K':              'Gas temperature T [K]',
    'T_aw_K':           'Adiabatic wall temperature T_aw [K]',
    'eta_Pa_s':         'Dynamic viscosity \u03b7 [Pa\u00b7s]',
}

# ---------------------------------------------------------------------------
# Column groups, for a readable menu
# ---------------------------------------------------------------------------
_GROUPS = [
    ('Geometry',           ['x_m', 'r_m', 'A_m2']),
    ('Gas properties',     ['gamma', 'Cpcg_J_kgK', 'Prcg_gas',
                            'molar_mass_kg_mol', 'Rs_J_kgK']),
    ('Gas flow',           ['M', 'N_M2', 'P_Pa', 'T_K', 'T_aw_K']),
    ('Other',              ['eta_Pa_s']),
]


# ===========================================================================
# Helpers
# ===========================================================================

def _label(col):
    """Return a readable axis label for a column."""
    return _LABELS.get(col, col.replace('_', ' '))


def _get_values(df, col):
    """Return the column values, converting m to mm where appropriate."""
    vals = df[col].values.astype(float)
    if col in _MM_COLUMNS:
        vals = vals * 1000.0
    return vals


# ===========================================================================
# File loading
# ===========================================================================

def _read_metadata(filepath):
    """Parse the metadata block ('# key: value') from a CSV file."""
    meta = {}
    with open(filepath, 'r', encoding='utf-8') as fh:
        for line in fh:
            if not line.startswith('#'):
                break
            line = line[1:].strip()
            if ':' in line:
                key, _, val = line.partition(':')
                meta[key.strip()] = val.strip()
    return meta


def _list_result_files():
    """Return a sorted list of CSV files from results/."""
    if not os.path.isdir(RESULTS_DIR):
        return []
    return sorted(
        os.path.join(RESULTS_DIR, f)
        for f in os.listdir(RESULTS_DIR)
        if f.endswith('.csv')
    )


# ===========================================================================
# Interaktywne wybory
# ===========================================================================

def select_result_file():
    """Show the file list and let the user pick one."""
    files = _list_result_files()

    if not files:
        print(f"\n  No result files in: {RESULTS_DIR}")
        print("  Run a simulation first (python main.py).")
        return None

    print("\n" + "=" * 65)
    print("  SELECT A RESULT FILE")
    print("=" * 65)

    for i, fp in enumerate(files, 1):
        meta = _read_metadata(fp)
        fname  = os.path.basename(fp)
        date   = meta.get('date', '?')
        conv   = meta.get('converged', '?')
        iters  = meta.get('iterations', '?')
        params = meta.get('params_name', '?')
        print(f"  [{i:2d}] {fname}")
        print(f"        parametry: {params}  |  data: {date}")
        print(f"        converged: {conv}  |  iterations: {iters}")

    print("-" * 65)

    while True:
        try:
            raw = input(f"Wybierz plik (1–{len(files)}): ").strip()
            idx = int(raw) - 1
            if 0 <= idx < len(files):
                return files[idx]
            print(f"  Enter a number from 1 to {len(files)}.")
        except ValueError:
            print("  Podaj numer pliku.")
        except (EOFError, KeyboardInterrupt):
            return None


def _build_index_map(df):
    """
    Przypisz numery do kolumn zgodnie z grupami.
    Zwraca dict {numer: nazwa_kolumny}.
    """
    cols_available = set(df.columns)
    index_map = {}
    idx = 1

    for _, group_cols in _GROUPS:
        for col in group_cols:
            if col in cols_available:
                index_map[idx] = col
                idx += 1

    # Columns outside the known groups (future extensions)
    assigned = {c for _, gc in _GROUPS for c in gc}
    for col in df.columns:
        if col not in assigned:
            index_map[idx] = col
            idx += 1

    return index_map


def display_columns(df, index_map):
    """Show the available columns as a grouped table."""
    cols_available = set(df.columns)
    reverse = {v: k for k, v in index_map.items()}

    print()
    print("  Available parameters:")
    print("  " + "-" * 61)

    for group_name, group_cols in _GROUPS:
        present = [c for c in group_cols if c in cols_available]
        if not present:
            continue
        print(f"  {group_name}:")
        for col in present:
            num = reverse[col]
            note = '  (→ mm)' if col in _MM_COLUMNS else ''
            print(f"    [{num:2d}] {col:22s}  {_label(col)}{note}")

    # Nieprzypisane
    assigned = {c for _, gc in _GROUPS for c in gc}
    extra = [c for c in df.columns if c not in assigned]
    if extra:
        print("  Inne:")
        for col in extra:
            num = reverse[col]
            print(f"    [{num:2d}] {col:22s}  {_label(col)}")

    print("  " + "-" * 61)


def _parse_selection(raw, index_map, multi=True):
    """
    Parse a number spec: "7,8,9" or "7-9" or "7, 9-12, 15".
    Returns the column names in the order selected.
    """
    selected = []
    for token in raw.replace(' ', '').split(','):
        if '-' in token and multi:
            parts = token.split('-', 1)
            try:
                a, b = int(parts[0]), int(parts[1])
                for n in range(a, b + 1):
                    if n in index_map and index_map[n] not in selected:
                        selected.append(index_map[n])
            except ValueError:
                pass
        else:
            try:
                n = int(token)
                if n in index_map and index_map[n] not in selected:
                    selected.append(index_map[n])
            except ValueError:
                pass
    return selected


def select_x_axis(df, index_map):
    """
    Pick the X axis column.
    Default: x_m (displayed in mm).
    """
    default_col = 'x_m' if 'x_m' in df.columns else list(index_map.values())[0]
    default_num = next((k for k, v in index_map.items() if v == default_col), 1)

    print(f"\n  X axis — enter a number  (default [{default_num}] = {_label(default_col)}):")
    try:
        raw = input(f"  X [{default_num}]: ").strip()
    except (EOFError, KeyboardInterrupt):
        return default_col

    if not raw:
        return default_col

    result = _parse_selection(raw, index_map, multi=False)
    if result:
        return result[0]

    print(f"  Invalid choice — using the default: {default_col}")
    return default_col


def select_y_axes(df, index_map):
    """
    Pick the Y axis columns (one or more).
    Wpisz numery oddzielone przecinkami lub zakresy, np. "7,8,9" / "7-9".
    """
    print("  Y axis — enter column numbers (commas or ranges, e.g. 7,8 or 7-9):")
    while True:
        try:
            raw = input("  Y: ").strip()
        except (EOFError, KeyboardInterrupt):
            return []

        if not raw:
            print("  Podaj co najmniej jeden numer kolumny.")
            continue

        result = _parse_selection(raw, index_map, multi=True)
        if result:
            return result

        print("  No column recognised. Try again.")


# ===========================================================================
# Chart building
# ===========================================================================

def make_chart(df, x_col, y_cols, meta):
    """
    Build the matplotlib chart and return the figure.

    With a single Y series the Y axis carries that series' full label. With
    several, the Y axis reads 'Value' and a legend identifies the series.
    """
    x_vals  = _get_values(df, x_col)
    x_label = _label(x_col)

    fig, ax = plt.subplots(figsize=(11, 6))

    for col in y_cols:
        y_vals = _get_values(df, col)
        ax.plot(x_vals, y_vals, linewidth=1.8, label=_label(col))

    ax.set_xlabel(x_label, fontsize=12)

    if len(y_cols) == 1:
        ax.set_ylabel(_label(y_cols[0]), fontsize=12)
    else:
        ax.set_ylabel('Value', fontsize=12)
        ax.legend(fontsize=10, loc='best')

    # Title from the file metadata
    params_name = meta.get('params_name', '')
    date        = meta.get('date', '?')
    conv        = meta.get('converged', '?')
    iters       = meta.get('iterations', '?')

    title    = f"ProPulsN — {params_name}"
    subtitle = f"run date: {date}  |  converged: {conv}  |  iterations: {iters}"
    ax.set_title(f"{title}\n{subtitle}", fontsize=11)

    ax.grid(True, alpha=0.35)
    fig.tight_layout()
    return fig


# ===========================================================================
# Chart saving
# ===========================================================================

def ask_save_chart(fig, params_name):
    """Ask whether to save the chart, and in which format."""
    try:
        ans = input("\n  Save the chart to a file? (y/n, default: n): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return

    if ans != 'y':
        return

    default_name = f"{params_name}_plot"
    try:
        name = input(f"  File name without extension (default '{default_name}'): ").strip()
    except (EOFError, KeyboardInterrupt):
        name = ''

    if not name:
        name = default_name

    safe_name = "".join(c for c in name if c.isalnum() or c in ('_', '-', '.'))
    if not safe_name:
        safe_name = default_name

    print("  Format zapisu:  [1] PNG   [2] PDF   [3] SVG")
    try:
        fmt = input("  Format [1]: ").strip()
    except (EOFError, KeyboardInterrupt):
        fmt = '1'

    ext = {' ': '.png', '': '.png', '1': '.png', '2': '.pdf', '3': '.svg'}.get(fmt, '.png')

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, safe_name + ext)
    fig.savefig(out_path, dpi=150, bbox_inches='tight')
    print(f"  Zapisano: {out_path}")


# ===========================================================================
# Main program loop
# ===========================================================================

def main():
    print("\n" + "=" * 65)
    print("  OPENENGINE — CHART BUILDER")
    print("=" * 65)

    # --- File selection ---
    filepath = select_result_file()
    if filepath is None:
        print("\n  Anulowano.")
        return

    df, meta = pd.read_csv(filepath, comment='#'), _read_metadata(filepath)
    # (re-read with pandas, to be sure the dtypes are numeric)
    df = pd.read_csv(filepath, comment='#')

    index_map = _build_index_map(df)

    fname = os.path.basename(filepath)
    print(f"\n  Plik:       {fname}")
    print(f"  Parametry:  {meta.get('params_name', '?')}")
    print(f"  Data:       {meta.get('date', '?')}")
    print(f"  Grid:       {len(df)} points  |  Columns: {len(df.columns)}")

    params_name = meta.get('params_name', 'results')

    # --- Chart loop ---
    while True:
        display_columns(df, index_map)

        x_col  = select_x_axis(df, index_map)
        y_cols = select_y_axes(df, index_map)

        if not y_cols:
            print("  Brak wybranych kolumn Y — pomijam.")
        else:
            print(f"\n  Plotting: X = {_label(x_col)}")
            print(f"          Y = {', '.join(_label(c) for c in y_cols)}")

            fig = make_chart(df, x_col, y_cols, meta)
            plt.show(block=True)          # blocks until the window is closed

            ask_save_chart(fig, params_name)
            plt.close(fig)

        # --- Another chart? ---
        print()
        try:
            again = input("  Build another chart? (y/n, default: n): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            again = 'n'

        if again != 'y':
            print("\n  Do widzenia!\n")
            break


if __name__ == '__main__':
    main()
