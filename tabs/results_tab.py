"""
tabs/results_tab_qt.py - Results tab: Plot Creator, Results Table, Wall Export.
"""

import os
import sys
import csv
import subprocess

import numpy as np
import matplotlib
matplotlib.use("QtAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import (
    FigureCanvasQTAgg,
    NavigationToolbar2QT,
)

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox,
    QGroupBox, QTabWidget, QSplitter,
    QTableView, QAbstractItemView,
    QSizePolicy, QMessageBox, QFrame,
    QCheckBox, QLineEdit, QScrollArea,
    QGridLayout, QFileDialog, QDialog,
)
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex
from PySide6.QtGui import QFont

import constants

_REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Dark palette colours
_BG    = "#1e1e2e"
_AX_BG = "#181825"
_FG    = "#cdd6f4"
_GRID  = "#313244"
_GRAY  = "#6c7086"
_BLUE  = "#89b4fa"

# Columns always used for X/Y/Z coordinates — excluded from property checkboxes
_COORD_COLS = {'x_m', 'r_m'}

# Sentinel value in the "Color by" combo meaning no property colouring
_COLOR_NONE = "(uniform colour)"

# Fluent-recognised field names: OpenEngine column → Fluent profile field name
_FLUENT_FIELD_MAP = {
    'T_K':          'temperature',
    'T_aw_K':       'temperature',
    'P_Pa':         'pressure',
    'M':            'mach-number',
    'h_gas_W_m2K':  'heat-transfer-coefficient',
}


# ── 3-D preview dialog ────────────────────────────────────────────────────────

class _Preview3DDialog(QDialog):
    """Non-modal window showing the nozzle wall as a 3-D point cloud.

    The embedded NavigationToolbar lets the user pan, zoom, rotate, and
    save the figure as an image file via the toolbar's floppy-disk button.
    """

    def __init__(self, X, Y, Z, color_data, color_label, n_pts, n_planes,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("3D Wall Preview")
        self.setModal(False)
        self.resize(960, 720)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)

        fig = Figure(figsize=(9, 7), facecolor=_BG)
        ax  = fig.add_subplot(111, projection='3d')
        ax.set_facecolor(_AX_BG)

        # Scatter — point size scales down for large clouds
        pt_size = max(0.3, min(4.0, 2000.0 / max(len(X), 1)))

        if color_data is not None:
            sc = ax.scatter(X, Y, Z, c=color_data, cmap='plasma',
                            s=pt_size, linewidths=0)
            cbar = fig.colorbar(sc, ax=ax, shrink=0.55, pad=0.1)
            cbar.set_label(color_label, color=_FG)
            cbar.ax.yaxis.set_tick_params(color=_FG)
            for lbl in cbar.ax.get_yticklabels():
                lbl.set_color(_FG)
        else:
            ax.scatter(X, Y, Z, color=_BLUE, s=pt_size, linewidths=0)

        ax.set_xlabel('X  [m]', color=_FG, labelpad=6)
        ax.set_ylabel('Y  [m]', color=_FG, labelpad=6)
        ax.set_zlabel('Z  [m]', color=_FG, labelpad=6)
        ax.tick_params(colors=_FG)
        ax.xaxis.pane.fill = False
        ax.yaxis.pane.fill = False
        ax.zaxis.pane.fill = False
        ax.xaxis.pane.set_edgecolor(_GRID)
        ax.yaxis.pane.set_edgecolor(_GRID)
        ax.zaxis.pane.set_edgecolor(_GRID)
        ax.grid(True, color=_GRID, alpha=0.4)

        # Equal scale on all three axes: 10 mm looks the same in every direction
        ax.set_aspect('equal')

        total = n_pts * n_planes
        title = (f"Nozzle wall — {total:,} points  "
                 f"({n_pts} wall pts × {n_planes} planes)")
        ax.set_title(title, color=_FG, pad=10)

        canvas  = FigureCanvasQTAgg(fig)
        toolbar = NavigationToolbar2QT(canvas, self)
        toolbar.setStyleSheet(
            f"background-color: {_BG}; color: {_FG}; border: none;"
        )

        layout.addWidget(toolbar)
        layout.addWidget(canvas, stretch=1)


