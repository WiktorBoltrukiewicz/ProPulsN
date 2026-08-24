"""
results.py — reading result CSVs and building the wall-export point cloud.

Ported from the old Qt ResultsTab. The maths here (revolve angles, the
x/r -> X/Y/Z transform, the Fluent field mapping and its T_K/T_aw_K conflict
rule, the .prof format) is carried over unchanged; only the UI around it is
gone.
"""

import csv
import os
from typing import Optional

import numpy as np

from ..core import RESULTS_DIR

# Columns that describe position rather than a flow property.
COORD_COLS = {"x_m", "r_m"}

# ProPulsN column -> the Fluent profile field it feeds.
# T_K and T_aw_K deliberately collide; resolve_fluent_fields() breaks the tie.
FLUENT_FIELD_MAP = {
    "T_K": "temperature",
    "T_aw_K": "temperature",
    "P_Pa": "pressure",
    "M": "mach-number",
    "h_gas_W_m2K": "heat-transfer-coefficient",
}


def safe_results_path(filename: str) -> str:
    """Resolve `filename` inside results/, refusing anything that escapes it.

    The desktop app could trust its own file dialog; a web server cannot, so
    path traversal ("../../etc/passwd") is rejected here.
    """
    if not filename:
        raise ValueError("No filename given.")
    if os.path.basename(filename) != filename:
        raise ValueError(f"Invalid filename: {filename!r}")
    path = os.path.abspath(os.path.join(RESULTS_DIR, filename))
    if os.path.dirname(path) != os.path.abspath(RESULTS_DIR):
        raise ValueError(f"Invalid filename: {filename!r}")
    return path


def list_result_files() -> list:
    """Every .csv in results/, sorted — the old file dropdown's contents."""
    os.makedirs(RESULTS_DIR, exist_ok=True)
    return sorted(f for f in os.listdir(RESULTS_DIR) if f.endswith(".csv"))


def read_results_csv(filepath: str):
    """Read a results CSV, skipping the '#' metadata preamble.

    Returns (data, headers) where data maps column name -> float array.
    Unparseable cells become NaN, matching the old reader.
    """
    rows, headers = [], None
    with open(filepath, "r", encoding="utf-8") as fh:
        for row in csv.reader(fh):
            if not row or row[0].strip().startswith("#"):
                continue
            if headers is None:
                headers = [h.strip() for h in row]
            else:
                rows.append(row)

    if not headers:
        raise ValueError("No header row found in the CSV file.")

    data = {}
    for i, col in enumerate(headers):
        values = []
        for row in rows:
            cell = row[i].strip() if i < len(row) else ""
            try:
                values.append(float(cell) if cell else float("nan"))
            except ValueError:
                values.append(float("nan"))
        data[col] = np.array(values, dtype=float)
    return data, headers


def parse_revolve_angles(
    enabled: bool = True,
    start_deg: float = 0.0,
    end_deg: float = 360.0,
    n_planes: int = 36,
) -> np.ndarray:
    """The revolve plane angles, in radians.

    A full 360° sweep drops the duplicate end plane (endpoint=False) so the
    seam isn't exported twice; a partial arc keeps both ends.
    """
    if not enabled:
        return np.array([0.0])
    if n_planes < 1:
        raise ValueError("Number of planes must be at least 1.")
    if end_deg <= start_deg:
        raise ValueError("End angle must be greater than start angle.")

    full_circle = abs(end_deg - start_deg) >= 359.9
    return np.linspace(
        np.radians(start_deg),
        np.radians(end_deg),
        n_planes,
        endpoint=not full_circle,
    )


