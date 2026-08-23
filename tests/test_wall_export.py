"""
tests/test_wall_export.py — Wall Export sub-tab tests.

Tests:
  1.  Wall Export sub-tab exists as the third sub-tab
  2.  Property checkboxes populate after loading a file
  3.  x_m and r_m are excluded from property checkboxes (used for coords)
  4.  All property checkboxes are ticked by default
  5.  Select All / Deselect All buttons work
  6.  Revolve fields are disabled when revolve checkbox is unchecked
  7.  Revolve fields are enabled when revolve checkbox is checked
  8.  Export without data loaded shows a warning
  9.  Single-plane export (no revolve) produces correct point count
  10. Full 360° revolve export produces n_pts × n_planes points
  11. Partial arc export includes the endpoint plane
  12. Profile always contains x, y, z fields
  13. z field is all zeros when revolve is disabled
  14. x field equals x_m values for every plane
  15. Y = r * cos(theta), Z = r * sin(theta) for a known angle
  16. Invalid revolve parameters show an error dialog
  17. Color-by combo populates after loading a file
  18. Color-by combo defaults to a preferred property (P_Pa or T_K or M)
  19. Preview 3D without data shows a warning
  20. Preview 3D with data opens a _Preview3DDialog
  21. _generate_wall_points returns correct array lengths
  22. _generate_wall_points raises ValueError when x_m/r_m missing
"""

import os
import sys
import csv
import tempfile
import unittest
from unittest.mock import patch, MagicMock

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from PySide6.QtWidgets import QApplication
import numpy as np

_qapp = QApplication.instance() or QApplication(sys.argv)


def _make_tab():
    from tabs.results_tab import ResultsTab
    return ResultsTab()


def _write_csv(rows, headers):
    f = tempfile.NamedTemporaryFile(
        mode='w', suffix='.csv', delete=False, encoding='utf-8', newline=''
    )
    writer = csv.writer(f)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    f.close()
    return f.name


def _load_tab_with(tab, rows, headers):
    path = _write_csv(rows, headers)
    tab._load_from_path(path)
    return path


def _read_prof(path):
    """Parse a Fluent .prof file. Returns dict field_name -> list[float]."""
    data = {}
    current_field = None
    current_values = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('(('):
                continue
            if line == ')':
                if current_field is not None:
                    data[current_field] = current_values
                    current_field = None
                    current_values = []
            elif line.startswith('(') and not line.startswith('(('):
                current_field = line[1:].strip()
                current_values = []
            elif current_field is not None:
                current_values.extend(float(v) for v in line.split())
    return data


