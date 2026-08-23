"""
tests/test_qt_update5.py — Update 5: Results tab tests.

Tests:
  1.  ResultsTab instantiates as a QWidget
  2.  Sub-tabs: exactly 2 (Plot Creator + Results Table)
  3.  Sub-tab titles correct
  4.  refresh_file_list() runs without error
  5.  CSV reader parses a synthetic CSV correctly
  6.  CSV reader skips comment lines
  7.  Axis combos populate after loading data
  8.  Table model row count matches data
  9.  Table model column count matches data
  10. Table model returns numeric string for cell data
  11. Plot renders without error after loading data
  12. Clear resets the plot without error
"""

import os
import sys
import csv
import tempfile
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from PySide6.QtWidgets import QApplication, QWidget
_qapp = QApplication.instance() or QApplication(sys.argv)

import numpy as np


def _make_tab():
    from tabs.results_tab import ResultsTab
    return ResultsTab()


def _write_tmp_csv(rows, headers, comments=None):
    """Write a temporary CSV file; returns its path."""
    f = tempfile.NamedTemporaryFile(
        mode='w', suffix='.csv', delete=False, encoding='utf-8', newline=''
    )
    writer = csv.writer(f)
    if comments:
        for c in comments:
            writer.writerow([f'# {c}'])
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    f.close()
    return f.name


class TestResultsTabQt(unittest.TestCase):

    def setUp(self):
        self.tab = _make_tab()

    # ── 1. Type ───────────────────────────────────────────────────────────────

    def test_is_qwidget(self):
        self.assertIsInstance(self.tab, QWidget)

    # ── 2-3. Sub-tabs ─────────────────────────────────────────────────────────

    def test_sub_tab_count(self):
        self.assertEqual(self.tab._sub_tabs.count(), 3)

    def test_sub_tab_titles(self):
        titles = [self.tab._sub_tabs.tabText(i).strip() for i in range(3)]
        self.assertIn("Plot Creator",  titles)
        self.assertIn("Results Table", titles)
        self.assertIn("Wall Export",   titles)

    # ── 4. refresh_file_list ──────────────────────────────────────────────────

    def test_refresh_file_list_no_error(self):
        try:
            self.tab.refresh_file_list()
        except Exception as exc:
            self.fail(f"refresh_file_list() raised {exc}")

    # ── 5-6. CSV reader ───────────────────────────────────────────────────────

    def test_csv_reader_parses_data(self):
        from tabs.results_tab import _read_csv
        path = _write_tmp_csv(
            rows=[[1.0, 2.0], [3.0, 4.0]],
            headers=['x', 'y'],
        )
        try:
            data, cols = _read_csv(path)
            self.assertEqual(cols, ['x', 'y'])
            np.testing.assert_array_equal(data['x'], [1.0, 3.0])
            np.testing.assert_array_equal(data['y'], [2.0, 4.0])
        finally:
            os.unlink(path)

    def test_csv_reader_skips_comments(self):
        from tabs.results_tab import _read_csv
        path = _write_tmp_csv(
            rows=[[10.0, 20.0]],
            headers=['a', 'b'],
            comments=['this is a comment'],
        )
        try:
            data, cols = _read_csv(path)
            self.assertEqual(len(data['a']), 1)
        finally:
            os.unlink(path)

    # ── 7. Axis combos populate ───────────────────────────────────────────────

    def test_axis_combos_populate(self):
        path = _write_tmp_csv(
            rows=[[1, 2], [3, 4]],
            headers=['x', 'M'],
        )
        try:
            self.tab._load_from_path(path)
            self.assertEqual(self.tab._x_combo.count(), 2)
            self.assertEqual(self.tab._y_combo.count(), 2)
        finally:
            os.unlink(path)

    # ── 8-10. Table model ─────────────────────────────────────────────────────

    def test_table_model_row_count(self):
        from tabs.results_tab import _CsvTableModel
        data = {'x': np.array([1.0, 2.0, 3.0]), 'y': np.array([4.0, 5.0, 6.0])}
        model = _CsvTableModel(data, ['x', 'y'])
        self.assertEqual(model.rowCount(), 3)

    def test_table_model_col_count(self):
        from tabs.results_tab import _CsvTableModel
        data = {'x': np.array([1.0]), 'y': np.array([2.0]), 'z': np.array([3.0])}
        model = _CsvTableModel(data, ['x', 'y', 'z'])
        self.assertEqual(model.columnCount(), 3)

    def test_table_model_data_is_string(self):
        from tabs.results_tab import _CsvTableModel
        from PySide6.QtCore import QModelIndex, Qt
        data = {'v': np.array([3.14159])}
        model = _CsvTableModel(data, ['v'])
        idx = model.index(0, 0)
        val = model.data(idx, Qt.DisplayRole)
        self.assertIsInstance(val, str)
        self.assertIn('3.14', val)

    # ── 11-12. Plot ───────────────────────────────────────────────────────────

    def test_plot_renders_without_error(self):
        path = _write_tmp_csv(
            rows=[[i, i * 2] for i in range(10)],
            headers=['x', 'y'],
        )
        try:
            self.tab._load_from_path(path)
            self.tab._x_combo.setCurrentText('x')
            self.tab._y_combo.setCurrentText('y')
            self.tab._do_plot()
        except Exception as exc:
            self.fail(f"_do_plot() raised {exc}")
        finally:
            os.unlink(path)

    def test_clear_plot_no_error(self):
        try:
            self.tab._clear_plot()
        except Exception as exc:
            self.fail(f"_clear_plot() raised {exc}")


if __name__ == '__main__':
    unittest.main()