# ── Table model ───────────────────────────────────────────────────────────────

class _CsvTableModel(QAbstractTableModel):
    """Read-only model backed by a dict of numpy arrays."""

    def __init__(self, data: dict, columns: list, parent=None):
        super().__init__(parent)
        self._data    = data
        self._columns = columns
        self._n_rows  = len(next(iter(data.values()))) if data else 0

    def rowCount(self, parent=QModelIndex()):
        return self._n_rows

    def columnCount(self, parent=QModelIndex()):
        return len(self._columns)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        if role == Qt.DisplayRole:
            col = self._columns[index.column()]
            val = self._data[col][index.row()]
            return f"{val:.6g}"
        if role == Qt.TextAlignmentRole:
            return Qt.AlignRight | Qt.AlignVCenter
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return self._columns[section]
            return str(section + 1)
        return None


# ── Tab ───────────────────────────────────────────────────────────────────────

class ResultsTab(QWidget):
    """CSV loader, interactive Plot Creator, Results Table, and Wall Export."""

    RESULTS_DIR = os.path.join(_REPO_DIR, 'results')

    def __init__(self, parent=None):
        super().__init__(parent)
        self._csv_files: list[str] = []
        self._data:    dict        = {}
        self._columns: list[str]   = []
        self._export_checkboxes: dict = {}   # col_name -> QCheckBox
        self._build_ui()
        self._refresh_file_list()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(6)
        root.addWidget(self._make_file_bar())
        root.addWidget(self._make_sub_tabs(), stretch=1)

    def _make_file_bar(self):
        box = QGroupBox("Results File")
        bar = QHBoxLayout(box)
        bar.setSpacing(6)

        bar.addWidget(QLabel("File:"))

        self._file_combo = QComboBox()
        self._file_combo.setMinimumWidth(320)
        bar.addWidget(self._file_combo)

        load_btn = QPushButton("Load")
        load_btn.clicked.connect(self._load_selected)
        bar.addWidget(load_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_file_list)
        bar.addWidget(refresh_btn)

        folder_btn = QPushButton("Open Results Folder")
        folder_btn.clicked.connect(self._open_folder)
        bar.addWidget(folder_btn)

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color: #45475a;")
        bar.addWidget(sep)

        self._status_label = QLabel(
            "No file loaded — select a CSV and click Load."
        )
        self._status_label.setStyleSheet(f"color: {_GRAY};")
        bar.addWidget(self._status_label, stretch=1)

        return box

    def _make_sub_tabs(self):
        self._sub_tabs = QTabWidget()

        plot_widget = QWidget()
        self._sub_tabs.addTab(plot_widget, "  Plot Creator  ")
        self._build_plot_creator(plot_widget)

        table_widget = QWidget()
        self._sub_tabs.addTab(table_widget, "  Results Table  ")
        self._build_results_table(table_widget)

        export_widget = QWidget()
        self._sub_tabs.addTab(export_widget, "  Wall Export  ")
        self._build_wall_export(export_widget)

        return self._sub_tabs

    # ── Plot Creator ──────────────────────────────────────────────────────────

    def _build_plot_creator(self, parent):
        splitter = QSplitter(Qt.Horizontal)
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.addWidget(splitter)

        ctrl_box = QGroupBox("Axes")
        ctrl_box.setMaximumWidth(260)
        ctrl_layout = QVBoxLayout(ctrl_box)
        ctrl_layout.setContentsMargins(14, 10, 14, 10)
        ctrl_layout.setSpacing(10)

        ctrl_layout.addWidget(QLabel("X axis:"))
        self._x_combo = QComboBox()
        ctrl_layout.addWidget(self._x_combo)

        ctrl_layout.addWidget(QLabel("Y axis:"))
        self._y_combo = QComboBox()
        ctrl_layout.addWidget(self._y_combo)

        ctrl_layout.addSpacing(8)

        plot_btn = QPushButton("Plot")
        plot_btn.clicked.connect(self._do_plot)
        ctrl_layout.addWidget(plot_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear_plot)
        ctrl_layout.addWidget(clear_btn)

        ctrl_layout.addStretch()
        splitter.addWidget(ctrl_box)

        plot_box = QGroupBox("Plot")
        plot_layout = QVBoxLayout(plot_box)
        plot_layout.setContentsMargins(4, 4, 4, 4)
        plot_layout.setSpacing(0)

        self._fig = Figure(figsize=(10, 6), facecolor=_BG)
        self._ax  = self._fig.add_subplot(111)
        self._ax.set_facecolor(_AX_BG)
        _style_axes(self._ax)

        self._canvas = FigureCanvasQTAgg(self._fig)
        self._canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        toolbar = NavigationToolbar2QT(self._canvas, plot_box)
        toolbar.setStyleSheet(
            f"background-color: {_BG}; color: {_FG}; border: none;"
        )

        plot_layout.addWidget(self._canvas)
        plot_layout.addWidget(toolbar)
        splitter.addWidget(plot_box)
        splitter.setSizes([220, 900])

        self._draw_placeholder()

    # ── Results Table ─────────────────────────────────────────────────────────

    def _build_results_table(self, parent):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(4)

        self._table_view = QTableView()
        self._table_view.setAlternatingRowColors(True)
        self._table_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table_view.horizontalHeader().setStretchLastSection(True)
        self._table_view.verticalHeader().setDefaultSectionSize(
            max(int(constants.BASE_FONT * 1.8), 22)
        )
        layout.addWidget(self._table_view, stretch=1)

        bottom = QHBoxLayout()
        self._row_count_label = QLabel("No data loaded.")
        self._row_count_label.setStyleSheet(f"color: {_GRAY};")
        bottom.addWidget(self._row_count_label)
        bottom.addStretch()
        folder_btn = QPushButton("Open Results Folder")
        folder_btn.clicked.connect(self._open_folder)
        bottom.addWidget(folder_btn)
        layout.addLayout(bottom)

    # ── Wall Export ───────────────────────────────────────────────────────────

    def _build_wall_export(self, parent):
        root = QVBoxLayout(parent)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # ── Properties ───────────────────────────────────────────────────────
        props_box = QGroupBox("Fluent Profile Fields")
        props_outer = QVBoxLayout(props_box)
        props_outer.setContentsMargins(10, 8, 10, 10)

        coord_note = QLabel(
            "Coordinates X Y Z are always included.  "
            "Only Ansys Fluent-recognised fields are shown."
        )
        coord_note.setStyleSheet(f"color: {_GRAY};")
        props_outer.addWidget(coord_note)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(160)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        self._cb_container = QWidget()
        self._cb_grid = QGridLayout(self._cb_container)
        self._cb_grid.setContentsMargins(0, 4, 0, 4)
        self._cb_grid.setHorizontalSpacing(20)
        self._cb_grid.setVerticalSpacing(4)

        placeholder = QLabel("Load a results file to see available properties.")
        placeholder.setStyleSheet(f"color: {_GRAY};")
        self._cb_grid.addWidget(placeholder, 0, 0)

        scroll.setWidget(self._cb_container)
        props_outer.addWidget(scroll)

        sel_bar = QHBoxLayout()
        sel_all_btn = QPushButton("Select All")
        sel_all_btn.clicked.connect(self._select_all_props)
        sel_none_btn = QPushButton("Deselect All")
        sel_none_btn.clicked.connect(self._deselect_all_props)
        sel_bar.addWidget(sel_all_btn)
        sel_bar.addWidget(sel_none_btn)
        sel_bar.addStretch()
        props_outer.addLayout(sel_bar)

        root.addWidget(props_box)

        # ── Revolve ───────────────────────────────────────────────────────────
        rev_box = QGroupBox("Revolve Around Engine Axis")
        rev_layout = QGridLayout(rev_box)
        rev_layout.setContentsMargins(14, 10, 14, 12)
        rev_layout.setHorizontalSpacing(10)
        rev_layout.setVerticalSpacing(8)

        self._revolve_cb = QCheckBox("Enable revolve")
        self._revolve_cb.setChecked(True)
        self._revolve_cb.toggled.connect(self._on_revolve_toggled)
        rev_layout.addWidget(self._revolve_cb, 0, 0, 1, 4)

        rev_layout.addWidget(QLabel("Start angle:"), 1, 0, Qt.AlignRight)
        self._revolve_start = QLineEdit("0")
        self._revolve_start.setFixedWidth(70)
        self._revolve_start.setAlignment(Qt.AlignCenter)
        rev_layout.addWidget(self._revolve_start, 1, 1)
        rev_layout.addWidget(QLabel("°"), 1, 2, Qt.AlignLeft)

        rev_layout.addWidget(QLabel("End angle:"), 2, 0, Qt.AlignRight)
        self._revolve_end = QLineEdit("360")
        self._revolve_end.setFixedWidth(70)
        self._revolve_end.setAlignment(Qt.AlignCenter)
        rev_layout.addWidget(self._revolve_end, 2, 1)
        rev_layout.addWidget(QLabel("°"), 2, 2, Qt.AlignLeft)

        rev_layout.addWidget(QLabel("Number of planes:"), 3, 0, Qt.AlignRight)
        self._revolve_n = QLineEdit("36")
        self._revolve_n.setFixedWidth(70)
        self._revolve_n.setAlignment(Qt.AlignCenter)
        rev_layout.addWidget(self._revolve_n, 3, 1)
        hint = QLabel("(= every 10° for 0–360°)")
        hint.setStyleSheet(f"color: {_GRAY};")
        rev_layout.addWidget(hint, 3, 2, 1, 2, Qt.AlignLeft)

        rev_layout.setColumnStretch(3, 1)
        root.addWidget(rev_box)

        # ── Operating pressure (Fluent gauge offset) ──────────────────────────
        op_row = QHBoxLayout()
        op_row.setSpacing(6)
        op_row.addWidget(QLabel("Fluent operating pressure:"))
        self._op_pressure_field = QLineEdit("101325")
        self._op_pressure_field.setFixedWidth(90)
        self._op_pressure_field.setAlignment(Qt.AlignCenter)
        op_row.addWidget(self._op_pressure_field)
        op_row.addWidget(QLabel("Pa"))
        op_note = QLabel("(gauge offset — must match Fluent's Operating Conditions panel)")
        op_note.setStyleSheet(f"color: {_GRAY};")
        op_row.addWidget(op_note)
        op_row.addStretch()
        root.addLayout(op_row)

        # ── Action buttons ────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        btn_row.addWidget(QLabel("Color by:"))
        self._color_by_combo = QComboBox()
        self._color_by_combo.setMinimumWidth(140)
        self._color_by_combo.addItem(_COLOR_NONE)
        btn_row.addWidget(self._color_by_combo)

        btn_row.addStretch()

        preview_btn = QPushButton("Preview 3D")
        preview_btn.clicked.connect(self._do_preview_3d)
        btn_row.addWidget(preview_btn)

        export_btn = QPushButton("Export Fluent Profile (.prof)…")
        export_btn.clicked.connect(self._do_fluent_export)
        btn_row.addWidget(export_btn)

        root.addLayout(btn_row)
        root.addStretch()

    # ── Wall Export helpers ───────────────────────────────────────────────────

    def _on_revolve_toggled(self, enabled):
        for w in (self._revolve_start, self._revolve_end, self._revolve_n):
            w.setEnabled(enabled)

    def _select_all_props(self):
        for cb in self._export_checkboxes.values():
            cb.setChecked(True)

    def _deselect_all_props(self):
        for cb in self._export_checkboxes.values():
            cb.setChecked(False)

    def _update_export_checkboxes(self):
        """Rebuild Fluent-field checkboxes and color-by combo from loaded columns."""
        self._export_checkboxes.clear()
        while self._cb_grid.count():
            item = self._cb_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        fluent_cols  = [c for c in self._columns
                        if c not in _COORD_COLS and c in _FLUENT_FIELD_MAP]
        all_prop_cols = [c for c in self._columns if c not in _COORD_COLS]

        if not fluent_cols:
            lbl = QLabel("No Fluent-recognised properties found in this file.")
            lbl.setStyleSheet(f"color: {_GRAY};")
            self._cb_grid.addWidget(lbl, 0, 0)
        else:
            n_cols = 2
            for i, col in enumerate(fluent_cols):
                cb = QCheckBox(f"{col}  →  {_FLUENT_FIELD_MAP[col]}")
                cb.setChecked(True)
                self._export_checkboxes[col] = cb
                self._cb_grid.addWidget(cb, i // n_cols, i % n_cols)

        # Color-by combo shows ALL columns — used only for the 3-D preview
        self._color_by_combo.clear()
        self._color_by_combo.addItem(_COLOR_NONE)
        for col in all_prop_cols:
            self._color_by_combo.addItem(col)
        preferred = ['P_Pa', 'T_K', 'M', 'T_aw_K']
        for p in preferred:
            if p in all_prop_cols:
                self._color_by_combo.setCurrentText(p)
                break

    def _parse_revolve_params(self):
        """Parse and validate revolve fields.  Returns angles_rad array.
        Raises ValueError with a human-readable message on bad input."""
        revolve = self._revolve_cb.isChecked()
        start_deg = float(self._revolve_start.text().strip())
        end_deg   = float(self._revolve_end.text().strip())
        n_planes  = int(self._revolve_n.text().strip())
        if n_planes < 1:
            raise ValueError("Number of planes must be at least 1.")
        if end_deg <= start_deg:
            raise ValueError("End angle must be greater than start angle.")
        if revolve:
            full_circle = abs(end_deg - start_deg) >= 359.9
            return np.linspace(
                np.radians(start_deg),
                np.radians(end_deg),
                n_planes,
                endpoint=not full_circle,
            )
        return np.array([0.0])

    def _generate_wall_points(self, selected_cols):
        """Build flat X/Y/Z arrays and property arrays for all planes.

        Returns a dict with keys: X, Y, Z, props (dict col->array),
        n_pts, n_planes.
        Raises ValueError on bad input or missing data.
        """
        if not self._data:
            raise ValueError("No data loaded.")
        if 'x_m' not in self._data or 'r_m' not in self._data:
            raise ValueError(
                "The loaded file must contain 'x_m' and 'r_m' columns."
            )
        angles_rad = self._parse_revolve_params()
        x_arr = self._data['x_m']
        r_arr = self._data['r_m']
        n_pts = len(x_arr)
        n_planes = len(angles_rad)
        total = n_pts * n_planes

        X = np.empty(total)
        Y = np.empty(total)
        Z = np.empty(total)
        props = {col: np.empty(total) for col in selected_cols}

        idx = 0
        for theta in angles_rad:
            cos_t = np.cos(theta)
            sin_t = np.sin(theta)
            sl = slice(idx, idx + n_pts)
            X[sl] = x_arr
            Y[sl] = r_arr * cos_t
            Z[sl] = r_arr * sin_t
            for col in selected_cols:
                props[col][sl] = self._data[col]
            idx += n_pts

        return {
            'X': X, 'Y': Y, 'Z': Z,
            'props': props,
            'n_pts': n_pts,
            'n_planes': n_planes,
        }

    def _do_preview_3d(self):
        if not self._data:
            QMessageBox.warning(self, "No data",
                                "Load a results CSV file first.")
            return

        selected_cols = [col for col, cb in self._export_checkboxes.items()
                         if cb.isChecked()]
        color_col = self._color_by_combo.currentText()
        if color_col == _COLOR_NONE:
            color_col = None
        # Ensure color column is included in the generated data
        cols_needed = list(selected_cols)
        if color_col and color_col not in cols_needed:
            cols_needed.append(color_col)

        try:
            pts = self._generate_wall_points(cols_needed)
        except ValueError as exc:
            QMessageBox.critical(self, "Preview Error", str(exc))
            return

        color_data  = pts['props'][color_col] if color_col else None
        color_label = color_col or ''

        dlg = _Preview3DDialog(
            pts['X'], pts['Y'], pts['Z'],
            color_data, color_label,
            pts['n_pts'], pts['n_planes'],
            parent=self,
        )
        dlg.show()

    def _do_fluent_export(self):
        if not self._data:
            QMessageBox.warning(self, "No data",
                                "Load a results CSV file first.")
            return

        selected = {col: _FLUENT_FIELD_MAP[col]
                    for col, cb in self._export_checkboxes.items()
                    if cb.isChecked()}

        if not selected:
            QMessageBox.warning(self, "Nothing selected",
                                "Select at least one Fluent field to export.")
            return

        # T_K and T_aw_K both map to 'temperature' — keep T_aw_K
        temp_cols = [c for c, fn in selected.items() if fn == 'temperature']
        if len(temp_cols) > 1:
            for c in temp_cols:
                if c != 'T_aw_K':
                    del selected[c]
            QMessageBox.information(
                self, "Temperature field resolved",
                "T_K and T_aw_K both map to Fluent's 'temperature'.\n"
                "Only T_aw_K (adiabatic wall temperature) will be exported.",
            )

        try:
            op_pressure = float(self._op_pressure_field.text().strip())
        except ValueError:
            op_pressure = 101325.0

        try:
            pts = self._generate_wall_points(list(selected.keys()))
        except ValueError as exc:
            QMessageBox.critical(self, "Export error", str(exc))
            return

        os.makedirs(self.RESULTS_DIR, exist_ok=True)
        default_path = os.path.join(self.RESULTS_DIR, 'nozzle-wall.prof')
        out_path, _ = QFileDialog.getSaveFileName(
            self, "Save Fluent Profile as…", default_path,
            "Fluent Profile (*.prof);;All files (*.*)",
        )
        if not out_path:
            return

        n_total = pts['n_pts'] * pts['n_planes']
        profile_name = (os.path.splitext(os.path.basename(out_path))[0]
                        .replace(' ', '-'))

        def _write_field(fh, name, arr):
            fh.write(f"({name}\n")
            for v in arr:
                fh.write(f"{v:.8g}\n")
            fh.write(')\n')

        try:
            with open(out_path, 'w', encoding='utf-8') as fh:
                fh.write(f"(({profile_name} point {n_total})\n")
                _write_field(fh, 'x', pts['X'])
                _write_field(fh, 'y', pts['Y'])
                _write_field(fh, 'z', pts['Z'])
                for col, fluent_name in selected.items():
                    arr = pts['props'][col].copy()
                    if fluent_name == 'pressure':
                        arr -= op_pressure
                    _write_field(fh, fluent_name, arr)
                fh.write(')\n')
        except Exception as exc:
            QMessageBox.critical(self, "Export error", str(exc))
            return

        exported = ', '.join(dict.fromkeys(selected.values()))
        QMessageBox.information(
            self, "Export complete",
            f"Fluent profile written:  {n_total:,} points\n"
            f"Profile name:  '{profile_name}'\n"
            f"Fields:  x, y, z, {exported}\n\n"
            f"In Fluent:  Boundary Conditions → select wall boundary\n"
            f"            → Thermal tab → Temperature → Profile\n"
            f"            → choose  '{profile_name}'\n\n"
            f"{out_path}",
        )

    # ── File management ───────────────────────────────────────────────────────

    def refresh_file_list(self):
        """Public API — called by SimulationTab after a successful run."""
        self._refresh_file_list()

    def _refresh_file_list(self):
        os.makedirs(self.RESULTS_DIR, exist_ok=True)
        all_files = sorted(
            f for f in os.listdir(self.RESULTS_DIR) if f.endswith('.csv')
        )
        self._csv_files = [os.path.join(self.RESULTS_DIR, f) for f in all_files]

        current = self._file_combo.currentText()
        self._file_combo.blockSignals(True)
        self._file_combo.clear()
        self._file_combo.addItems(all_files)
        if current in all_files:
            self._file_combo.setCurrentIndex(all_files.index(current))
        self._file_combo.blockSignals(False)

    def _load_from_path(self, filepath):
        """Load a CSV directly by path — used internally and by tests."""
        try:
            data, columns = _read_csv(filepath)
        except Exception as exc:
            QMessageBox.critical(self, "Load Error",
                                 f"Could not load:\n{filepath}\n\n{exc}")
            return
        self._data    = data
        self._columns = columns
        n_rows = len(next(iter(data.values()))) if data else 0
        self._status_label.setText(
            f"Loaded:  {os.path.basename(filepath)}  "
            f"({n_rows} rows,  {len(columns)} columns)"
        )
        self._status_label.setStyleSheet("color: #a6e3a1;")
        self._update_axis_combos()
        self._populate_table()
        self._update_export_checkboxes()

    def _load_selected(self):
        idx = self._file_combo.currentIndex()
        if idx < 0 or not self._csv_files:
            QMessageBox.warning(self, "No file selected",
                                "Select a CSV file from the dropdown first.")
            return
        self._load_from_path(self._csv_files[idx])

    # ── Axis combos ───────────────────────────────────────────────────────────

    def _update_axis_combos(self):
        cols = self._columns
        for combo in (self._x_combo, self._y_combo):
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(cols)
            combo.blockSignals(False)
        if not cols:
            return
        self._x_combo.setCurrentIndex(0)
        default_y = cols.index('M') if 'M' in cols else (1 if len(cols) > 1 else 0)
        self._y_combo.setCurrentIndex(default_y)

    # ── Plot ──────────────────────────────────────────────────────────────────

    def _draw_placeholder(self):
        ax = self._ax
        ax.clear()
        ax.set_facecolor(_AX_BG)
        _style_axes(ax)
        ax.text(0.5, 0.5, 'Load a CSV file and click "Plot"',
                transform=ax.transAxes, ha='center', va='center',
                fontsize=max(constants.BASE_FONT - 1, 9),
                color=_GRAY, style='italic')
        ax.set_xticks([])
        ax.set_yticks([])
        self._fig.tight_layout(pad=2.0)
        self._canvas.draw_idle()

    def _do_plot(self):
        if not self._data:
            QMessageBox.warning(self, "No data", "Load a CSV file first.")
            return
        x_col = self._x_combo.currentText()
        y_col = self._y_combo.currentText()
        if not x_col or not y_col:
            QMessageBox.warning(self, "No axes selected",
                                "Select both X and Y axes.")
            return

        ax = self._ax
        ax.clear()
        ax.set_facecolor(_AX_BG)
        _style_axes(ax)
        ax.plot(self._data[x_col], self._data[y_col],
                color=_BLUE, linewidth=1.8)
        ax.set_xlabel(x_col, color=_FG)
        ax.set_ylabel(y_col, color=_FG)
        ax.set_title(f"{y_col}  vs  {x_col}", color=_FG)
        ax.grid(True, color=_GRID, alpha=0.5)
        self._fig.tight_layout(pad=2.0)
        self._canvas.draw_idle()

    def _clear_plot(self):
        self._draw_placeholder()

    # ── Results table ─────────────────────────────────────────────────────────

    def _populate_table(self):
        model = _CsvTableModel(self._data, self._columns)
        self._table_view.setModel(model)
        self._table_view.resizeColumnsToContents()
        n_rows = model.rowCount()
        n_cols = model.columnCount()
        self._row_count_label.setText(
            f"{n_rows} rows  ×  {n_cols} columns"
        )

    # ── Utilities ─────────────────────────────────────────────────────────────

    def _open_folder(self):
        os.makedirs(self.RESULTS_DIR, exist_ok=True)
        try:
            if sys.platform == 'win32':
                os.startfile(self.RESULTS_DIR)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', self.RESULTS_DIR])
            else:
                subprocess.Popen(['xdg-open', self.RESULTS_DIR])
        except Exception as exc:
            QMessageBox.information(
                self, "Open Folder",
                f"Could not open folder automatically.\n\n"
                f"Path:\n{self.RESULTS_DIR}\n\n{exc}",
            )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _read_csv(filepath):
    """Read a CSV that may have comment lines starting with '#'."""
    rows, headers = [], None
    with open(filepath, 'r', encoding='utf-8') as fh:
        for row in csv.reader(fh):
            if not row or row[0].strip().startswith('#'):
                continue
            if headers is None:
                headers = [h.strip() for h in row]
            else:
                rows.append(row)
    if not headers:
        raise ValueError("No header row found in the CSV file.")
    data = {}
    for i, col in enumerate(headers):
        vals = []
        for row in rows:
            cell = row[i].strip() if i < len(row) else ''
            try:
                vals.append(float(cell) if cell else float('nan'))
            except ValueError:
                vals.append(float('nan'))
        data[col] = np.array(vals, dtype=float)
    return data, headers


def _style_axes(ax):
    ax.tick_params(colors=_FG)
    ax.spines[:].set_color(_GRID)
    for lbl in ax.get_xticklabels() + ax.get_yticklabels():
        lbl.set_color(_FG)
