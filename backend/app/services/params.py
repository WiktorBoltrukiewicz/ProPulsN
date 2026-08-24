"""
params.py — listing, loading and saving params/*.json.

Replaces the old Parameters tab's file bar. `load_params()` from the core is
reused as-is so the flat/raw dual structure stays identical; saving preserves
the nested layout (and int-vs-float typing) for a clean round trip.
"""

import json
import os
import re

from ..core import PARAMS_DIR
from ..core.param_loader import load_params
from ..core.param_schema import (
    format_warnings,
    looks_like_params,
    normalise_raw,
    stamp_meta,
)

# Temp files the simulation runner drops here; not user configs.
_RUN_PREFIX = "_run_"


def safe_params_path(filename: str) -> str:
    """Resolve `filename` inside params/, refusing anything that escapes it."""
    if not filename:
        raise ValueError("No filename given.")
    if os.path.basename(filename) != filename:
        raise ValueError(f"Invalid filename: {filename!r}")
    path = os.path.abspath(os.path.join(PARAMS_DIR, filename))
    if os.path.dirname(path) != os.path.abspath(PARAMS_DIR):
        raise ValueError(f"Invalid filename: {filename!r}")
    return path


def sanitize_name(name: str) -> str:
    """Turn user input into a safe `<name>.json` basename."""
    name = os.path.basename((name or "").strip())
    if name.lower().endswith(".json"):
        name = name[:-5]
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name).strip("._-")
    if not name:
        raise ValueError("Please give the file a name.")
    return f"{name}.json"


def list_param_files() -> list:
    """User-visible param files, newest-run temp files excluded."""
    os.makedirs(PARAMS_DIR, exist_ok=True)
    return sorted(
        f for f in os.listdir(PARAMS_DIR)
        if f.endswith(".json") and not f.startswith(_RUN_PREFIX)
    )


def load(filename: str):
    """Return (flat, raw, warnings) for one params file."""
    path = safe_params_path(filename)
    if not os.path.exists(path):
        raise ValueError(f"No such parameter file: {filename}")
    flat, raw = load_params(path)
    return flat, raw, format_warnings(raw, filename)


def _prepare(filename: str, raw: dict):
    """Vet, migrate and stamp a config. Returns (basename, prepared structure).

    Everything that produces a parameter file goes through here — saving into
    params/ and downloading a copy alike. A file that leaves the app must be
    indistinguishable from one that stays, so there is one place that decides
    what a config looks like, and one place (`stamp_meta`) that writes `_meta`.
    """
    if not looks_like_params(raw):
        raise ValueError(
            "That does not look like an ProPulsN parameter file: no section "
            "carries any parameter entries."
        )

    name = sanitize_name(filename)
    # Always written in the English vocabulary, so a legacy file migrates the
    # first time it is saved. Loading normalises too, but an uploaded file
    # reaches here without having been loaded first.
    prepared = normalise_raw(raw)
    stamp_meta(prepared, name)
    return name, prepared


def export(filename: str, raw: dict):
    """Serialise a config for download. Returns (basename, JSON text).

    Writes nothing: this is the copy the user keeps or sends on, so it must
    not clutter params/ with a file they never asked to store.
    """
    name, prepared = _prepare(filename, raw)
    return name, json.dumps(prepared, ensure_ascii=False, indent=4)


def save(filename: str, raw: dict, overwrite: bool = True) -> str:
    """Write the nested structure into params/. Returns the basename written."""
    name, prepared = _prepare(filename, raw)
    path = safe_params_path(name)

    if not overwrite and os.path.exists(path):
        raise ValueError(f"{name} already exists.")

    os.makedirs(PARAMS_DIR, exist_ok=True)
    # indent=4 / ensure_ascii=False keeps the descriptions readable, matching
    # how these files are written elsewhere.
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(prepared, fh, ensure_ascii=False, indent=4)

    return name
