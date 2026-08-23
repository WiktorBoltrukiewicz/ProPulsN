"""
tests/test_qt_update3.py — Update 3: Parameters tab tests.

Tests:
  1.  ParametersTab instantiates as a QWidget
  2.  Config combo is populated with at least one entry
  3.  Loading default.json populates R_throat field
  4.  Loading default.json populates P0 field
  5.  get_params() returns a dict after loading
  6.  get_params() R_throat is a positive float
  7.  Validation rejects non-numeric entry
  8.  Save writes JSON to a temp file
  9.  Loaded status label text contains filename
  10. _raw_data is set after loading
"""

import os
import sys
import json
import tempfile
import unittest
from unittest.mock import patch

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from PySide6.QtWidgets import QApplication, QWidget
_qapp = QApplication.instance() or QApplication(sys.argv)

from backend.app.core.param_loader import find_param_files

_DEFAULT_JSON = next(
    (f for f in find_param_files() if os.path.basename(f) == 'default.json'),
    find_param_files()[0] if find_param_files() else None,
)


class TestParametersTabQt(unittest.TestCase):

    def setUp(self):
        from tabs.parameters_tab import ParametersTab
        self.tab = ParametersTab()

    # ── 1. Type ───────────────────────────────────────────────────────────────

    def test_is_qwidget(self):
        self.assertIsInstance(self.tab, QWidget)

    # ── 2. Combo populated ────────────────────────────────────────────────────

    def test_combo_has_entries(self):
        self.assertGreater(self.tab._config_combo.count(), 0)

    # ── 3-4. Fields populated after load ─────────────────────────────────────

    @unittest.skipIf(_DEFAULT_JSON is None, "No param files found")
    def test_load_populates_r_throat(self):
        self.tab._load_file(_DEFAULT_JSON)
        self.assertNotEqual(self.tab._fields['R_throat'].text(), "")

    @unittest.skipIf(_DEFAULT_JSON is None, "No param files found")
    def test_load_populates_p0(self):
        self.tab._load_file(_DEFAULT_JSON)
        self.assertNotEqual(self.tab._fields['P0'].text(), "")

    # ── 5-6. get_params ───────────────────────────────────────────────────────

    @unittest.skipIf(_DEFAULT_JSON is None, "No param files found")
    def test_get_params_returns_dict(self):
        self.tab._load_file(_DEFAULT_JSON)
        result = self.tab.get_params()
        self.assertIsInstance(result, dict)

    @unittest.skipIf(_DEFAULT_JSON is None, "No param files found")
    def test_get_params_r_throat_positive(self):
        self.tab._load_file(_DEFAULT_JSON)
        params = self.tab.get_params()
        self.assertIn('R_throat', params)
        self.assertGreater(params['R_throat'], 0)

    # ── 7. Validation rejects non-numeric ────────────────────────────────────

    @unittest.skipIf(_DEFAULT_JSON is None, "No param files found")
    def test_validation_rejects_non_numeric(self):
        self.tab._load_file(_DEFAULT_JSON)
        self.tab._fields['R_throat'].setText("not_a_number")
        with patch('PySide6.QtWidgets.QMessageBox.critical') as mock_err:
            result = self.tab._write_fields_to_raw()
            self.assertFalse(result)
            mock_err.assert_called_once()

    # ── 8. Save writes JSON ───────────────────────────────────────────────────

    @unittest.skipIf(_DEFAULT_JSON is None, "No param files found")
    def test_save_writes_json(self):
        self.tab._load_file(_DEFAULT_JSON)
        with tempfile.NamedTemporaryFile(
            suffix='.json', delete=False, mode='w', encoding='utf-8'
        ) as f:
            tmp_path = f.name

        try:
            original = self.tab._current_file
            self.tab._current_file = tmp_path
            self.tab._save()
            with open(tmp_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.assertIsInstance(data, dict)
        finally:
            self.tab._current_file = original
            os.unlink(tmp_path)

    # ── 9. Status label ───────────────────────────────────────────────────────

    @unittest.skipIf(_DEFAULT_JSON is None, "No param files found")
    def test_status_label_shows_filename(self):
        self.tab._load_file(_DEFAULT_JSON)
        self.assertIn(
            os.path.basename(_DEFAULT_JSON),
            self.tab._status_label.text(),
        )

    # ── 10. raw_data set ─────────────────────────────────────────────────────

    @unittest.skipIf(_DEFAULT_JSON is None, "No param files found")
    def test_raw_data_set_after_load(self):
        self.tab._load_file(_DEFAULT_JSON)
        self.assertIsNotNone(self.tab._raw_data)


if __name__ == '__main__':
    unittest.main()
