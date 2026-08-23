"""
tabs/parameters_tab_qt.py - Parameters tab: load / edit / save rocket parameters.
"""

import os
import json

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QLineEdit, QComboBox,
    QGroupBox, QScrollArea, QFrame, QMessageBox,
    QFileDialog, QSizePolicy,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from backend.app.core.param_loader import find_param_files, load_params, PARAMS_DIR
import constants

_GRAY = "#6c7086"

# Gas-property 3-node table rows  (label, unit, key_chamber, key_throat, key_exit)
_GAS_ROWS = [
    ('Adiabatic index  gamma', '-',
     'gamma_chamber', 'gamma_throat', 'gamma_exit'),
    ('Specific heat  Cp', 'J/(kg·K)',
     'Cpcg_chamber', 'Cpcg_throat', 'Cpcg_exit'),
    ('Prandtl number', '-',
     'Prcg_chamber', 'Prcg_throat', 'Prcg_exit'),
    ('Molar mass', 'kg/mol',
     'combustion_molar_mass_chamber',
     'combustion_molar_mass_throat',
     'combustion_molar_mass_exit'),
]

_SIMPLE_SECTIONS = [
    ("Initial Conditions", [
        ('N0',       'M²  at nozzle inlet',          '-'),
        ('P0',       'Inlet static pressure',         'Pa'),
        ('T0',       'Inlet static temperature',      'K'),
    ]),
    ("Nozzle Geometry", [
        ('R_throat', 'Throat radius',                         'm'),
        ('E_r',      'Expansion ratio  (A_exit / A_throat)',  '-'),
    ]),
    ("Mass Flow", [
        ('mdot_gas', 'Gas mass flow  ṁ', 'kg/s'),
    ]),
]

_SCALAR_GAS = [
    ('eta',    'Dynamic viscosity  η',          'Pa·s'),
    ('c_star', 'Characteristic velocity  c*',   'm/s'),
    ('sonvel', 'Sound velocity estimate',        'm/s'),
]


