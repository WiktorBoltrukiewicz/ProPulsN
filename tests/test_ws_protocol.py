"""
Behavioural tests for the simulation-streaming WebSocket commands
(CLAUDE.md Phase 4).

These actually spawn the solver subprocess, so they cap the iteration count to
stay fast. Note they do NOT shrink n_grid: the solver needs a fine enough grid
to resolve the sonic point, and a coarse one (e.g. 30) fails with a bad-domain
ValueError rather than converging.
"""

import contextlib
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.core import PARAMS_DIR, REPO_ROOT
from backend.app.core.param_loader import load_params
from backend.app.services.simulation_runner import (
    build_run_params,
    parse_convergence_line,
)


@contextlib.contextmanager
def ws_connect(client):
    """Connect, and swallow the `server_info` greeting the backend opens with.

    The greeting is the stale-backend handshake (see backend/app/version.py);
    it is asserted on in tests/test_version_handshake.py, so everywhere else
    just steps over it.
    """
    with client.websocket_connect("/ws") as ws:
        greeting = ws.receive_json()
        assert greeting["type"] == "server_info", greeting
        yield ws


class TestConvergenceLineParsing(unittest.TestCase):
    """The regex is carried over verbatim from the old Qt tab; lock it down."""

    def test_parses_a_full_line_with_r_f(self):
        line = ("  [Iteration 33] R_N=3.720e-08 R_P=1.867e-08 R_T=1.147e-08 "
                "R_F=3.536e-08  stop=4.605e-07 (target: < 1.0e-06)\n")
        got = parse_convergence_line(line)
        self.assertEqual(got["type"], "convergence_update")
        self.assertEqual(got["iteration"], 33)
        self.assertAlmostEqual(got["r_n"], 3.720e-08)
        self.assertAlmostEqual(got["r_p"], 1.867e-08)
        self.assertAlmostEqual(got["r_t"], 1.147e-08)
        self.assertAlmostEqual(got["r_f"], 3.536e-08)

    def test_r_f_is_optional(self):
        line = "[Iteration 2] R_N=1.0e-03 R_P=2.0e-03 R_T=3.0e-03"
        got = parse_convergence_line(line)
        self.assertEqual(got["iteration"], 2)
        self.assertIsNone(got["r_f"], "missing R_F must be None, not a crash")

    def test_plain_decimals_parse(self):
        got = parse_convergence_line("[Iteration 1] R_N=0.5 R_P=0.25 R_T=0.125")
        self.assertAlmostEqual(got["r_n"], 0.5)

    def test_non_convergence_lines_return_none(self):
        for line in [
            "Building nozzle geometry...\n",
            "Stage 1: ODE integration (isentropic flow)...\n",
            "  CONVERGENCE ACHIEVED after 33 iterations!\n",
            "",
        ]:
            with self.subTest(line=line):
                self.assertIsNone(parse_convergence_line(line))

    def test_payload_is_json_safe(self):
        got = parse_convergence_line("[Iteration 1] R_N=1e-3 R_P=1e-3 R_T=1e-3")
        json.dumps(got, allow_nan=False)  # would raise on NaN


