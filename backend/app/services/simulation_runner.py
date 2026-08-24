"""
simulation_runner.py — runs one simulation and streams its output.

This is the asyncio replacement for the old Qt `_SimWorker(QThread)`. The
design is deliberately unchanged: the solver is NOT run in-process, it is
spawned as `python main.py <temp.json>` exactly as the desktop app did, and
its stdout is read line by line. Only the transport differs — lines go out as
WebSocket events instead of Qt signals.

Several details here are load-bearing and must not be "cleaned up":
  * `-u`                     — unbuffered stdout; without it the OS pipe buffers
                               and the live convergence chart stops updating.
  * `PYTHONIOENCODING=utf-8` — the solver prints Polish text; without this the
                               subprocess dies on Windows' default codepage.
  * `cwd=REPO_ROOT`          — the CLI resolves params/ and results/ from there.
  * `terminate()` not `kill()` — matches the old `terminate_process()`.

Why blocking `subprocess.Popen` in a worker thread, and not
`asyncio.create_subprocess_exec`: on Windows, spawning a subprocess requires a
ProactorEventLoop, but uvicorn installs a SelectorEventLoop, which raises
NotImplementedError. Reading the pipe with `asyncio.to_thread` works on every
event loop and platform, and mirrors what the old Qt `_SimWorker` thread did.
"""

import asyncio
import copy
import json
import os
import re
import subprocess
import sys
import tempfile
from typing import Any, Awaitable, Callable, Optional

from ..core import PARAMS_DIR, REPO_ROOT, RESULTS_DIR
from ..core.param_loader import load_params_from_raw
from ..core.param_schema import (
    REQUIRED_PARAMS,
    has_value,
    missing_params,
    normalise_raw,
)

# The repo-root CLI shim — the same entry point a human runs by hand. Spawning
# this (rather than backend/app/core/main.py directly) keeps the standalone CLI
# path exercised by every web run.
MAIN_PY = os.path.join(REPO_ROOT, "main.py")

# Kept character-for-character from the old SimulationTab._CONV_RE.
# Groups: 1=iteration, 2=R_N, 3=R_P, 4=R_T, 5=R_F (optional).
_CONV_RE = re.compile(
    r'\[Iteration\s+(\d+)\]'
    r'\s+R_N=([\d.]+(?:[eE][+\-]?\d+)?)'
    r'\s+R_P=([\d.]+(?:[eE][+\-]?\d+)?)'
    r'\s+R_T=([\d.]+(?:[eE][+\-]?\d+)?)'
    r'(?:\s+R_F=([\d.]+(?:[eE][+\-]?\d+)?))?'
)

SendEvent = Callable[[Any], Awaitable[None]]


def parse_convergence_line(line: str) -> Optional[dict]:
    """Parse one solver log line into a `convergence_update` payload.

    Returns None for lines that aren't convergence lines.
    """
    m = _CONV_RE.search(line)
    if not m:
        return None
    return {
        "type": "convergence_update",
        "iteration": int(m.group(1)),
        "r_n": float(m.group(2)),
        "r_p": float(m.group(3)),
        "r_t": float(m.group(4)),
        # The old tab used NaN here; None is the JSON-safe equivalent.
        "r_f": float(m.group(5)) if m.group(5) is not None else None,
    }


def _set_param(raw: dict, key: str, value) -> bool:
    """Overwrite `key`'s `value` wherever it appears in the nested params.

    Preserves int-ness the same way the old `_build_temp_json` did, so a value
    declared as an int in the JSON stays an int.

    A key the file does not carry yet is created rather than dropped: the UI
    offers a field for every required parameter, so a file predating one of
    them must still be able to receive what the user typed. Returns True if
    anything was written.
    """
    written = False
    for section in raw.values():
        if not isinstance(section, dict):
            continue
        for param_key, param in section.items():
            if param_key == key and has_value(param):
                old = param["value"]
                param["value"] = (
                    int(value)
                    if isinstance(old, int)
                    and not isinstance(old, bool)
                    and float(value) == int(value)
                    else value
                )
                written = True

    if not written and key in REQUIRED_PARAMS:
        section, unit, description = REQUIRED_PARAMS[key]
        raw.setdefault(section, {})[key] = {
            "value": value,
            "unit": unit,
            "description": description,
        }
        written = True

    return written


