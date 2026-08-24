"""
End-to-end WebSocket tests for the non-simulation commands.

Covers the params / geometry / DXF / results / wall-export / settings half of
the protocol. Simulation streaming lives in test_ws_protocol.py.
"""

import contextlib
import json
import os
import shutil
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.core import PARAMS_DIR, RESULTS_DIR

# The geometry commands carry no defaults any more — a payload has to state
# the whole contour, the way the Geometry section does.
CHAMBER = {"R_chamber": 0.04205, "L_chamber": 0.14262, "R_conv_arc": 0.07265}


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


class WSTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from backend.app.main import app
        cls.client = TestClient(app)

    def roundtrip(self, command: dict) -> dict:
        with ws_connect(self.client) as ws:
            ws.send_json(command)
            return ws.receive_json()


class TestParamsCommands(WSTestCase):

    def test_list_params_finds_the_shipped_configs(self):
        evt = self.roundtrip({"type": "list_params"})
        self.assertEqual(evt["type"], "params_list")
        self.assertIn("default.json", evt["files"])

    def test_list_params_hides_run_temp_files(self):
        evt = self.roundtrip({"type": "list_params"})
        self.assertFalse([f for f in evt["files"] if f.startswith("_run_")])

    def test_load_params_returns_flat_and_raw(self):
        evt = self.roundtrip({"type": "load_params", "filename": "default.json"})
        self.assertEqual(evt["type"], "params_loaded")
        self.assertIn("R_throat", evt["flat"])
        self.assertTrue(evt["raw"], "raw nested structure must come back too")
        # raw must keep the nested value/unit/description shape for round-trips
        nested = [s for s in evt["raw"].values() if isinstance(s, dict)]
        self.assertTrue(
            any("value" in v for s in nested for v in s.values()
                if isinstance(v, dict))
        )

    def test_load_params_rejects_traversal(self):
        evt = self.roundtrip({"type": "load_params", "filename": "../settings.json"})
        self.assertEqual(evt["type"], "error")

    def test_load_params_missing_file_errors(self):
        evt = self.roundtrip({"type": "load_params", "filename": "nope.json"})
        self.assertEqual(evt["type"], "error")

    def test_save_and_reload_round_trip(self):
        loaded = self.roundtrip({"type": "load_params", "filename": "default.json"})
        saved = self.roundtrip({
            "type": "save_params",
            "filename": "zz-test-roundtrip.json",
            "raw": loaded["raw"],
        })
        self.assertEqual(saved["type"], "params_saved")
        path = os.path.join(PARAMS_DIR, saved["filename"])
        try:
            back = self.roundtrip(
                {"type": "load_params", "filename": saved["filename"]}
            )
            self.assertEqual(back["flat"], loaded["flat"],
                             "a save/load round trip must not change values")
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_save_preserves_int_typing(self):
        loaded = self.roundtrip({"type": "load_params", "filename": "default.json"})
        saved = self.roundtrip({
            "type": "save_params",
            "filename": "zz-test-typing.json",
            "raw": loaded["raw"],
        })
        path = os.path.join(PARAMS_DIR, saved["filename"])
        try:
            stored = json.load(open(path, encoding="utf-8"))
            checked = False
            for section in stored.values():
                if not isinstance(section, dict):
                    continue
                for key, param in section.items():
                    if key == "n_grid" and isinstance(param, dict):
                        self.assertIsInstance(param["value"], int)
                        checked = True
            self.assertTrue(checked, "expected an int-typed n_grid in default.json")
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_save_sanitises_the_filename(self):
        # Leading underscores are stripped so user files can't collide with the
        # reserved _run_*.json temp files; the event reports the real name.
        loaded = self.roundtrip({"type": "load_params", "filename": "default.json"})
        saved = self.roundtrip({
            "type": "save_params",
            "filename": "_run_sneaky.json",
            "raw": loaded["raw"],
        })
        self.assertEqual(saved["type"], "params_saved")
        self.assertFalse(saved["filename"].startswith("_"))
        path = os.path.join(PARAMS_DIR, saved["filename"])
        if os.path.exists(path):
            os.remove(path)

    def test_save_params_as_refuses_to_clobber(self):
        evt = self.roundtrip(
            {"type": "save_params_as", "filename": "default.json", "raw": {"a": 1}}
        )
        self.assertEqual(evt["type"], "error")

    def test_save_rejects_empty_params(self):
        evt = self.roundtrip(
            {"type": "save_params", "filename": "_junk.json", "raw": {}}
        )
        self.assertEqual(evt["type"], "error")


