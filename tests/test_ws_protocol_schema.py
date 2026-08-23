"""
Schema-level tests for the WebSocket protocol models (CLAUDE.md Phase 3).

These cover the message contract only. Behavioural tests for the command
handlers (run_simulation streaming, params round-trip, ...) live in
test_ws_protocol.py and land with the handlers themselves.
"""

import json
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydantic import TypeAdapter, ValidationError

from backend.app.ws import protocol as p


class TestCommandParsing(unittest.TestCase):
    """The discriminated union must route each `type` to the right model."""

    def setUp(self):
        self.adapter = TypeAdapter(p.Command)

    def test_dispatches_on_type(self):
        cmd = self.adapter.validate_python(
            {"type": "load_params", "filename": "default.json"}
        )
        self.assertIsInstance(cmd, p.LoadParamsCmd)
        self.assertEqual(cmd.filename, "default.json")

    def test_unknown_type_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.adapter.validate_python({"type": "definitely_not_a_command"})

    def test_missing_required_field_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.adapter.validate_python({"type": "load_params"})  # no filename

    def test_bare_commands_need_no_payload(self):
        for type_name, model in [
            ("list_params", p.ListParamsCmd),
            ("stop_simulation", p.StopSimulationCmd),
            ("list_results", p.ListResultsCmd),
            ("get_settings", p.GetSettingsCmd),
        ]:
            with self.subTest(type_name):
                self.assertIsInstance(
                    self.adapter.validate_python({"type": type_name}), model
                )


class TestDefaults(unittest.TestCase):
    """Defaults must match the old Qt widgets they replace."""

    def test_revolve_defaults_match_old_wall_export_tab(self):
        rev = p.RevolveConfig()
        self.assertTrue(rev.enabled)
        self.assertEqual((rev.start_deg, rev.end_deg, rev.n_planes), (0.0, 360.0, 36))

    def test_export_wall_operating_pressure_default(self):
        cmd = p.ExportWallCmd(filename="r.csv", selected_cols=["P_Pa"])
        self.assertEqual(cmd.operating_pressure_pa, 101325.0)

    def test_run_simulation_defaults_to_convergence_mode(self):
        cmd = p.RunSimulationCmd(raw_params={})
        self.assertEqual(cmd.solver_mode, "convergence")
        self.assertIsNone(cmd.solver_overrides.n_grid)

    def test_solver_mode_is_constrained(self):
        with self.assertRaises(ValidationError):
            p.RunSimulationCmd(raw_params={}, solver_mode="turbo")

    def test_save_settings_has_no_base_font(self):
        # base_font was a Qt-only font-scaling concept; browsers use zoom.
        self.assertNotIn("base_font", p.SaveSettingsCmd.model_fields)


class TestEvents(unittest.TestCase):

    def test_convergence_update_allows_missing_r_f(self):
        evt = p.ConvergenceUpdateEvt(iteration=3, r_n=1e-6, r_p=2e-6, r_t=3e-6)
        self.assertIsNone(evt.r_f)

    def test_simulation_complete_defaults(self):
        evt = p.SimulationCompleteEvt(returncode=0)
        self.assertIsNone(evt.results_file)
        self.assertFalse(evt.stopped_by_user)

    def test_every_event_carries_its_type(self):
        evt = p.ParamsListEvt(files=["default.json"])
        self.assertEqual(evt.model_dump()["type"], "params_list")


class TestSanitizeFloats(unittest.TestCase):
    """Solver output contains NaN; JSON.parse in the browser rejects it."""

    def test_replaces_nan_and_inf_with_none(self):
        self.assertIsNone(p.sanitize_floats(float("nan")))
        self.assertIsNone(p.sanitize_floats(float("inf")))
        self.assertIsNone(p.sanitize_floats(float("-inf")))

    def test_leaves_finite_values_alone(self):
        self.assertEqual(p.sanitize_floats(1.5), 1.5)
        self.assertEqual(p.sanitize_floats(0.0), 0.0)
        self.assertEqual(p.sanitize_floats("T_aw_K"), "T_aw_K")
        self.assertIsNone(p.sanitize_floats(None))

    def test_recurses_into_nested_structures(self):
        cleaned = p.sanitize_floats(
            {"rows": [[1.0, float("nan")], [float("inf"), 2.0]], "name": "x"}
        )
        self.assertEqual(cleaned, {"rows": [[1.0, None], [None, 2.0]], "name": "x"})

    def test_result_is_strict_json_serialisable(self):
        evt = p.ResultsTableEvt(
            filename="r.csv", columns=["T_aw_K"], rows=[[float("nan")]]
        )
        # allow_nan=False is what the send path uses; it raises on bare NaN.
        payload = json.dumps(p.sanitize_floats(evt.model_dump()), allow_nan=False)
        self.assertIn("null", payload)
        self.assertNotIn("NaN", payload)

    def test_unsanitised_nan_would_have_failed(self):
        # Guards the reason sanitize_floats exists.
        with self.assertRaises(ValueError):
            json.dumps({"v": float("nan")}, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