class TestBuildRunParams(unittest.TestCase):
    """Mirrors the old _build_temp_json() overlay behaviour."""

    def setUp(self):
        self.raw = {
            "solver": {
                "max_iterations": {"value": 50, "unit": "", "description": "x"},
                "tol": {"value": 1e-6, "unit": "", "description": "x"},
            },
            "_meta": {"name": "test"},
        }

    def test_injects_solver_mode_override(self):
        out = build_run_params(self.raw, {}, "fixed")
        self.assertEqual(
            out["_solver_mode_override"]["solver_mode"]["value"], "fixed"
        )

    def test_overrides_are_applied(self):
        out = build_run_params(self.raw, {"max_iterations": 3, "tol": 1e-3})
        self.assertEqual(out["solver"]["max_iterations"]["value"], 3)
        self.assertAlmostEqual(out["solver"]["tol"]["value"], 1e-3)

    def test_int_typing_is_preserved(self):
        # max_iterations was declared int; a float override must land as int.
        out = build_run_params(self.raw, {"max_iterations": 7.0})
        value = out["solver"]["max_iterations"]["value"]
        self.assertIsInstance(value, int)
        self.assertEqual(value, 7)

    def test_float_params_stay_float(self):
        out = build_run_params(self.raw, {"tol": 2.0})
        self.assertIsInstance(out["solver"]["tol"]["value"], float)

    def test_none_overrides_are_skipped(self):
        out = build_run_params(self.raw, {"max_iterations": None})
        self.assertEqual(out["solver"]["max_iterations"]["value"], 50)

    def test_unknown_keys_are_ignored(self):
        # The old code silently did nothing for keys not present in the file.
        out = build_run_params(self.raw, {"not_a_real_param": 1})
        self.assertNotIn("not_a_real_param", out["solver"])

    def test_input_is_not_mutated(self):
        build_run_params(self.raw, {"max_iterations": 99})
        self.assertEqual(self.raw["solver"]["max_iterations"]["value"], 50)
        self.assertNotIn("_solver_mode_override", self.raw)


def _fast_params():
    """Real default params, dialled down so the solver finishes quickly."""
    _, raw = load_params(os.path.join(PARAMS_DIR, "default.json"))
    return raw


class TestRunsOnSelectorEventLoop(unittest.TestCase):
    """Regression guard for the loop uvicorn actually uses.

    uvicorn installs a SelectorEventLoop on Windows, which cannot spawn
    subprocesses: asyncio.create_subprocess_exec raises NotImplementedError
    there. TestClient runs on the default (Proactor) loop, so the WS tests
    below happily passed while the real server could not solve at all. This
    pins the runner to a loop with no subprocess support of its own.
    """

    def test_solver_streams_on_a_selector_loop(self):
        import asyncio
        from backend.app.services.simulation_runner import SimulationRun
        from backend.app.core import RESULTS_DIR

        selector_loop = getattr(asyncio, "SelectorEventLoop", None)
        if selector_loop is None:                       # pragma: no cover
            self.skipTest("no SelectorEventLoop on this platform")

        events = []

        async def collect(evt):
            events.append(evt)

        run = SimulationRun(
            raw_params=_fast_params(),
            solver_overrides={"max_iterations": 1},
            solver_mode="fixed",
        )

        loop = selector_loop()
        try:
            loop.run_until_complete(run.run(collect))
        finally:
            loop.close()

        kinds = [e["type"] for e in events]
        self.assertIn("log_line", kinds)
        self.assertEqual(kinds[-1], "simulation_complete")
        self.assertEqual(events[-1]["returncode"], 0,
                         "solver must run on a SelectorEventLoop")

        produced = events[-1].get("results_file")
        if produced:
            path = os.path.join(RESULTS_DIR, produced)
            if os.path.exists(path):
                os.remove(path)