class TestGeometryCommands(WSTestCase):

    def test_preview_returns_profile_and_stats(self):
        evt = self.roundtrip({
            "type": "preview_geometry",
            "R_throat": 0.01878, "E_r": 5, "n_grid": 100, **CHAMBER,
        })
        self.assertEqual(evt["type"], "geometry_preview")
        self.assertEqual(len(evt["x_mm"]), 100)
        self.assertEqual(len(evt["r_mm"]), 100)

        stats = evt["stats"]
        # Throat is the profile minimum, and E_r should come back as asked.
        self.assertAlmostEqual(stats["throat_radius_mm"], min(evt["r_mm"]), places=6)
        self.assertAlmostEqual(stats["E_r_actual"], 5.0, places=2)
        self.assertAlmostEqual(stats["throat_radius_mm"], 18.78, places=2)
        self.assertGreater(stats["exit_radius_mm"], stats["throat_radius_mm"])

    def test_throat_index_points_at_the_minimum(self):
        evt = self.roundtrip({
            "type": "preview_geometry", "R_throat": 0.01878, "E_r": 5,
            "n_grid": 100, **CHAMBER,
        })
        self.assertEqual(evt["r_mm"][evt["throat_index"]], min(evt["r_mm"]))

    def test_rejects_nonsense_geometry(self):
        for payload in [
            {"R_throat": 0, "E_r": 5},
            {"R_throat": 0.01, "E_r": 1},
            {"R_throat": -1, "E_r": 5},
        ]:
            with self.subTest(**payload):
                evt = self.roundtrip({
                    "type": "preview_geometry", "n_grid": 100,
                    **CHAMBER, **payload,
                })
                self.assertEqual(evt["type"], "error")

    def test_export_dxf_writes_a_file(self):
        evt = self.roundtrip({
            "type": "export_dxf",
            "R_throat": 0.01878, "E_r": 5, "n_grid": 100, **CHAMBER,
            "mirror": True, "spline": False, "labels": True,
        })
        self.assertEqual(evt["type"], "dxf_export_ready")
        path = os.path.join(RESULTS_DIR, evt["filename"])
        try:
            self.assertTrue(os.path.exists(path))
            self.assertGreater(os.path.getsize(path), 0)
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_export_dxf_rejects_path_traversal(self):
        evt = self.roundtrip({
            "type": "export_dxf", "R_throat": 0.01878, "E_r": 5, **CHAMBER,
            "filename": "../escaped.dxf",
        })
        self.assertEqual(evt["type"], "error")


