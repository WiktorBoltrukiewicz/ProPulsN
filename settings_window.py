"""
settings_window_qt.py - Application settings dialog (Qt).

Layout:
  Left  (fixed width) : QTreeWidget category list
  Right (expanding)   : QStackedWidget that swaps panel on selection
"""

import os

from PySide6.QtWidgets import (
    QDialog, QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QPushButton, QLabel, QLineEdit, QCheckBox,
    QSlider, QGroupBox, QGridLayout,
    QTreeWidget, QTreeWidgetItem, QStackedWidget,
    QFrame, QMessageBox, QApplication,
    QSizePolicy,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

import constants

_REPO_DIR = os.path.dirname(os.path.abspath(__file__))
_GRAY = "#6c7086"


class SettingsWindow(QDialog):
    """Application settings dialog — modal, single instance."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self._app = app
        self.setWindowTitle("Settings")
        self.setMinimumSize(780, 500)
        self.resize(1000, 600)
        self.setModal(True)

        self._panels = {}   # tree item id -> QWidget panel
        self._build_ui()
        self._default_select()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 0)
        root.setSpacing(0)

        # Main splitter: tree left, content right
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        root.addWidget(splitter, stretch=1)

        # Left tree
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setFixedWidth(190)
        self._tree.setStyleSheet("QTreeWidget { border: none; }")
        self._tree.currentItemChanged.connect(self._on_tree_select)
        splitter.addWidget(self._tree)

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color: #45475a;")
        splitter.addWidget(sep)

        # Right stacked widget
        self._stack = QStackedWidget()
        splitter.addWidget(self._stack)
        splitter.setSizes([190, 1, 780])

        self._populate_tree()

        # Bottom bar
        sep_h = QFrame()
        sep_h.setFrameShape(QFrame.HLine)
        sep_h.setStyleSheet("color: #45475a;")
        root.addWidget(sep_h)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(6, 4, 6, 6)
        bottom.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(90)
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(close_btn)
        root.addLayout(bottom)

    def _populate_tree(self):
        exp_item = QTreeWidgetItem(self._tree, ["Export"])
        exp_item.setExpanded(True)

        res_item  = QTreeWidgetItem(exp_item, ["Results"])
        geo_item  = QTreeWidgetItem(exp_item, ["Geometry"])
        vis_item  = QTreeWidgetItem(self._tree, ["Visual"])

        self._panels[id(res_item)]  = self._make_results_panel()
        self._panels[id(geo_item)]  = self._make_geometry_panel()
        self._panels[id(vis_item)]  = self._make_visual_panel()

        for panel in self._panels.values():
            self._stack.addWidget(panel)

        self._geo_item = geo_item
        self._vis_item = vis_item

    def _on_tree_select(self, current, _previous):
        if current is None:
            return
        key = id(current)
        if key in self._panels:
            self._stack.setCurrentWidget(self._panels[key])
        else:
            # Parent node selected — jump to first child
            if current.childCount():
                self._tree.setCurrentItem(current.child(0))

    def _default_select(self):
        self._tree.setCurrentItem(self._geo_item)

    # ── Panel: Export > Results ───────────────────────────────────────────────

    def _make_results_panel(self):
        f = QWidget()
        layout = QVBoxLayout(f)
        layout.setContentsMargins(12, 12, 12, 12)

        title = QLabel("Export  →  Results")
        font = title.font()
        font.setBold(True)
        font.setPointSize(constants.BASE_FONT + 1)
        title.setFont(font)
        layout.addWidget(title)

        note = QLabel("Results export settings will be configured in a future update.")
        note.setStyleSheet(f"color: {_GRAY};")
        layout.addWidget(note)
        layout.addStretch()
        return f

    # ── Panel: Export > Geometry ──────────────────────────────────────────────

    def _make_geometry_panel(self):
        s     = self._app.settings
        outer = QWidget()
        layout = QVBoxLayout(outer)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel("Export  →  Geometry (DXF)")
        font = title.font()
        font.setBold(True)
        font.setPointSize(constants.BASE_FONT + 1)
        title.setFont(font)
        layout.addWidget(title)

        # Profile options
        pf = QGroupBox("Profile Options")
        pf_grid = QGridLayout(pf)
        pf_grid.setContentsMargins(14, 8, 14, 10)
        pf_grid.setHorizontalSpacing(10)
        pf_grid.setVerticalSpacing(6)

        pf_grid.addWidget(QLabel("Grid points  (n_grid):"), 0, 0, Qt.AlignLeft)
        self._dxf_n_grid = QLineEdit(str(s.get('dxf_n_grid', 500)))
        self._dxf_n_grid.setFixedWidth(90)
        pf_grid.addWidget(self._dxf_n_grid, 0, 1)
        hint = QLabel("more = smoother profile in CAD")
        hint.setStyleSheet(f"color: {_GRAY};")
        pf_grid.addWidget(hint, 0, 2, Qt.AlignLeft)

        self._dxf_mirror = QCheckBox("Include lower profile (mirror  −r)")
        self._dxf_mirror.setChecked(s.get('dxf_mirror', True))
        pf_grid.addWidget(self._dxf_mirror, 1, 0, 1, 3)

        self._dxf_spline = QCheckBox(
            "Use SPLINE curve instead of LWPOLYLINE  "
            "(smoother, but slower import in some CAD tools)"
        )
        self._dxf_spline.setChecked(s.get('dxf_spline', False))
        pf_grid.addWidget(self._dxf_spline, 2, 0, 1, 3)

        self._dxf_labels = QCheckBox("Include dimension labels  (DIMENSIONS layer)")
        self._dxf_labels.setChecked(s.get('dxf_labels', True))
        pf_grid.addWidget(self._dxf_labels, 3, 0, 1, 3)

        pf_grid.setColumnStretch(2, 1)
        layout.addWidget(pf)

# DXF layers info
        lf = QGroupBox("DXF Layers  (informational)")
        lf_grid = QGridLayout(lf)
        lf_grid.setContentsMargins(14, 8, 14, 10)
        lf_grid.setHorizontalSpacing(12)
        lf_grid.setVerticalSpacing(4)

        bold_font = QFont()
        bold_font.setBold(True)
        for c, h in enumerate(["Layer", "Style", "Contents"]):
            lbl = QLabel(h)
            lbl.setFont(bold_font)
            lf_grid.addWidget(lbl, 0, c, Qt.AlignLeft)

        layer_rows = [
            ("UPPER_PROFILE", "White,  0.50 mm", "Upper nozzle contour  +r"),
            ("LOWER_PROFILE", "Cyan,   0.35 mm", "Lower contour  −r  (when mirror is ON)"),
            ("SYMMETRY_AXIS", "Red,    CENTER",   "Axis of symmetry"),
            ("POINTS",        "Yellow, 0.18 mm",  "Key section markers  (throat / inlet / exit)"),
            ("DIMENSIONS",    "Green,  0.18 mm",  "Text labels  (when labels are ON)"),
        ]
        mono_font = QFont("Consolas", constants.BASE_FONT - 1)
        for r, (name, style, desc) in enumerate(layer_rows, 1):
            name_lbl = QLabel(name)
            name_lbl.setFont(mono_font)
            lf_grid.addWidget(name_lbl, r, 0, Qt.AlignLeft)
            style_lbl = QLabel(style)
            style_lbl.setStyleSheet(f"color: {_GRAY};")
            lf_grid.addWidget(style_lbl, r, 1, Qt.AlignLeft)
            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet(f"color: {_GRAY};")
            lf_grid.addWidget(desc_lbl, r, 2, Qt.AlignLeft)
        lf_grid.setColumnStretch(2, 1)
        layout.addWidget(lf)

        apply_btn = QPushButton("Apply")
        apply_btn.setFixedWidth(90)
        apply_btn.clicked.connect(self._apply_geometry)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(apply_btn)
        layout.addLayout(btn_row)
        layout.addStretch()
        return outer

    def _apply_geometry(self):
        try:
            n = int(self._dxf_n_grid.text().strip())
            if n < 10:
                raise ValueError("must be at least 10")
        except ValueError as exc:
            QMessageBox.critical(self, "Invalid value",
                                 f"Grid points: {exc}")
            return
        s = self._app.settings
        s['dxf_n_grid']  = n
        s['dxf_mirror']  = self._dxf_mirror.isChecked()
        s['dxf_spline']  = self._dxf_spline.isChecked()
        s['dxf_labels']  = self._dxf_labels.isChecked()
        self._app.save_settings()

    # ── Panel: Visual ─────────────────────────────────────────────────────────

    def _make_visual_panel(self):
        s     = self._app.settings
        outer = QWidget()
        layout = QVBoxLayout(outer)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel("Visual")
        font = title.font()
        font.setBold(True)
        font.setPointSize(constants.BASE_FONT + 1)
        title.setFont(font)
        layout.addWidget(title)

        ff = QGroupBox("Font Size / Interface Scale")
        ff_grid = QGridLayout(ff)
        ff_grid.setContentsMargins(14, 10, 14, 12)
        ff_grid.setHorizontalSpacing(10)
        ff_grid.setVerticalSpacing(8)

        ff_grid.addWidget(
            QLabel("Interface scale  (BASE_FONT):"), 0, 0, Qt.AlignLeft
        )

        self._font_slider = QSlider(Qt.Horizontal)
        self._font_slider.setRange(8, 24)
        self._font_slider.setValue(s.get('base_font', constants.BASE_FONT))
        self._font_slider.setFixedWidth(280)
        ff_grid.addWidget(self._font_slider, 0, 1)

        self._font_spin = QLineEdit(str(s.get('base_font', constants.BASE_FONT)))
        self._font_spin.setFixedWidth(46)
        self._font_spin.setAlignment(Qt.AlignCenter)
        ff_grid.addWidget(self._font_spin, 0, 2)

        pt_label = QLabel("pt")
        pt_label.setStyleSheet(f"color: {_GRAY};")
        ff_grid.addWidget(pt_label, 0, 3, Qt.AlignLeft)

        # Keep slider and text box in sync
        self._font_slider.valueChanged.connect(
            lambda v: self._font_spin.setText(str(v))
        )
        self._font_spin.textChanged.connect(self._on_font_text_changed)

        note = QLabel(
            "Range: 8 – 24 pt.  Change takes effect after clicking Apply.\n"
            "Most elements update immediately; a few may require a restart."
        )
        note.setStyleSheet(f"color: {_GRAY};")
        note.setWordWrap(True)
        ff_grid.addWidget(note, 1, 0, 1, 4)
        ff_grid.setColumnStretch(1, 1)

        layout.addWidget(ff)

        apply_btn = QPushButton("Apply")
        apply_btn.setFixedWidth(90)
        apply_btn.clicked.connect(self._apply_visual)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(apply_btn)
        layout.addLayout(btn_row)
        layout.addStretch()
        return outer

    def _on_font_text_changed(self, text):
        """Keep slider in sync when the user types a value directly."""
        try:
            v = int(text.strip())
            if 8 <= v <= 24:
                self._font_slider.setValue(v)
        except ValueError:
            pass

    def _apply_visual(self):
        try:
            val = int(self._font_spin.text().strip())
            if not (8 <= val <= 24):
                raise ValueError("out of range")
        except ValueError:
            QMessageBox.critical(self, "Invalid value",
                                 "Font size must be a whole number between 8 and 24.")
            return
        old_base = constants.BASE_FONT
        constants.BASE_FONT = val
        self._app.settings['base_font'] = val
        self._app._apply_fonts(old_base=old_base)
        self._app.save_settings()
