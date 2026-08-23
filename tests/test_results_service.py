"""
Tests for backend/app/services/results.py.

This is the port of the pure-maths half of the old test_wall_export.py, which
could not be kept as-is: despite CLAUDE.md describing it as GUI-independent, it
imported QApplication and asserted against ResultsTab widget internals. The
geometry/format assertions live on here; the widget assertions are retired.
"""

import math
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from backend.app.services import results as rs


def _demo_data(n=5):
    return {
        "x_m": np.linspace(0.0, 0.1, n),
        "r_m": np.linspace(0.02, 0.04, n),
        "T_aw_K": np.full(n, 2500.0),
        "P_Pa": np.full(n, 200000.0),
        "M": np.linspace(0.2, 3.0, n),
    }


class TestRevolveAngles(unittest.TestCase):

    def test_full_circle_drops_the_duplicate_seam(self):
        angles = rs.parse_revolve_angles(True, 0.0, 360.0, 36)
        self.assertEqual(len(angles), 36)
        # 0 and 360 are the same plane, so 360 must not appear.
        self.assertAlmostEqual(angles[0], 0.0)
        self.assertLess(angles[-1], 2 * math.pi)
        self.assertAlmostEqual(angles[1] - angles[0], math.radians(10.0))

    def test_partial_arc_keeps_both_ends(self):
        angles = rs.parse_revolve_angles(True, 0.0, 90.0, 4)
        self.assertEqual(len(angles), 4)
        self.assertAlmostEqual(angles[0], 0.0)
        self.assertAlmostEqual(angles[-1], math.radians(90.0))

    def test_disabled_revolve_is_a_single_plane(self):
        angles = rs.parse_revolve_angles(False)
        self.assertEqual(list(angles), [0.0])

    def test_rejects_bad_ranges(self):
        with self.assertRaises(ValueError):
            rs.parse_revolve_angles(True, 90.0, 90.0, 4)     # end == start
        with self.assertRaises(ValueError):
            rs.parse_revolve_angles(True, 180.0, 90.0, 4)    # end < start
        with self.assertRaises(ValueError):
            rs.parse_revolve_angles(True, 0.0, 360.0, 0)     # no planes


class TestGenerateWallPoints(unittest.TestCase):

    def test_point_count_is_points_times_planes(self):
        data = _demo_data(n=5)
        pts = rs.generate_wall_points(data, [], n_planes=36)
        self.assertEqual(pts["n_pts"], 5)
        self.assertEqual(pts["n_planes"], 36)
        self.assertEqual(len(pts["X"]), 5 * 36)

    def test_revolve_transform_is_correct(self):
        # At theta=0: Y = r, Z = 0. At theta=90 deg: Y = 0, Z = r.
        data = _demo_data(n=3)
        pts = rs.generate_wall_points(data, [], start_deg=0.0, end_deg=90.0, n_planes=2)
        n = 3
        np.testing.assert_allclose(pts["Y"][:n], data["r_m"], atol=1e-12)
        np.testing.assert_allclose(pts["Z"][:n], 0.0, atol=1e-12)
        np.testing.assert_allclose(pts["Y"][n:], 0.0, atol=1e-12)
        np.testing.assert_allclose(pts["Z"][n:], data["r_m"], atol=1e-12)

    def test_x_repeats_unchanged_on_every_plane(self):
        data = _demo_data(n=4)
        pts = rs.generate_wall_points(data, [], n_planes=3)
        for plane in range(3):
            np.testing.assert_allclose(pts["X"][plane * 4:(plane + 1) * 4], data["x_m"])

    def test_radius_is_preserved_by_the_revolve(self):
        data = _demo_data(n=4)
        pts = rs.generate_wall_points(data, [], n_planes=12)
        radius = np.hypot(pts["Y"], pts["Z"])
        np.testing.assert_allclose(radius, np.tile(data["r_m"], 12), atol=1e-12)

    def test_properties_are_repeated_per_plane(self):
        data = _demo_data(n=4)
        pts = rs.generate_wall_points(data, ["T_aw_K", "M"], n_planes=3)
        self.assertEqual(len(pts["props"]["T_aw_K"]), 12)
        np.testing.assert_allclose(pts["props"]["M"], np.tile(data["M"], 3))

    def test_missing_coordinate_columns_raise(self):
        with self.assertRaises(ValueError):
            rs.generate_wall_points({"r_m": np.array([1.0])}, [])
        with self.assertRaises(ValueError):
            rs.generate_wall_points({"x_m": np.array([1.0])}, [])

    def test_empty_data_raises(self):
        with self.assertRaises(ValueError):
            rs.generate_wall_points({}, [])

    def test_unknown_property_column_raises(self):
        with self.assertRaises(ValueError):
            rs.generate_wall_points(_demo_data(), ["not_a_column"])


