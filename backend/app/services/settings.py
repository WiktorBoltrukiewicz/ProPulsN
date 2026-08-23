"""
settings.py — read/write settings.json at the repo root.

Only the DXF export options survive the move to the browser. `base_font` was
Qt font-scaling and has no browser equivalent (use zoom), so it is dropped —
and stripped on write if an old file still carries it.
"""

import json
import os

from ..core import REPO_ROOT

SETTINGS_PATH = os.path.join(REPO_ROOT, "settings.json")

DEFAULTS = {
    "dxf_n_grid": 500,
    "dxf_mirror": False,
    "dxf_spline": True,
    "dxf_labels": False,
}


def load_settings() -> dict:
    """Current settings, with defaults filled in for anything missing."""
    settings = dict(DEFAULTS)
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as fh:
            stored = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return settings

    if isinstance(stored, dict):
        for key in DEFAULTS:
            if key in stored:
                settings[key] = stored[key]
    return settings


def save_settings(values: dict) -> dict:
    """Persist the known settings keys. Returns what was written."""
    settings = dict(DEFAULTS)
    for key in DEFAULTS:
        if key in values and values[key] is not None:
            settings[key] = values[key]

    settings["dxf_n_grid"] = int(settings["dxf_n_grid"])
    if settings["dxf_n_grid"] < 10:
        raise ValueError("DXF grid must be at least 10 points.")
    for key in ("dxf_mirror", "dxf_spline", "dxf_labels"):
        settings[key] = bool(settings[key])

    with open(SETTINGS_PATH, "w", encoding="utf-8") as fh:
        json.dump(settings, fh, indent=2)

    return settings