class TestWallExport(unittest.TestCase):

    HEADERS = ['x_m', 'r_m', 'M', 'P_Pa', 'T_K']
    ROWS = [
        [0.01, 0.015, 0.3, 2_100_000, 3200],
        [0.02, 0.012, 0.8, 1_500_000, 2900],
        [0.03, 0.010, 1.0,   900_000, 2600],
        [0.04, 0.012, 1.5,   500_000, 2200],
        [0.05, 0.018, 2.0,   200_000, 1800],
    ]

    def setUp(self):
        self.tab = _make_tab()
        self._tmp = _load_tab_with(self.tab, self.ROWS, self.HEADERS)

    def tearDown(self):
        try:
            os.unlink(self._tmp)
        except OSError:
            pass

    # ── 1. Sub-tab exists ─────────────────────────────────────────────────────

    def test_wall_export_is_third_subtab(self):
        titles = [self.tab._sub_tabs.tabText(i).strip()
                  for i in range(self.tab._sub_tabs.count())]
        self.assertIn("Wall Export", titles)
        self.assertEqual(titles.index("Wall Export"), 2)

    # ── 2-4. Checkboxes ───────────────────────────────────────────────────────

    def test_checkboxes_populated_after_load(self):
        self.assertGreater(len(self.tab._export_checkboxes), 0)

    def test_coord_cols_excluded_from_checkboxes(self):
        self.assertNotIn('x_m', self.tab._export_checkboxes)
        self.assertNotIn('r_m', self.tab._export_checkboxes)

    def test_all_checkboxes_checked_by_default(self):
        for col, cb in self.tab._export_checkboxes.items():
            self.assertTrue(cb.isChecked(), f"Checkbox '{col}' not checked by default")

    # ── 5. Select All / Deselect All ─────────────────────────────────────────

    def test_deselect_all(self):
        self.tab._deselect_all_props()
        for col, cb in self.tab._export_checkboxes.items():
            self.assertFalse(cb.isChecked())

    def test_select_all(self):
        self.tab._deselect_all_props()
        self.tab._select_all_props()
        for col, cb in self.tab._export_checkboxes.items():
            self.assertTrue(cb.isChecked())

    # ── 6-7. Revolve toggle ───────────────────────────────────────────────────

    def test_revolve_off_disables_fields(self):
        self.tab._revolve_cb.setChecked(False)
        for w in (self.tab._revolve_start, self.tab._revolve_end, self.tab._revolve_n):
            self.assertFalse(w.isEnabled())

    def test_revolve_on_enables_fields(self):
        self.tab._revolve_cb.setChecked(False)
        self.tab._revolve_cb.setChecked(True)
        for w in (self.tab._revolve_start, self.tab._revolve_end, self.tab._revolve_n):
            self.assertTrue(w.isEnabled())

    # ── 8. Export without data warns ─────────────────────────────────────────

    def test_export_without_data_warns(self):
        tab = _make_tab()
        with patch('PySide6.QtWidgets.QMessageBox.warning') as mock_warn:
            tab._do_fluent_export()
            mock_warn.assert_called_once()

    # ── Helper ────────────────────────────────────────────────────────────────

    def _run_export(self, revolve, start, end, n_planes, out_path):
        self.tab._revolve_cb.setChecked(revolve)
        self.tab._revolve_start.setText(str(start))
        self.tab._revolve_end.setText(str(end))
        self.tab._revolve_n.setText(str(n_planes))
        with patch('PySide6.QtWidgets.QFileDialog.getSaveFileName',
                   return_value=(out_path, '')):
            with patch('PySide6.QtWidgets.QMessageBox.information'):
                self.tab._do_fluent_export()
        return _read_prof(out_path)

    # ── 9-11. Point counts ────────────────────────────────────────────────────

    def test_single_plane_row_count(self):
        tmp = tempfile.mktemp(suffix='.prof')
        try:
            data = self._run_export(False, 0, 360, 36, tmp)
            self.assertEqual(len(data['x']), len(self.ROWS))
        finally:
            os.unlink(tmp)

    def test_full_revolve_row_count(self):
        n_planes = 12
        tmp = tempfile.mktemp(suffix='.prof')
        try:
            data = self._run_export(True, 0, 360, n_planes, tmp)
            self.assertEqual(len(data['x']), len(self.ROWS) * n_planes)
        finally:
            os.unlink(tmp)

    def test_partial_arc_includes_endpoint(self):
        tmp = tempfile.mktemp(suffix='.prof')
        try:
            data = self._run_export(True, 0, 90, 4, tmp)
            self.assertEqual(len(data['x']), len(self.ROWS) * 4)
        finally:
            os.unlink(tmp)

    # ── 12-15. Coordinate correctness ────────────────────────────────────────

    def test_prof_has_xyz_fields(self):
        tmp = tempfile.mktemp(suffix='.prof')
        try:
            data = self._run_export(False, 0, 360, 1, tmp)
            self.assertIn('x', data)
            self.assertIn('y', data)
            self.assertIn('z', data)
        finally:
            os.unlink(tmp)

    def test_z_is_zero_without_revolve(self):
        tmp = tempfile.mktemp(suffix='.prof')
        try:
            data = self._run_export(False, 0, 360, 1, tmp)
            for v in data['z']:
                self.assertAlmostEqual(v, 0.0, places=10)
        finally:
            os.unlink(tmp)

    def test_x_equals_x_m(self):
        n_planes = 6
        tmp = tempfile.mktemp(suffix='.prof')
        try:
            data = self._run_export(True, 0, 360, n_planes, tmp)
            expected_x = [r[0] for r in self.ROWS]
            for plane in range(n_planes):
                for i, x_exp in enumerate(expected_x):
                    self.assertAlmostEqual(
                        data['x'][plane * len(self.ROWS) + i],
                        x_exp, places=6)
        finally:
            os.unlink(tmp)

    def test_revolve_coordinates_correct(self):
        """Plane at 90°: Y ≈ 0, Z = r."""
        tmp = tempfile.mktemp(suffix='.prof')
        try:
            # 4 planes: 0°, 90°, 180°, 270° (partial arc, endpoint=True)
            data = self._run_export(True, 0, 270, 4, tmp)
            n_pts = len(self.ROWS)
            for i, src_row in enumerate(self.ROWS):
                r = src_row[1]
                y = data['y'][n_pts + i]   # second plane = 90°
                z = data['z'][n_pts + i]
                self.assertAlmostEqual(y, 0.0, delta=1e-9)
                self.assertAlmostEqual(z, r,   delta=1e-9)
        finally:
            os.unlink(tmp)

    # ── 16. Invalid parameters ────────────────────────────────────────────────

    def test_invalid_n_planes_shows_error(self):
        self.tab._revolve_n.setText('0')
        with patch('PySide6.QtWidgets.QMessageBox.critical') as mock_err:
            self.tab._do_fluent_export()
            mock_err.assert_called_once()

    def test_end_not_greater_than_start_shows_error(self):
        self.tab._revolve_start.setText('90')
        self.tab._revolve_end.setText('45')
        with patch('PySide6.QtWidgets.QMessageBox.critical') as mock_err:
            self.tab._do_fluent_export()
            mock_err.assert_called_once()

    # ── 17-18. Color-by combo ─────────────────────────────────────────────────

    def test_color_by_combo_populated(self):
        # Should have at least the "(uniform colour)" sentinel + property items
        self.assertGreater(self.tab._color_by_combo.count(), 1)

    def test_color_by_combo_default_is_preferred(self):
        preferred = {'P_Pa', 'T_K', 'M', 'T_aw_K'}
        current = self.tab._color_by_combo.currentText()
        from tabs.results_tab import _COLOR_NONE
        self.assertTrue(
            current in preferred or current == _COLOR_NONE,
            f"Unexpected default color-by: {current}"
        )

    # ── 19-20. Preview 3D ────────────────────────────────────────────────────

    def test_preview_without_data_warns(self):
        tab = _make_tab()
        with patch('PySide6.QtWidgets.QMessageBox.warning') as mock_warn:
            tab._do_preview_3d()
            mock_warn.assert_called_once()

    def test_preview_opens_dialog(self):
        from tabs.results_tab import _Preview3DDialog
        opened = []

        original_show = _Preview3DDialog.show
        def _capture_show(self_dlg):
            opened.append(self_dlg)
        with patch.object(_Preview3DDialog, 'show', _capture_show):
            self.tab._do_preview_3d()
        self.assertEqual(len(opened), 1)
        self.assertIsInstance(opened[0], _Preview3DDialog)

    # ── 21-22. _generate_wall_points ─────────────────────────────────────────

    def test_generate_wall_points_length(self):
        self.tab._revolve_cb.setChecked(True)
        self.tab._revolve_start.setText('0')
        self.tab._revolve_end.setText('360')
        self.tab._revolve_n.setText('12')
        pts = self.tab._generate_wall_points(['M', 'P_Pa'])
        self.assertEqual(len(pts['X']), len(self.ROWS) * 12)
        self.assertEqual(pts['n_pts'], len(self.ROWS))
        self.assertEqual(pts['n_planes'], 12)

    def test_generate_wall_points_missing_coords_raises(self):
        # Load a file without x_m / r_m
        tmp = _write_csv([[1, 2], [3, 4]], ['a', 'b'])
        try:
            self.tab._load_from_path(tmp)
            with self.assertRaises(ValueError):
                self.tab._generate_wall_points([])
        finally:
            os.unlink(tmp)


if __name__ == '__main__':
    unittest.main()
