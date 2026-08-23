"""
tests/test_qt_update1.py — Update 1: Qt shell smoke tests.

Tests:
  1.  QApplication can be created without errors
  2.  OpenEngineApp instantiates without errors
  3.  Main window title is "OpenEngine"
  4.  Tab widget contains exactly 4 tabs
  5.  Tab titles contain the expected names
  6.  GeometryTab placeholder is a QWidget
  7.  ParametersTab placeholder is a QWidget
  8.  SimulationTab placeholder is a QWidget
  9.  ResultsTab placeholder is a QWidget
  10. settings.json round-trip: save then load recovers the same values
  11. constants.BASE_FONT is applied to QApplication font size
"""

import os
import sys
import json
import tempfile
import unittest

# Ensure repo root is on the path when tests are run from any directory
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from PySide6.QtWidgets import QApplication, QWidget, QTabWidget

# One QApplication for the whole test module
_qapp = QApplication.instance() or QApplication(sys.argv)


class TestQtUpdate1(unittest.TestCase):

    def setUp(self):
        """Create a fresh OpenEngineApp before each test."""
        from app import OpenEngineApp
        self.app = OpenEngineApp()

    # ── 1. QApplication exists ────────────────────────────────────────────────

    def test_qapplication_exists(self):
        self.assertIsNotNone(QApplication.instance())

    # ── 2. App instantiates ───────────────────────────────────────────────────

    def test_app_instantiates(self):
        from app import OpenEngineApp
        self.assertIsInstance(self.app, OpenEngineApp)

    # ── 3. Window title ───────────────────────────────────────────────────────

    def test_window_title(self):
        self.assertEqual(self.app._win.windowTitle(), "OpenEngine")

    # ── 4. Tab count ──────────────────────────────────────────────────────────

    def test_tab_count(self):
        self.assertEqual(self.app._tabs.count(), 4)

    # ── 5. Tab titles ─────────────────────────────────────────────────────────

    def test_tab_titles(self):
        titles = [self.app._tabs.tabText(i).strip() for i in range(4)]
        self.assertIn("Geometry",   titles)
        self.assertIn("Parameters", titles)
        self.assertIn("Simulation", titles)
        self.assertIn("Results",    titles)

    # ── 6-9. Tab widget types ─────────────────────────────────────────────────

    def test_geometry_tab_is_qwidget(self):
        self.assertIsInstance(self.app.geo_tab, QWidget)

    def test_parameters_tab_is_qwidget(self):
        self.assertIsInstance(self.app.params_tab, QWidget)

    def test_simulation_tab_is_qwidget(self):
        self.assertIsInstance(self.app.sim_tab, QWidget)

    def test_results_tab_is_qwidget(self):
        self.assertIsInstance(self.app.results_tab, QWidget)

    # ── 10. Settings round-trip ───────────────────────────────────────────────

    def test_settings_roundtrip(self):
        import constants
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False, encoding='utf-8'
        ) as f:
            tmp_path = f.name

        try:
            original = self.app._SETTINGS_FILE
            self.app._SETTINGS_FILE = tmp_path

            self.app.settings['dxf_n_grid'] = 999
            self.app.settings['base_font']  = 14
            self.app.save_settings()

            # Reset to defaults then reload
            self.app.settings['dxf_n_grid'] = 1
            self.app.settings['base_font']  = 16
            self.app._load_settings()

            self.assertEqual(self.app.settings['dxf_n_grid'], 999)
            self.assertEqual(self.app.settings['base_font'],  14)
        finally:
            self.app._SETTINGS_FILE = original
            os.unlink(tmp_path)

    # ── 11. Font size applied ─────────────────────────────────────────────────

    def test_font_size_applied(self):
        import constants
        qfont = QApplication.instance().font()
        self.assertEqual(qfont.pointSize(), constants.BASE_FONT)


if __name__ == '__main__':
    unittest.main()