def generate_wall_points(
    data: dict,
    selected_cols: Optional[list] = None,
    enabled: bool = True,
    start_deg: float = 0.0,
    end_deg: float = 360.0,
    n_planes: int = 36,
) -> dict:
    """Revolve the 2D profile around the X axis into a 3D point cloud.

    X = x_m, Y = r_m·cos(theta), Z = r_m·sin(theta) — the engine axis is X.
    Property columns are repeated once per plane so they line up with the
    flattened coordinate arrays.
    """
    if not data:
        raise ValueError("No data loaded.")
    if "x_m" not in data or "r_m" not in data:
        raise ValueError("The loaded file must contain 'x_m' and 'r_m' columns.")

    selected_cols = list(selected_cols or [])
    for col in selected_cols:
        if col not in data:
            raise ValueError(f"Column not found in file: {col}")

    angles_rad = parse_revolve_angles(enabled, start_deg, end_deg, n_planes)

    x_arr = data["x_m"]
    r_arr = data["r_m"]
    n_pts = len(x_arr)
    n_planes_actual = len(angles_rad)
    total = n_pts * n_planes_actual

    X = np.empty(total)
    Y = np.empty(total)
    Z = np.empty(total)
    props = {col: np.empty(total) for col in selected_cols}

    idx = 0
    for theta in angles_rad:
        cos_t = np.cos(theta)
        sin_t = np.sin(theta)
        sl = slice(idx, idx + n_pts)
        X[sl] = x_arr
        Y[sl] = r_arr * cos_t
        Z[sl] = r_arr * sin_t
        for col in selected_cols:
            props[col][sl] = data[col]
        idx += n_pts

    return {
        "X": X,
        "Y": Y,
        "Z": Z,
        "props": props,
        "n_pts": n_pts,
        "n_planes": n_planes_actual,
    }


def resolve_fluent_fields(selected_cols: list):
    """Map selected columns to Fluent field names, breaking the temperature tie.

    T_K and T_aw_K both feed Fluent's 'temperature'. The old export kept
    T_aw_K (adiabatic wall temperature) and told the user; we return which
    column won so the event can say the same.
    """
    selected = {
        col: FLUENT_FIELD_MAP[col]
        for col in selected_cols
        if col in FLUENT_FIELD_MAP
    }
    if not selected:
        raise ValueError("Select at least one Fluent-recognised field to export.")

    resolved = None
    temp_cols = [c for c, field in selected.items() if field == "temperature"]
    if len(temp_cols) > 1:
        for col in temp_cols:
            if col != "T_aw_K":
                del selected[col]
        resolved = "T_aw_K"

    return selected, resolved


def _write_field(fh, name: str, values) -> None:
    fh.write(f"({name}\n")
    for value in values:
        fh.write(f"{value:.8g}\n")
    fh.write(")\n")


def write_fluent_profile(
    out_path: str,
    points: dict,
    selected: dict,
    operating_pressure_pa: float = 101325.0,
) -> int:
    """Write the point cloud as a Fluent ASCII .prof file. Returns point count.

    Pressure is written as gauge pressure (absolute minus Fluent's operating
    pressure), matching the old exporter.
    """
    n_total = points["n_pts"] * points["n_planes"]
    profile_name = os.path.splitext(os.path.basename(out_path))[0].replace(" ", "-")

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(f"(({profile_name} point {n_total})\n")
        _write_field(fh, "x", points["X"])
        _write_field(fh, "y", points["Y"])
        _write_field(fh, "z", points["Z"])
        for col, fluent_name in selected.items():
            values = points["props"][col].copy()
            if fluent_name == "pressure":
                values = values - operating_pressure_pa
            _write_field(fh, fluent_name, values)
        fh.write(")\n")

    return n_total


def unique_results_path(stem: str, extension: str) -> str:
    """results/<stem>_NN.<ext>, picking the first free NN (matches export_dxf)."""
    os.makedirs(RESULTS_DIR, exist_ok=True)
    for i in range(1, 100):
        path = os.path.join(RESULTS_DIR, f"{stem}_{i:02d}.{extension}")
        if not os.path.exists(path):
            return path
    return os.path.join(RESULTS_DIR, f"{stem}_99.{extension}")