def build_run_params(
    raw_params: dict,
    solver_overrides: Optional[dict] = None,
    solver_mode: str = "convergence",
) -> dict:
    """Assemble the params structure to hand to the CLI.

    Mirrors the tail of the old `_build_temp_json()`: overlay the solver
    settings, then inject the solver-mode override section.
    """
    # A client may still be holding a structure loaded from a pre-translation
    # file, so normalise before overlaying anything onto it.
    raw = normalise_raw(copy.deepcopy(raw_params))

    for key, value in (solver_overrides or {}).items():
        if value is None:
            continue
        _set_param(raw, key, value)

    raw["_solver_mode_override"] = {
        "solver_mode": {
            "value": solver_mode,
            "unit": "",
            "description": "Solver mode",
        },
    }
    return raw


class SimulationRun:
    """One in-flight solver subprocess, streamed to a WebSocket client."""

    def __init__(
        self,
        raw_params: dict,
        solver_overrides: Optional[dict] = None,
        solver_mode: str = "convergence",
    ):
        self._raw = build_run_params(raw_params, solver_overrides, solver_mode)
        self._proc: Optional[subprocess.Popen] = None
        self._tmp_path: Optional[str] = None
        self._stopped_by_user = False

    def missing_parameters(self) -> list:
        """Required parameters this run does not supply.

        The solver refuses an incomplete file itself (core/main.py), but that
        happens inside the subprocess and reaches the user as a traceback in
        the console. Checking the assembled parameters here turns it into a
        plain error event, before anything is spawned.
        """
        flat, _ = load_params_from_raw(self._raw)
        return missing_params(flat)

    # ── lifecycle ────────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def stop(self) -> None:
        """Ask the subprocess to exit (SIGTERM), as the old Stop button did."""
        self._stopped_by_user = True
        if self.is_running:
            try:
                self._proc.terminate()
            except (ProcessLookupError, OSError):
                pass

    # ── internals ────────────────────────────────────────────────────────────

    def _write_temp_params(self) -> str:
        os.makedirs(PARAMS_DIR, exist_ok=True)
        fd, path = tempfile.mkstemp(
            suffix=".json", prefix="_run_", dir=PARAMS_DIR
        )
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(self._raw, fh, ensure_ascii=False, indent=4)
        return path

    def _cleanup_temp(self) -> None:
        if self._tmp_path and os.path.exists(self._tmp_path):
            try:
                os.remove(self._tmp_path)
            except OSError:
                pass
        self._tmp_path = None

    @staticmethod
    def _snapshot_results() -> set:
        try:
            return {f for f in os.listdir(RESULTS_DIR) if f.endswith(".csv")}
        except OSError:
            return set()

    # ── run ──────────────────────────────────────────────────────────────────

    async def run(self, send_event: SendEvent) -> None:
        """Spawn the solver and stream it. Always ends with one
        `simulation_complete` event."""
        before = self._snapshot_results()

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        # Don't flash a console window when spawned from a background server.
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        try:
            self._tmp_path = self._write_temp_params()

            self._proc = subprocess.Popen(
                [sys.executable, "-u", MAIN_PY, self._tmp_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                cwd=REPO_ROOT,
                env=env,
                creationflags=creationflags,
            )

            # Blocking readline, off-loop, so this works under any event loop.
            while True:
                line = await asyncio.to_thread(self._proc.stdout.readline)
                if not line:
                    break
                # Keep the trailing newline: the old console inserted the line
                # verbatim, and the frontend renders into a <pre>.
                await send_event({"type": "log_line", "text": line})

                update = parse_convergence_line(line)
                if update is not None:
                    await send_event(update)

            returncode = await asyncio.to_thread(self._proc.wait)

        finally:
            if self._proc is not None and self._proc.stdout is not None:
                self._proc.stdout.close()
            self._cleanup_temp()

        results_file = None
        if returncode == 0 and not self._stopped_by_user:
            new_files = self._snapshot_results() - before
            if new_files:
                # Newest, in case a concurrent run also landed one.
                results_file = max(
                    new_files,
                    key=lambda f: os.path.getmtime(os.path.join(RESULTS_DIR, f)),
                )

        await send_event({
            "type": "simulation_complete",
            "returncode": returncode,
            "results_file": results_file,
            "stopped_by_user": self._stopped_by_user,
        })
