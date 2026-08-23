"""
tabs/geometry_tab_qt.py - Geometry tab: 2D nozzle profile viewer and DXF export.
"""

import os
import argparse

import numpy as np
import matplotlib
matplotlib.use("QtAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import (
    FigureCanvasQTAgg,
    NavigationToolbar2QT,
)
from matplotlib.figure import Figure

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QGroupBox, QGridLayout,
    QSizePolicy, QMessageBox, QFileDialog,
)
from PySide6.QtCore import Qt

from backend.app.core.geometry import build_nozzle_geometry
import constants

_REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Dark palette — kept in sync with app_qt.py QSS colours
_BG       = "#1e1e2e"   # widget / figure background
_AX_BG    = "#181825"   # axes face
_FG       = "#cdd6f4"   # default text / tick colour
_GRID     = "#313244"   # grid lines
_BLUE     = "#89b4fa"   # accent (nozzle wall, throat marker)
_RED      = "#f38ba8"   # throat marker
_GRAY     = "#6c7086"   # muted labels


class GeometryTab(QWidget):
    """Displays the 2-D nozzle cross-section and exposes DXF export."""

    def __init__(self, parent=None, app=None):
        super().__init__(parent)
        self._app = app
        self._stat_labels = {}   # key -> QLabel (value cell)
        self._build_ui()
        self._compute_and_plot()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(6)

        root.addLayout(self._make_control_bar())
        root.addWidget(self._make_stats_box())
        root.addWidget(self._make_canvas(), stretch=1)

    def _make_control_bar(self):
        bar = QHBoxLayout()
        bar.setSpacing(8)

        refresh_btn = QPushButton("Refresh Geometry")
        refresh_btn.clicked.connect(self._compute_and_plot)
        bar.addWidget(refresh_btn)

        export_btn = QPushButton("Export to .dxf")
        export_btn.clicked.connect(self._export_dxf)
        bar.addWidget(export_btn)

        note = QLabel(
            "Geometry is hardcoded (Rao bell nozzle).  "
            "Geometry builder coming in a future update."
        )
        note.setStyleSheet(f"color: {_GRAY};")
        bar.addWidget(note)
        bar.addStretch()

        return bar

    def _make_stats_box(self):
        box = QGroupBox("Geometry Summary")
        layout = QGridLayout(box)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setHorizontalSpacing(4)
        layout.setVerticalSpacing(2)

        stats = [
            "Total length",
            "Throat radius",
            "Exit radius",
            "Expansion ratio E_r",
            "Throat position",
        ]
        for col, key in enumerate(stats):
            lbl_key = QLabel(f"{key}:")
            lbl_key.setStyleSheet(f"color: {_GRAY};")
            layout.addWidget(lbl_key, 0, col * 2, Qt.AlignLeft)

            lbl_val = QLabel("—")
            lbl_val.setStyleSheet(
                f"color: {_FG}; font-family: 'Consolas', monospace; font-weight: bold;"
            )
            layout.addWidget(lbl_val, 0, col * 2 + 1, Qt.AlignLeft)
            self._stat_labels[key] = lbl_val

            if col < len(stats) - 1:
                spacer = QLabel()
                spacer.setFixedWidth(20)
                layout.addWidget(spacer, 0, col * 2 + 2)

        return box

    def _make_canvas(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._fig = Figure(figsize=(12, 5), facecolor=_BG)
        self._ax  = self._fig.add_subplot(111)
        self._ax.set_facecolor(_AX_BG)
        _style_axes(self._ax)

        self._canvas = FigureCanvasQTAgg(self._fig)
        self._canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        toolbar = NavigationToolbar2QT(self._canvas, container)
        toolbar.setStyleSheet(
            f"background-color: {_BG}; color: {_FG}; border: none;"
        )

        layout.addWidget(self._canvas)
        layout.addWidget(toolbar)
        return container

    # ── DXF export ────────────────────────────────────────────────────────────

    def _export_dxf(self):
        try:
            import ezdxf  # noqa: F401
        except ImportError:
            QMessageBox.critical(
                self,
                "Missing library",
                "ezdxf is not installed.\n\nInstall with:\n  pip install ezdxf",
            )
            return

        from backend.app.core.export_dxf import build_dxf, generate_output_filename

        s = self._app.settings if self._app else {}
        n_grid     = s.get('dxf_n_grid', 500)
        mirror     = s.get('dxf_mirror', True)
        spline     = s.get('dxf_spline', False)
        add_labels = s.get('dxf_labels', True)

        R_throat = constants.DEFAULT_R_THROAT
        E_r      = constants.DEFAULT_E_R
        if self._app and hasattr(self._app, 'params_tab'):
            p = self._app.params_tab.get_params()
            R_throat = p.get('R_throat', constants.DEFAULT_R_THROAT)
            E_r      = p.get('E_r',      constants.DEFAULT_E_R)

        # Build suggested filename so the dialog opens with a sensible default
        results_dir  = os.path.join(_REPO_DIR, 'results')
        os.makedirs(results_dir, exist_ok=True)
        default_path = generate_output_filename(R_throat, E_r, output_dir=results_dir)

        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save DXF as…",
            default_path,
            "DXF files (*.dxf);;All files (*.*)",
        )
        if not output_path:
            return   # user cancelled

        x_grid_arr, r_grid_arr, *_ = build_nozzle_geometry(
            R_param=R_throat, E_r=E_r, n_grid=n_grid
        )

        args = argparse.Namespace(spline=spline, no_mirror=not mirror)
        doc  = build_dxf(
            x_grid_arr, r_grid_arr, args,
            R_throat_mm=R_throat * 1000, E_r=E_r,
            add_labels=add_labels,
        )

        try:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            doc.saveas(output_path)
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", str(exc))
            return

        QMessageBox.information(self, "Export Complete", f"DXF saved to:\n{output_path}")

    # ── Plot ──────────────────────────────────────────────────────────────────

    def _compute_and_plot(self):
        x_grid, r_grid, *_ = build_nozzle_geometry(
            R_param=constants.DEFAULT_R_THROAT,
            E_r=constants.DEFAULT_E_R,
            n_grid=constants.DEFAULT_N_GRID,
        )

        idx_throat = int(np.argmin(r_grid))
        r_throat   = r_grid[idx_throat]
        x_throat   = x_grid[idx_throat]
        r_exit     = r_grid[-1]
        length     = x_grid[-1] - x_grid[0]
        E_r_actual = (r_exit / r_throat) ** 2

        self._stat_labels["Total length"].setText(f"{length * 1000:.2f} mm")
        self._stat_labels["Throat radius"].setText(f"{r_throat * 1000:.3f} mm")
        self._stat_labels["Exit radius"].setText(f"{r_exit * 1000:.3f} mm")
        self._stat_labels["Expansion ratio E_r"].setText(f"{E_r_actual:.3f}")
        self._stat_labels["Throat position"].setText(f"{x_throat * 1000:.2f} mm")

        x_mm = x_grid * 1000
        r_mm = r_grid * 1000

        ax = self._ax
        ax.clear()
        ax.set_facecolor(_AX_BG)
        _style_axes(ax)

        ax.fill_between(x_mm, r_mm, -r_mm, alpha=0.12, color=_BLUE)
        ax.plot(x_mm,  r_mm, color=_BLUE, linewidth=2.0, label='Nozzle wall')
        ax.plot(x_mm, -r_mm, color=_BLUE, linewidth=2.0)
        ax.axhline(0, color=_GRAY, linewidth=0.8, linestyle='--', label='Axis of symmetry')
        ax.axvline(
            x_mm[idx_throat], color=_RED, linewidth=1.0, linestyle=':',
            label=f'Throat  x = {x_mm[idx_throat]:.1f} mm,  r = {r_throat*1000:.2f} mm',
        )

        ax.set_xlabel('Axial position  x  [mm]', color=_FG)
        ax.set_ylabel('Radius  r  [mm]', color=_FG)
        ax.set_title('Nozzle Geometry — R(x)  (Rao bell nozzle)', color=_FG)
        ax.legend(loc='lower right', fontsize=constants.BASE_FONT - 2,
                  facecolor=_BG, edgecolor=_GRID, labelcolor=_FG)
        ax.grid(True, color=_GRID, alpha=0.6)
        ax.set_aspect('equal', adjustable='datalim')

        self._fig.tight_layout(pad=2.0)
        self._canvas.draw()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _style_axes(ax):
    """Apply dark theme colours to an axes object."""
    ax.tick_params(colors=_FG)
    ax.spines[:].set_color(_GRID)
    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_color(_FG)