class ParametersTab(QWidget):
    """Load / edit / save rocket performance parameters from JSON config files."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._raw_data     = None
        self._current_file = None
        self._config_files = []
        self._fields: dict[str, QLineEdit] = {}
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(6)
        root.addWidget(self._make_config_bar())
        root.addWidget(self._make_scroll_area(), stretch=1)

    def _make_config_bar(self):
        box = QGroupBox("Configuration File")
        bar = QHBoxLayout(box)
        bar.setSpacing(6)

        bar.addWidget(QLabel("Config:"))

        self._config_combo = QComboBox()
        self._config_combo.setMinimumWidth(260)
        bar.addWidget(self._config_combo)

        for text, slot in [
            ("Load",     self._load_selected),
            ("Save",     self._save),
            ("Save As…", self._save_as),
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            bar.addWidget(btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_config_list)
        bar.addWidget(refresh_btn)

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color: #45475a;")
        bar.addWidget(sep)

        self._status_label = QLabel(
            "No config loaded — select one from the dropdown and click Load."
        )
        self._status_label.setStyleSheet(f"color: {_GRAY};")
        bar.addWidget(self._status_label, stretch=1)

        self._refresh_config_list()
        return box

    def _make_scroll_area(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        for title, params in _SIMPLE_SECTIONS:
            layout.addWidget(self._make_simple_section(title, params))

        layout.addWidget(self._make_gas_table())
        layout.addStretch()

        scroll.setWidget(container)
        return scroll

    def _make_simple_section(self, title, params):
        box = QGroupBox(title)
        grid = QGridLayout(box)
        grid.setContentsMargins(14, 8, 14, 8)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        grid.setColumnMinimumWidth(0, 280)

        for row, (key, label, unit) in enumerate(params):
            grid.addWidget(QLabel(label), row, 0, Qt.AlignLeft)
            entry = QLineEdit()
            entry.setFixedWidth(160)
            grid.addWidget(entry, row, 1)
            unit_lbl = QLabel(unit)
            unit_lbl.setStyleSheet(f"color: {_GRAY};")
            grid.addWidget(unit_lbl, row, 2, Qt.AlignLeft)
            self._fields[key] = entry

        grid.setColumnStretch(3, 1)
        return box

    def _make_gas_table(self):
        box = QGroupBox("Gas Properties  (3 nodes: Chamber · Throat · Exit)")
        grid = QGridLayout(box)
        grid.setContentsMargins(14, 8, 14, 8)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        grid.setColumnMinimumWidth(0, 280)

        bold_font = QFont()
        bold_font.setBold(True)

        # Column headers
        for col, text in enumerate(['', 'Chamber', 'Throat', 'Exit', ''], 0):
            if text:
                lbl = QLabel(text)
                lbl.setFont(bold_font)
                grid.addWidget(lbl, 0, col + 1, Qt.AlignLeft)

        # 3-node rows
        for r, (label, unit, k_ch, k_th, k_ex) in enumerate(_GAS_ROWS, 1):
            grid.addWidget(QLabel(label), r, 0, Qt.AlignLeft)
            for c, key in enumerate([k_ch, k_th, k_ex]):
                entry = QLineEdit()
                entry.setFixedWidth(130)
                grid.addWidget(entry, r, c + 1)
                self._fields[key] = entry
            unit_lbl = QLabel(unit)
            unit_lbl.setStyleSheet(f"color: {_GRAY};")
            grid.addWidget(unit_lbl, r, 4, Qt.AlignLeft)

        # Divider
        sep_row = len(_GAS_ROWS) + 1
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #45475a;")
        grid.addWidget(sep, sep_row, 0, 1, 5)

        # Scalar rows
        for i, (key, label, unit) in enumerate(_SCALAR_GAS, sep_row + 1):
            grid.addWidget(QLabel(label), i, 0, Qt.AlignLeft)
            entry = QLineEdit()
            entry.setFixedWidth(130)
            grid.addWidget(entry, i, 1)
            unit_lbl = QLabel(unit)
            unit_lbl.setStyleSheet(f"color: {_GRAY};")
            grid.addWidget(unit_lbl, i, 4, Qt.AlignLeft)
            self._fields[key] = entry

        grid.setColumnStretch(5, 1)
        return box

    # ── Config file management ────────────────────────────────────────────────

    def _refresh_config_list(self):
        self._config_files = find_param_files()
        names = [os.path.basename(f) for f in self._config_files]
        current = self._config_combo.currentText()
        self._config_combo.blockSignals(True)
        self._config_combo.clear()
        self._config_combo.addItems(names)
        if current in names:
            self._config_combo.setCurrentIndex(names.index(current))
        self._config_combo.blockSignals(False)

    def _load_selected(self):
        idx = self._config_combo.currentIndex()
        if idx < 0 or not self._config_files:
            QMessageBox.warning(self, "No config selected",
                                "Select a config file from the dropdown first.")
            return
        self._load_file(self._config_files[idx])

    def _load_file(self, filepath):
        try:
            flat, raw = load_params(filepath)
        except Exception as exc:
            QMessageBox.critical(self, "Load Error",
                                 f"Could not load:\n{filepath}\n\n{exc}")
            return

        self._raw_data     = raw
        self._current_file = filepath

        for key, entry in self._fields.items():
            if key in flat:
                val = flat[key]
                if isinstance(val, float):
                    if abs(val) >= 1e6 or (0 < abs(val) < 1e-3):
                        entry.setText(f"{val:.6e}")
                    else:
                        entry.setText(f"{val:g}")
                else:
                    entry.setText(str(val))
            else:
                entry.setText("")

        self._status_label.setText(f"Loaded:  {os.path.basename(filepath)}")
        self._status_label.setStyleSheet("color: #a6e3a1;")

    # ── Collect / validate ────────────────────────────────────────────────────

    def _collect_values(self):
        flat, errors = {}, []
        for key, entry in self._fields.items():
            s = entry.text().strip()
            if not s:
                continue
            try:
                flat[key] = float(s)
            except ValueError:
                errors.append(f"  {key}: '{s}' is not a valid number")
        if errors:
            return None, "Invalid values:\n" + "\n".join(errors)
        return flat, None

    def _write_fields_to_raw(self):
        flat, err = self._collect_values()
        if err:
            QMessageBox.critical(self, "Validation Error", err)
            return False
        for section in self._raw_data.values():
            if not isinstance(section, dict):
                continue
            for param_key, param_data in section.items():
                if param_key.startswith('_'):
                    continue
                if (isinstance(param_data, dict)
                        and 'value' in param_data
                        and param_key in flat):
                    old = param_data['value']
                    new = flat[param_key]
                    if isinstance(old, int) and new == int(new):
                        new = int(new)
                    param_data['value'] = new
        return True

    # ── Save ──────────────────────────────────────────────────────────────────

    def _save(self):
        if self._raw_data is None or self._current_file is None:
            QMessageBox.warning(self, "No config loaded",
                                "Load a config file first, then edit and save.")
            return
        if not self._write_fields_to_raw():
            return
        try:
            with open(self._current_file, 'w', encoding='utf-8') as f:
                json.dump(self._raw_data, f, ensure_ascii=False, indent=4)
            self._status_label.setText(
                f"Saved:  {os.path.basename(self._current_file)}")
            self._status_label.setStyleSheet("color: #a6e3a1;")
        except Exception as exc:
            QMessageBox.critical(self, "Save Error", str(exc))

    def _save_as(self):
        if self._raw_data is None:
            QMessageBox.warning(self, "No config loaded",
                                "Load a config file first to use as a base.")
            return
        if not self._write_fields_to_raw():
            return
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save config as…", PARAMS_DIR,
            "JSON config (*.json);;All files (*.*)",
        )
        if not filepath:
            return
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self._raw_data, f, ensure_ascii=False, indent=4)
            self._current_file = filepath
            self._status_label.setText(
                f"Saved as:  {os.path.basename(filepath)}")
            self._status_label.setStyleSheet("color: #a6e3a1;")
            self._refresh_config_list()
            basename = os.path.basename(filepath)
            names = [self._config_combo.itemText(i)
                     for i in range(self._config_combo.count())]
            if basename in names:
                self._config_combo.setCurrentIndex(names.index(basename))
        except Exception as exc:
            QMessageBox.critical(self, "Save Error", str(exc))

    # ── Public API ────────────────────────────────────────────────────────────

    def get_params(self):
        """Return a flat dict of current field values (empty fields omitted)."""
        flat, _ = self._collect_values()
        return flat or {}
