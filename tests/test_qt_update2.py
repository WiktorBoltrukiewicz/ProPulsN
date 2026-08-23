"""
tests/test_qt_update2.py — Update 2: Geometry tab tests.

Tests:
  1.  GeometryTab instantiates as a QWidget
  2.  Stats group box is present
  3.  All 5 stat labels are populated (not "—") after init
  4.  Matplotlib canvas is embedded (FigureCanvasQTAgg present)
  5.  Navigation toolbar is present
  6.  Refresh button triggers replot without errors
  7.  Stat label "Throat radius" contains "mm"
  8.  Stat label "Total length" contains "mm"
  9.  Stat label "Expansion ratio E_r" is a valid float
  10. DXF export shows error dialog when ezdxf is missing (monkeypatched)
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from PySide6.QtWidgets import QApplication, QWidget
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

_qapp = QApplication.instance() or QApplication(sys.argv)


def _make_tab():
    from tabs.geometry_tab import GeometryTab
    return GeometryTab()


class TestGeometryTabQt(unittest.TestCase):

    def setUp(self):
        self.tab = _make_tab()

    # ── 1. Type check ─────────────────────────────────────────────────────────

    def test_is_qwidget(self):
        self.assertIsInstance(self.tab, QWidget)

    # ── 2. Stats box ──────────────────────────────────────────────────────────

    def test_stat_labels_dict_has_five_keys(self):
        self.assertEqual(len(self.tab._stat_labels), 5)

    # ── 3. Labels populated ───────────────────────────────────────────────────

    def test_stat_labels_not_empty(self):
        for key, lbl in self.tab._stat_labels.items():
            self.assertNotEqual(lbl.text(), "—", f"Label '{key}' was not updated.")

    # ── 4. Canvas present ─────────────────────────────────────────────────────

    def test_canvas_is_figure_canvas(self):
        self.assertIsInstance(self.tab._canvas, FigureCanvasQTAgg)

    # ── 5. Toolbar present ────────────────────────────────────────────────────

    def test_toolbar_present(self):
        from matplotlib.backends.backend_qt import NavigationToolbar2QT
        # Walk children to find the toolbar
        found = any(
            isinstance(child, NavigationToolbar2QT)
            for child in self.tab.findChildren(NavigationToolbar2QT)
        )
        self.assertTrue(found, "NavigationToolbar2QT not found in widget tree.")

    # ── 6. Refresh replot ─────────────────────────────────────────────────────

    def test_refresh_does_not_raise(self):
        try:
            self.tab._compute_and_plot()
        except Exception as exc:
            self.fail(f"_compute_and_plot() raised {exc}")

    # ── 7-8. Label units ──────────────────────────────────────────────────────

    def test_throat_radius_has_mm(self):
        self.assertIn("mm", self.tab._stat_labels["Throat radius"].text())

    def test_total_length_has_mm(self):
        self.assertIn("mm", self.tab._stat_labels["Total length"].text())

    # ── 9. Expansion ratio is numeric ─────────────────────────────────────────

    def test_expansion_ratio_is_float(self):
        text = self.tab._stat_labels["Expansion ratio E_r"].text()
        try:
            float(text)
        except ValueError:
            self.fail(f"Expansion ratio text '{text}' is not a valid float.")

    # ── 10. DXF export — missing ezdxf shows dialog ───────────────────────────

    def test_dxf_export_missing_ezdxf_shows_error(self):
        import builtins
        real_import = builtins.__import__

        def _block_ezdxf(name, *args, **kwargs):
            if name == 'ezdxf':
                raise ImportError("blocked for test")
            return real_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=_block_ezdxf):
            with patch('PySide6.QtWidgets.QMessageBox.critical') as mock_crit:
                self.tab._export_dxf()
                mock_crit.assert_called_once()


if __name__ == '__main__':
    unittest.main()