class TestResultsCommands(WSTestCase):
    """Uses a temporary CSV placed in results/."""

    FIXTURE = "_test_results_fixture.csv"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        os.makedirs(RESULTS_DIR, exist_ok=True)
        cls.fixture_path = os.path.join(RESULTS_DIR, cls.FIXTURE)
        with open(cls.fixture_path, "w", encoding="utf-8") as fh:
            fh.write("# ProPulsN test fixture\n")
            fh.write("x_m,r_m,M,P_Pa,T_aw_K\n")
            fh.write("0.00,0.020,0.5,300000,2500\n")
            fh.write("0.05,0.019,1.0,200000,2400\n")
            fh.write("0.10,0.040,3.0,100000,2300\n")

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.fixture_path):
            os.remove(cls.fixture_path)

    def test_list_results_includes_the_fixture(self):
        evt = self.roundtrip({"type": "list_results"})
        self.assertEqual(evt["type"], "results_list")
        self.assertIn(self.FIXTURE, evt["files"])

    def test_results_table_returns_all_columns_and_rows(self):
        evt = self.roundtrip(
            {"type": "get_results_table", "filename": self.FIXTURE}
        )
        self.assertEqual(evt["type"], "results_table")
        self.assertEqual(evt["columns"], ["x_m", "r_m", "M", "P_Pa", "T_aw_K"])
        self.assertEqual(len(evt["rows"]), 3)
        self.assertEqual(evt["rows"][0][0], 0.0)

    def test_plot_data_extracts_two_columns(self):
        evt = self.roundtrip({
            "type": "get_plot_data", "filename": self.FIXTURE,
            "x_col": "x_m", "y_col": "M",
        })
        self.assertEqual(evt["type"], "plot_data")
        self.assertEqual(evt["x"], [0.0, 0.05, 0.10])
        self.assertEqual(evt["y"], [0.5, 1.0, 3.0])

    def test_plot_data_unknown_column_errors(self):
        evt = self.roundtrip({
            "type": "get_plot_data", "filename": self.FIXTURE,
            "x_col": "x_m", "y_col": "nope",
        })
        self.assertEqual(evt["type"], "error")

    def test_preview_wall_returns_a_point_cloud(self):
        evt = self.roundtrip({
            "type": "preview_wall", "filename": self.FIXTURE,
            "color_by": "M",
            "revolve": {"enabled": True, "start_deg": 0, "end_deg": 360,
                        "n_planes": 12},
        })
        self.assertEqual(evt["type"], "wall_preview_ready")
        self.assertEqual(evt["n_points"], 3 * 12)
        self.assertEqual(evt["n_planes"], 12)
        self.assertEqual(len(evt["x"]), 36)
        self.assertEqual(len(evt["color_values"]), 36)
        self.assertEqual(evt["color_label"], "M")

    def test_preview_wall_without_colour_column(self):
        evt = self.roundtrip({
            "type": "preview_wall", "filename": self.FIXTURE,
            "revolve": {"enabled": False},
        })
        self.assertEqual(evt["type"], "wall_preview_ready")
        self.assertIsNone(evt["color_values"])
        self.assertEqual(evt["n_points"], 3)

    def test_export_wall_writes_a_prof(self):
        evt = self.roundtrip({
            "type": "export_wall", "filename": self.FIXTURE,
            "selected_cols": ["M", "P_Pa"],
            "revolve": {"enabled": True, "start_deg": 0, "end_deg": 360,
                        "n_planes": 4},
            "output_name": "_test_wall",
        })
        self.assertEqual(evt["type"], "wall_export_ready")
        self.assertEqual(evt["n_points"], 12)
        self.assertCountEqual(evt["fields_exported"], ["mach-number", "pressure"])

        path = os.path.join(RESULTS_DIR, evt["filename"])
        try:
            self.assertTrue(os.path.exists(path))
            text = open(path, encoding="utf-8").read()
            self.assertIn("point 12", text)
            self.assertIn("(mach-number", text)
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_export_wall_reports_temperature_resolution(self):
        evt = self.roundtrip({
            "type": "export_wall", "filename": self.FIXTURE,
            "selected_cols": ["T_aw_K", "M"],
            "revolve": {"enabled": False},
            "output_name": "_test_wall_temp",
        })
        self.assertEqual(evt["type"], "wall_export_ready")
        # Only T_aw_K is present here, so nothing needed resolving.
        self.assertIsNone(evt["temperature_field_resolved"])
        path = os.path.join(RESULTS_DIR, evt["filename"])
        if os.path.exists(path):
            os.remove(path)

    def test_export_wall_with_nothing_recognised_errors(self):
        evt = self.roundtrip({
            "type": "export_wall", "filename": self.FIXTURE,
            "selected_cols": ["x_m"],
            "revolve": {"enabled": False},
        })
        self.assertEqual(evt["type"], "error")

    def test_results_commands_reject_traversal(self):
        evt = self.roundtrip(
            {"type": "get_results_table", "filename": "../settings.json"}
        )
        self.assertEqual(evt["type"], "error")


class TestSettingsCommands(WSTestCase):

    def setUp(self):
        from backend.app.services.settings import SETTINGS_PATH
        self.path = SETTINGS_PATH
        self.backup = self.path + ".bak"
        if os.path.exists(self.path):
            shutil.copy2(self.path, self.backup)

    def tearDown(self):
        if os.path.exists(self.backup):
            shutil.move(self.backup, self.path)

    def test_get_settings_returns_the_dxf_keys(self):
        evt = self.roundtrip({"type": "get_settings"})
        self.assertEqual(evt["type"], "settings")
        for key in ("dxf_n_grid", "dxf_mirror", "dxf_spline", "dxf_labels"):
            self.assertIn(key, evt)

    def test_get_settings_never_returns_base_font(self):
        evt = self.roundtrip({"type": "get_settings"})
        self.assertNotIn("base_font", evt)

    def test_save_settings_persists_and_drops_base_font(self):
        evt = self.roundtrip({
            "type": "save_settings",
            "dxf_n_grid": 250, "dxf_mirror": True,
            "dxf_spline": False, "dxf_labels": True,
        })
        self.assertEqual(evt["type"], "settings")
        self.assertEqual(evt["dxf_n_grid"], 250)

        stored = json.load(open(self.path, encoding="utf-8"))
        self.assertEqual(stored["dxf_n_grid"], 250)
        self.assertNotIn("base_font", stored)

        again = self.roundtrip({"type": "get_settings"})
        self.assertEqual(again["dxf_n_grid"], 250)

    def test_save_settings_rejects_a_tiny_grid(self):
        evt = self.roundtrip({"type": "save_settings", "dxf_n_grid": 2})
        self.assertEqual(evt["type"], "error")


if __name__ == "__main__":
    unittest.main()
