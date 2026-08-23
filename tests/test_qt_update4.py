"""
tests/test_qt_update4.py — Update 4: Simulation tab tests.

Tests:
  1.  SimulationTab instantiates as a QWidget
  2.  All 4 solver fields present (n_grid, max_iterations, tol, relax)
  3.  Solver field default values are correct
  4.  Mode combo has exactly 2 options
  5.  Switching to Fixed disables the tol entry
  6.  Switching back to Convergence re-enables tol
  7.  Convergence regex parses a valid line correctly
  8.  Convergence regex ignores a non-matching line
  9.  _build_temp_json produces a valid JSON file (with default params)
  10. terminate() is safe to call when no simulation is running
  11. Console widget is read-only (QPlainTextEdit)
  12. Progress bar starts hidden
"""

import os
import sys
import json
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from PySide6.QtWidgets import QApplication, QWidget, QPlainTextEdit
_qapp = QApplication.instance() or QApplication(sys.argv)


def _make_tab():
    from tabs.simulation_tab import SimulationTab
    return SimulationTab()


class TestSimulationTabQt(unittest.TestCase):

    def setUp(self):
        self.tab = _make_tab()

    # ── 1. Type ───────────────────────────────────────────────────────────────

    def test_is_qwidget(self):
        self.assertIsInstance(self.tab, QWidget)

    # ── 2. Solver fields present ──────────────────────────────────────────────

    def test_all_solver_fields_present(self):
        for key in ('n_grid', 'max_iterations', 'tol', 'relax'):
            self.assertIn(key, self.tab._fields,
                          f"Missing solver field: {key}")

    # ── 3. Default values ─────────────────────────────────────────────────────

    def test_default_n_grid(self):
        self.assertEqual(self.tab._fields['n_grid'].text(), '100')

    def test_default_tol(self):
        self.assertEqual(self.tab._fields['tol'].text(), '1e-6')

    # ── 4. Mode combo ─────────────────────────────────────────────────────────

    def test_mode_combo_count(self):
        self.assertEqual(self.tab._mode_combo.count(), 2)

    # ── 5-6. Tol entry enable/disable ────────────────────────────────────────

    def test_fixed_mode_disables_tol(self):
        self.tab._mode_combo.setCurrentText('Fixed iterations')
        self.assertFalse(self.tab._tol_entry.isEnabled())

    def test_convergence_mode_enables_tol(self):
        self.tab._mode_combo.setCurrentText('Fixed iterations')
        self.tab._mode_combo.setCurrentText('Convergence-based')
        self.assertTrue(self.tab._tol_entry.isEnabled())

    # ── 7-8. Convergence regex ────────────────────────────────────────────────

    def test_conv_regex_parses_valid_line(self):
        from tabs.simulation_tab import _CONV_RE
        line = "[Iteration 5] R_N=1.23e-04 R_P=2.34e-05 R_T=3.45e-06 R_F=4.56e-07"
        m = _CONV_RE.search(line)
        self.assertIsNotNone(m)
        self.assertEqual(int(m.group(1)), 5)
        self.assertAlmostEqual(float(m.group(2)), 1.23e-4)

    def test_conv_regex_ignores_plain_line(self):
        from tabs.simulation_tab import _CONV_RE
        self.assertIsNone(_CONV_RE.search("Stage 1 complete."))

    # ── 9. Temp JSON builds ───────────────────────────────────────────────────

    def test_build_temp_json_produces_valid_json(self):
        path = self.tab._build_temp_json()
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.assertIsInstance(data, dict)
        finally:
            if os.path.exists(path):
                os.remove(path)

    # ── 10. terminate() safe when idle ───────────────────────────────────────

    def test_terminate_safe_when_idle(self):
        try:
            self.tab.terminate()
        except Exception as exc:
            self.fail(f"terminate() raised {exc} when idle")

    # ── 11. Console is read-only ──────────────────────────────────────────────

    def test_console_is_readonly(self):
        self.assertIsInstance(self.tab._console, QPlainTextEdit)
        self.assertTrue(self.tab._console.isReadOnly())

    # ── 12. Progress bar starts hidden ───────────────────────────────────────

    def test_progress_bar_starts_hidden(self):
        self.assertFalse(self.tab._progress.isVisible())


if __name__ == '__main__':
    unittest.main()