class TestFluentFieldResolution(unittest.TestCase):

    def test_maps_columns_to_fluent_names(self):
        selected, resolved = rs.resolve_fluent_fields(["P_Pa", "M"])
        self.assertEqual(selected, {"P_Pa": "pressure", "M": "mach-number"})
        self.assertIsNone(resolved)

    def test_t_aw_wins_the_temperature_slot(self):
        selected, resolved = rs.resolve_fluent_fields(["T_K", "T_aw_K"])
        self.assertEqual(resolved, "T_aw_K")
        self.assertIn("T_aw_K", selected)
        self.assertNotIn("T_K", selected)

    def test_t_k_alone_is_still_temperature(self):
        selected, resolved = rs.resolve_fluent_fields(["T_K"])
        self.assertEqual(selected, {"T_K": "temperature"})
        self.assertIsNone(resolved)

    def test_unrecognised_columns_are_dropped(self):
        selected, _ = rs.resolve_fluent_fields(["M", "x_m", "gamma"])
        self.assertEqual(selected, {"M": "mach-number"})

    def test_nothing_recognised_raises(self):
        with self.assertRaises(ValueError):
            rs.resolve_fluent_fields(["gamma", "x_m"])


class TestFluentProfileWriting(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_writes_expected_structure(self):
        data = _demo_data(n=3)
        selected, _ = rs.resolve_fluent_fields(["M"])
        pts = rs.generate_wall_points(data, ["M"], n_planes=2)
        out = os.path.join(self.tmp, "nozzle-wall.prof")

        n = rs.write_fluent_profile(out, pts, selected)

        self.assertEqual(n, 6)
        text = open(out, encoding="utf-8").read()
        self.assertTrue(text.startswith("((nozzle-wall point 6)"))
        for field in ("(x", "(y", "(z", "(mach-number"):
            self.assertIn(field, text)

    def test_pressure_is_written_as_gauge(self):
        data = _demo_data(n=2)
        selected, _ = rs.resolve_fluent_fields(["P_Pa"])
        pts = rs.generate_wall_points(data, ["P_Pa"], enabled=False)
        out = os.path.join(self.tmp, "p.prof")

        rs.write_fluent_profile(out, pts, selected, operating_pressure_pa=101325.0)

        text = open(out, encoding="utf-8").read()
        # 200000 absolute - 101325 operating = 98675 gauge
        self.assertIn("98675", text)
        self.assertNotIn("200000", text)

    def test_export_does_not_mutate_the_source_data(self):
        data = _demo_data(n=2)
        selected, _ = rs.resolve_fluent_fields(["P_Pa"])
        pts = rs.generate_wall_points(data, ["P_Pa"], enabled=False)
        rs.write_fluent_profile(
            os.path.join(self.tmp, "x.prof"), pts, selected, 101325.0
        )
        np.testing.assert_allclose(data["P_Pa"], 200000.0)

    def test_spaces_in_the_name_become_hyphens(self):
        data = _demo_data(n=2)
        selected, _ = rs.resolve_fluent_fields(["M"])
        pts = rs.generate_wall_points(data, ["M"], enabled=False)
        out = os.path.join(self.tmp, "my wall.prof")
        rs.write_fluent_profile(out, pts, selected)
        self.assertIn("((my-wall point", open(out, encoding="utf-8").read())


class TestCsvReading(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _write(self, text):
        path = os.path.join(self.tmp, "r.csv")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def test_skips_comment_preamble(self):
        path = self._write(
            "# generated by OpenEngine\n"
            "# date: today\n"
            "x_m,r_m\n"
            "0.0,0.02\n"
            "0.1,0.04\n"
        )
        data, headers = rs.read_results_csv(path)
        self.assertEqual(headers, ["x_m", "r_m"])
        np.testing.assert_allclose(data["x_m"], [0.0, 0.1])

    def test_blank_and_unparseable_cells_become_nan(self):
        path = self._write("x_m,r_m\n0.0,\n0.1,oops\n")
        data, _ = rs.read_results_csv(path)
        self.assertTrue(np.isnan(data["r_m"]).all())

    def test_file_with_no_header_raises(self):
        with self.assertRaises(ValueError):
            rs.read_results_csv(self._write("# only comments\n"))


class TestPathSafety(unittest.TestCase):
    """The desktop app trusted its file dialog; a web server must not."""

    def test_rejects_traversal(self):
        for bad in ["../secrets.csv", "sub/dir.csv", "/etc/passwd", ""]:
            with self.subTest(bad):
                with self.assertRaises(ValueError):
                    rs.safe_results_path(bad)

    def test_accepts_a_plain_basename(self):
        path = rs.safe_results_path("default_results_01.csv")
        self.assertTrue(path.endswith("default_results_01.csv"))


if __name__ == "__main__":
    unittest.main()
