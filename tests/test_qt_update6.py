"""
tests/test_qt_update6.py — Update 6: Settings dialog + cutover tests.

Tests:
  1.  ui.py imports OpenEngineApp from app (not app_qt)
  2.  app.py imports from final module names (no _qt suffix)
  3.  No _qt suffix files remain in the repo
  4.  SettingsWindow instantiates as a QDialog
  5.  Settings tree has Export and Visual nodes
  6.  Geometry panel has dxf_n_grid field
  7.  Visual panel has font slider and spinbox
  8.  Slider and spinbox stay in sync
  9.  _apply_geometry saves settings correctly
  10. _apply_geometry rejects n_grid < 10
  11. _apply_visual updates constants.BASE_FONT
  12. _apply_visual persists to app.settings
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from PySide6.QtWidgets import QApplication, QDialog
_qapp = QApplication.instance() or QApplication(sys.argv)

import constants


def _make_mock_app():
    app = MagicMock()
    app.settings = {
        'dxf_n_grid': 500, 'dxf_mirror': True, 'dxf_spline': False,
        'dxf_labels': True, 'dxf_auto_filename': True, 'dxf_path': '',
        'base_font': constants.BASE_FONT,
    }
    app._apply_fonts = MagicMock()
    app.save_settings = MagicMock()
    return app


class TestSettingsWindowQt(unittest.TestCase):

    def setUp(self):
        from settings_window import SettingsWindow
        from PySide6.QtWidgets import QWidget
        self.mock_app = _make_mock_app()
        # Keep parent alive as instance attribute so GC doesn't collect it
        self._parent = QWidget()
        self.win = SettingsWindow(self._parent, self.mock_app)

    # ── 1-2. Cutover: correct imports ─────────────────────────────────────────

    def test_ui_py_imports_from_app(self):
        import importlib, ast
        src = open(os.path.join(_REPO, 'ui.py'), encoding='utf-8').read()
        tree = ast.parse(src)
        imports = [
            (n.module, alias.name)
            for n in ast.walk(tree)
            if isinstance(n, ast.ImportFrom)
            for alias in n.names
        ]
        self.assertIn(('app', 'OpenEngineApp'), imports,
                      "ui.py must import OpenEngineApp from 'app', not 'app_qt'")

    def test_app_py_has_no_qt_imports(self):
        src = open(os.path.join(_REPO, 'app.py'), encoding='utf-8').read()
        self.assertNotIn('app_qt',           src)
        self.assertNotIn('settings_window_qt', src)
        self.assertNotIn('geometry_tab_qt',  src)

    # ── 3. No _qt files remain ────────────────────────────────────────────────

    def test_no_qt_suffix_files_remain(self):
        qt_files = []
        for root, _, files in os.walk(_REPO):
            for f in files:
                if f.endswith('_qt.py'):
                    qt_files.append(os.path.join(root, f))
        self.assertEqual(qt_files, [],
                         f"Found leftover _qt files: {qt_files}")

    # ── 4. SettingsWindow type ────────────────────────────────────────────────

    def test_is_qdialog(self):
        self.assertIsInstance(self.win, QDialog)

    # ── 5. Tree nodes ─────────────────────────────────────────────────────────

    def test_tree_has_export_and_visual(self):
        tree = self.win._tree
        top_texts = [tree.topLevelItem(i).text(0)
                     for i in range(tree.topLevelItemCount())]
        self.assertIn('Export', top_texts)
        self.assertIn('Visual', top_texts)

    # ── 6. Geometry panel fields ──────────────────────────────────────────────

    def test_geometry_panel_has_n_grid(self):
        self.assertIsNotNone(self.win._dxf_n_grid)
        self.assertEqual(self.win._dxf_n_grid.text(), '500')

    # ── 7. Visual panel widgets ───────────────────────────────────────────────

    def test_visual_panel_has_slider_and_spinbox(self):
        self.assertIsNotNone(self.win._font_slider)
        self.assertIsNotNone(self.win._font_spin)

    # ── 8. Slider and text box sync ───────────────────────────────────────────

    def test_slider_spinbox_sync(self):
        self.win._font_slider.setValue(12)
        self.assertEqual(self.win._font_spin.text(), '12')
        self.win._font_spin.setText('18')
        self.assertEqual(self.win._font_slider.value(), 18)

    # ── 9. _apply_geometry saves settings ────────────────────────────────────

    def test_apply_geometry_saves(self):
        self.win._dxf_n_grid.setText('300')
        self.win._dxf_mirror.setChecked(False)
        self.win._apply_geometry()
        self.assertEqual(self.mock_app.settings['dxf_n_grid'], 300)
        self.assertFalse(self.mock_app.settings['dxf_mirror'])
        self.mock_app.save_settings.assert_called_once()

    # ── 10. _apply_geometry rejects bad n_grid ────────────────────────────────

    def test_apply_geometry_rejects_small_n_grid(self):
        self.win._dxf_n_grid.setText('5')
        with patch('PySide6.QtWidgets.QMessageBox.critical') as mock_err:
            self.win._apply_geometry()
            mock_err.assert_called_once()
        self.mock_app.save_settings.assert_not_called()

    # ── 11-12. _apply_visual ──────────────────────────────────────────────────

    def test_apply_visual_updates_base_font(self):
        self.win._font_spin.setText('12')
        self.win._apply_visual()
        self.assertEqual(constants.BASE_FONT, 12)

    def test_apply_visual_persists_to_settings(self):
        self.win._font_spin.setText('14')
        self.win._apply_visual()
        self.assertEqual(self.mock_app.settings['base_font'], 14)
        self.mock_app.save_settings.assert_called()


if __name__ == '__main__':
    unittest.main()