class TestSimulationStreaming(unittest.TestCase):
    """End-to-end: run_simulation must stream and then complete."""

    @classmethod
    def setUpClass(cls):
        # Imported here so a missing fastapi/httpx skips rather than errors.
        from fastapi.testclient import TestClient
        from backend.app.main import app
        cls.client = TestClient(app)

    def _collect(self, ws, timeout_msgs=4000):
        """Drain events until simulation_complete."""
        events = []
        for _ in range(timeout_msgs):
            evt = ws.receive_json()
            events.append(evt)
            if evt["type"] == "simulation_complete":
                return events
        self.fail("never received simulation_complete")

    def test_run_streams_logs_and_completes(self):
        with ws_connect(self.client) as ws:
            ws.send_json({
                "type": "run_simulation",
                "raw_params": _fast_params(),
                "solver_overrides": {"max_iterations": 2},
                "solver_mode": "fixed",
            })
            events = self._collect(ws)

        kinds = {e["type"] for e in events}
        self.assertIn("log_line", kinds)
        self.assertIn("convergence_update", kinds)

        done = events[-1]
        self.assertEqual(done["type"], "simulation_complete")
        self.assertEqual(done["returncode"], 0)
        self.assertFalse(done["stopped_by_user"])
        self.assertIsNotNone(
            done["results_file"], "a successful run should report its CSV"
        )

        # Clean up the CSV this test produced.
        from backend.app.core import RESULTS_DIR
        produced = os.path.join(RESULTS_DIR, done["results_file"])
        if os.path.exists(produced):
            os.remove(produced)

    def test_convergence_updates_are_well_formed(self):
        with ws_connect(self.client) as ws:
            ws.send_json({
                "type": "run_simulation",
                "raw_params": _fast_params(),
                "solver_overrides": {"max_iterations": 2},
                "solver_mode": "fixed",
            })
            events = self._collect(ws)

        updates = [e for e in events if e["type"] == "convergence_update"]
        self.assertTrue(updates)
        for u in updates:
            for key in ("iteration", "r_n", "r_p", "r_t"):
                self.assertIn(key, u)
                self.assertIsNotNone(u[key])
        self.assertEqual([u["iteration"] for u in updates],
                         sorted(u["iteration"] for u in updates),
                         "iterations should arrive in order")

        from backend.app.core import RESULTS_DIR
        rf = events[-1].get("results_file")
        if rf and os.path.exists(os.path.join(RESULTS_DIR, rf)):
            os.remove(os.path.join(RESULTS_DIR, rf))

    def test_temp_param_files_are_cleaned_up(self):
        before = {f for f in os.listdir(PARAMS_DIR) if f.startswith("_run_")}
        with ws_connect(self.client) as ws:
            ws.send_json({
                "type": "run_simulation",
                "raw_params": _fast_params(),
                "solver_overrides": {"max_iterations": 1},
                "solver_mode": "fixed",
            })
            events = self._collect(ws)
        after = {f for f in os.listdir(PARAMS_DIR) if f.startswith("_run_")}
        self.assertEqual(before, after, "temp _run_*.json must be deleted")

        from backend.app.core import RESULTS_DIR
        rf = events[-1].get("results_file")
        if rf and os.path.exists(os.path.join(RESULTS_DIR, rf)):
            os.remove(os.path.join(RESULTS_DIR, rf))

    def test_invalid_payload_reports_error(self):
        with ws_connect(self.client) as ws:
            ws.send_json({"type": "run_simulation"})   # missing raw_params
            evt = ws.receive_json()
        self.assertEqual(evt["type"], "error")
        self.assertEqual(evt["context"], "run_simulation")

    def test_stop_without_a_run_reports_error(self):
        with ws_connect(self.client) as ws:
            ws.send_json({"type": "stop_simulation"})
            evt = ws.receive_json()
        self.assertEqual(evt["type"], "error")
        self.assertEqual(evt["context"], "stop_simulation")

    def test_stop_terminates_a_running_simulation(self):
        with ws_connect(self.client) as ws:
            ws.send_json({
                "type": "run_simulation",
                "raw_params": _fast_params(),
                # Long enough that it is still running when we stop it.
                "solver_overrides": {"max_iterations": 400},
                "solver_mode": "fixed",
            })
            ws.receive_json()               # wait for streaming to actually start
            ws.send_json({"type": "stop_simulation"})

            done = None
            for _ in range(20000):
                evt = ws.receive_json()
                if evt["type"] == "simulation_complete":
                    done = evt
                    break

        self.assertIsNotNone(done, "stopping must still yield simulation_complete")
        self.assertTrue(done["stopped_by_user"])
        self.assertIsNone(done["results_file"])


if __name__ == "__main__":
    unittest.main()
