"""
param_loader.py — Loading and managing rocket engine parameter files.

Handles:
  - searching for parameter files (.json) in the params/ directory
  - interactive parameter file selection
  - loading parameters from a JSON file
  - interactive parameter editing before running the simulation
  - saving modified parameters to a new file
"""

import json
import os
import glob


from . import PARAMS_DIR
from .param_schema import has_value, normalise_raw


def find_param_files():
    """
    Search for parameter files (.json) in the params/ directory.

    Returns
    -------
    list[str] : list of paths to parameter files
    """
    pattern = os.path.join(PARAMS_DIR, '*.json')
    files = sorted(glob.glob(pattern))
    return files


def select_param_file():
    """
    Interactive parameter file selection.

    Returns
    -------
    str : path to the selected file
    """
    files = find_param_files()

    if not files:
        print(f"No parameter files found in: {PARAMS_DIR}")
        print("Create a .json file in the params/ directory following the template.")
        return None

    print("\n" + "=" * 60)
    print("  SELECT PARAMETER FILE")
    print("=" * 60)

    for i, f in enumerate(files, 1):
        name = os.path.basename(f)
        try:
            with open(f, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            meta = data.get('_meta', {})
            meta_name = meta.get('name', meta.get('nazwa', ''))
            if meta_name:
                print(f"  [{i}] {name}  —  {meta_name}")
            else:
                print(f"  [{i}] {name}")
        except (json.JSONDecodeError, IOError):
            print(f"  [{i}] {name}  (read error)")

    print("-" * 60)

    while True:
        try:
            choice = input(f"Select file (1-{len(files)}): ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(files):
                print(f"  Selected: {os.path.basename(files[idx])}")
                return files[idx]
            else:
                print(f"  Enter a number from 1 to {len(files)}.")
        except ValueError:
            print("  Enter the file number.")
        except (EOFError, KeyboardInterrupt):
            print("\n  Selection cancelled.")
            return None


def load_params(filepath):
    """
    Load parameters from a JSON file.

    Parameters
    ----------
    filepath : str
        Path to the JSON parameter file.

    Returns
    -------
    dict : flat dictionary of parameters (key → value)
    dict : full JSON structure (for optional saving)
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        raw = json.load(f)

    # Files written before the app was translated use Polish keys; rewrite them
    # to the English vocabulary so everything downstream sees one shape.
    raw = normalise_raw(raw)

    # Extract flat values from the nested structure
    flat = {}
    for section_key, section in raw.items():
        if section_key == '_meta':
            continue
        if not isinstance(section, dict):
            continue
        for param_key, param_data in section.items():
            if param_key.startswith('_'):
                continue
            if has_value(param_data):
                flat[param_key] = param_data['value']

    return flat, raw


def display_params(raw_data):
    """
    Display all parameters in a readable format.

    Parameters
    ----------
    raw_data : dict
        Full JSON structure with parameters.
    """
    print("\n" + "=" * 70)
    print("  LOADED PARAMETERS")
    print("=" * 70)

    param_index = 0
    index_map = {}  # number → (section_key, param_key)

    for section_key, section in raw_data.items():
        if section_key == '_meta':
            continue
        if not isinstance(section, dict):
            continue

        section_desc = section.get('_description', section_key)
        print(f"\n  --- {section_desc} ---")

        for param_key, param_data in section.items():
            if param_key.startswith('_'):
                continue
            if has_value(param_data):
                param_index += 1
                val = param_data['value']
                unit = param_data.get('unit', '')
                desc = param_data.get('description', '')
                index_map[param_index] = (section_key, param_key)

                if isinstance(val, float) and (abs(val) >= 1e6 or (abs(val) < 1e-3 and val != 0)):
                    val_str = f"{val:.4e}"
                else:
                    val_str = str(val)

                print(f"  [{param_index:2d}] {param_key:25s} = {val_str:>14s} {unit:10s}  | {desc}")

    print("-" * 70)
    return index_map


def edit_params_interactive(raw_data):
    """
    Interactively edit parameters before simulation.

    Parameters
    ----------
    raw_data : dict
        Full JSON structure (modified in-place).

    Returns
    -------
    bool : True if changes were made, False otherwise
    """
    index_map = display_params(raw_data)
    total = len(index_map)

    print("\n  To change a parameter, enter its number.")
    print("  Type 'q' or press Enter to continue to simulation.")
    print("  Type 's' to save changes to a new file.\n")

    changed = False

    while True:
        try:
            choice = input("Change parameter (number/q/s): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n  Continuing...")
            break

        if choice in ('q', ''):
            break

        if choice == 's':
            save_params_interactive(raw_data)
            continue

        try:
            idx = int(choice)
            if idx < 1 or idx > total:
                print(f"  Enter a number from 1 to {total}.")
                continue
        except ValueError:
            print("  Enter a parameter number, 'q', or 's'.")
            continue

        section_key, param_key = index_map[idx]
        param_data = raw_data[section_key][param_key]
        old_val = param_data['value']
        unit = param_data.get('unit', '')
        desc = param_data.get('description', '')

        print(f"\n  {param_key}: {old_val} {unit}")
        print(f"  Description: {desc}")

        try:
            new_val_str = input(f"  New value (Enter = no change): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Cancelled.")
            continue

        if not new_val_str:
            print("  Value unchanged.")
            continue

        try:
            if isinstance(old_val, int) and '.' not in new_val_str and 'e' not in new_val_str.lower():
                new_val = int(new_val_str)
            else:
                new_val = float(new_val_str)
        except ValueError:
            print(f"  Error: '{new_val_str}' is not a valid number.")
            continue

        param_data['value'] = new_val
        changed = True
        print(f"  Changed: {param_key} = {old_val} → {new_val} {unit}")

    return changed


def save_params_interactive(raw_data):
    """
    Save parameters to a new JSON file.

    Parameters
    ----------
    raw_data : dict
        Full JSON structure with parameters.
    """
    print(f"\n  Save directory: {PARAMS_DIR}")

    try:
        name = input("  File name (without .json): ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n  Save cancelled.")
        return

    if not name:
        print("  Save cancelled (empty name).")
        return

    safe_name = "".join(c for c in name if c.isalnum() or c in ('_', '-', '.'))
    if not safe_name:
        print("  Invalid file name.")
        return

    filepath = os.path.join(PARAMS_DIR, f"{safe_name}.json")

    if os.path.exists(filepath):
        try:
            overwrite = input(f"  File {safe_name}.json already exists. Overwrite? (y/n): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n  Save cancelled.")
            return
        if overwrite != 'y':
            print("  Save cancelled.")
            return

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(raw_data, f, ensure_ascii=False, indent=4)

    print(f"  Saved: {filepath}")


def load_and_select_params():
    """
    Main function: select file → load → optional editing.

    Returns
    -------
    dict : flat parameter dictionary (key → value), or None if cancelled
    str  : path to the selected file, or None if cancelled
    """
    filepath = select_param_file()
    if filepath is None:
        return None, None

    flat, raw = load_params(filepath)

    print(f"\n  Loaded {len(flat)} parameters from file.")

    try:
        edit_choice = input("  Edit parameters before running? (y/n, default: n): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        edit_choice = 'n'

    if edit_choice == 'y':
        changed = edit_params_interactive(raw)
        if changed:
            flat, _ = load_params_from_raw(raw)

    return flat, filepath


def load_params_from_raw(raw_data):
    """
    Extract flat values from a full JSON structure.

    Parameters
    ----------
    raw_data : dict
        Full JSON structure.

    Returns
    -------
    dict : flat dictionary (key → value)
    dict : original full structure
    """
    raw_data = normalise_raw(raw_data)
    flat = {}
    for section_key, section in raw_data.items():
        if section_key == '_meta':
            continue
        if not isinstance(section, dict):
            continue
        for param_key, param_data in section.items():
            if param_key.startswith('_'):
                continue
            if has_value(param_data):
                flat[param_key] = param_data['value']
    return flat, raw_data
