"""
tabs/simulation_tab_qt.py - Simulation tab: solver settings, run control, convergence monitor.

The simulation runs as a child subprocess (python main.py <temp_params.json>).
A QThread reads stdout line-by-line and emits signals; the main thread receives
them and updates the console + convergence plot without any polling timers.
"""

import os
import sys
import json
import copy
import re
import math
import tempfile
import subprocess

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QLineEdit, QComboBox,
    QGroupBox, QPlainTextEdit, QSplitter, QProgressBar,
    QSizePolicy, QMessageBox,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QTextCursor

from backend.app.core.param_loader import find_param_files, load_params, PARAMS_DIR
import constants

_REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Dark palette colours (match app_qt.py QSS)
_BG    = "#1e1e2e"
_AX_BG = "#181825"
_FG    = "#cdd6f4"
_GRID  = "#313244"
_GRAY  = "#6c7086"

# Per-variable residual colours
_CONV_STYLES = {
    'N': ('#89b4fa', 'M²  (R_N)'),
    'P': ('#f38ba8', 'Pressure  (R_P)'),
    'T': ('#fab387', 'Temperature  (R_T)'),
    'F': ('#a6e3a1', 'Friction  (R_F)'),
}

_CONV_RE = re.compile(
    r'\[Iteration\s+(\d+)\]'
    r'\s+R_N=([\d.]+(?:[eE][+\-]?\d+)?)'
    r'\s+R_P=([\d.]+(?:[eE][+\-]?\d+)?)'
    r'\s+R_T=([\d.]+(?:[eE][+\-]?\d+)?)'
    r'(?:\s+R_F=([\d.]+(?:[eE][+\-]?\d+)?))?'
)


# ── Background worker ─────────────────────────────────────────────────────────

class _SimWorker(QThread):
    """Runs the simulation subprocess and emits each stdout line as a signal."""
    line_received = Signal(str)
    finished      = Signal(int)   # returncode

    def __init__(self, cmd, cwd, env):
        super().__init__()
        self._cmd  = cmd
        self._cwd  = cwd
        self._env  = env
        self._proc = None

    def run(self):
        self._proc = subprocess.Popen(
            self._cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            bufsize=1,
            cwd=self._cwd,
            env=self._env,
        )
        for line in self._proc.stdout:
            self.line_received.emit(line)
        self._proc.wait()
        self.finished.emit(self._proc.returncode)

    def terminate_process(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()


# ── Tab ───────────────────────────────────────────────────────────────────────

class SimulationTab(QWidget):
    """Configure solver settings, run the simulation, watch live output."""

    def __init__(self, parent=None, app=None):
        super().__init__(parent)
        self._app             = app
        self._worker          = None
        self._tmp_path        = None
        self._stopped_by_user = False
        self._fields: dict[str, QLineEdit] = {}

        # Convergence plot state
        self._conv_iters    = []
        self._conv_data     = {'N': [], 'P': [], 'T': [], 'F': []}
        self._conv_tol      = 1e-6
        self._conv_lines    = {}
        self._conv_tol_line = None
        self._conv_text     = None

        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(6)

        root.addWidget(self._make_solver_settings())
        root.addLayout(self._make_run_controls())
        root.addWidget(self._make_lower_panel(), stretch=1)

    def _make_solver_settings(self):
        box = QGroupBox("Solver Settings")
        grid = QGridLayout(box)
        grid.setContentsMargins(14, 8, 14, 8)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        grid.setColumnMinimumWidth(0, 260)

        settings = [
            ('n_grid',         'Grid points  (mesh size)',  '-',   '100'),
            ('max_iterations', 'Max / fixed iterations',    '-',   '100'),
            ('tol',            'Convergence tolerance',     '-',   '1e-6'),
            ('relax',          'Under-relaxation factor',   '0–1', '0.3'),
        ]

        self._tol_entry = None
        for row, (key, label, unit, default) in enumerate(settings):
            grid.addWidget(QLabel(label), row, 0, Qt.AlignLeft)
            entry = QLineEdit(default)
            entry.setFixedWidth(130)
            grid.addWidget(entry, row, 1)
            unit_lbl = QLabel(unit)
            unit_lbl.setStyleSheet(f"color: {_GRAY};")
            grid.addWidget(unit_lbl, row, 2, Qt.AlignLeft)
            self._fields[key] = entry
            if key == 'tol':
                self._tol_entry = entry

        # Solver mode row
        mode_row = len(settings)
        grid.addWidget(QLabel("Solver mode:"), mode_row, 0, Qt.AlignLeft)
        self._mode_combo = QComboBox()
        self._mode_combo.addItems(['Convergence-based', 'Fixed iterations'])
        self._mode_combo.setFixedWidth(200)
        self._mode_combo.currentTextChanged.connect(self._on_mode_change)
        grid.addWidget(self._mode_combo, mode_row, 1)
        hint = QLabel("Fixed: runs exactly N iters;  Convergence: stops early when residual < tol")
        hint.setStyleSheet(f"color: {_GRAY};")
        grid.addWidget(hint, mode_row, 2, 1, 2, Qt.AlignLeft)

        grid.setColumnStretch(3, 1)
        return box

    def _on_mode_change(self, text):
        if self._tol_entry:
            self._tol_entry.setEnabled(text != 'Fixed iterations')

    def _make_run_controls(self):
        bar = QHBoxLayout()
        bar.setSpacing(8)

        self._run_btn = QPushButton("Run Simulation")
        self._run_btn.clicked.connect(self._run)
        bar.addWidget(self._run_btn)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._stop)
        bar.addWidget(self._stop_btn)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)   # indeterminate
        self._progress.setFixedWidth(260)
        self._progress.setVisible(False)
        bar.addWidget(self._progress)

        self._status_label = QLabel("Idle")
        self._status_label.setStyleSheet(f"color: {_GRAY};")
        bar.addWidget(self._status_label)
        bar.addStretch()
        return bar

    def _make_lower_panel(self):
        splitter = QSplitter(Qt.Horizontal)

        # Left: console
        console_box = QGroupBox("Console Output")
        console_layout = QVBoxLayout(console_box)
        console_layout.setContentsMargins(4, 4, 4, 4)
        console_layout.setSpacing(4)

        self._console = QPlainTextEdit()
        self._console.setReadOnly(True)
        mono = QFont("Consolas", max(constants.BASE_FONT - 2, 9))
        self._console.setFont(mono)
        self._console.setMaximumBlockCount(5000)
        console_layout.addWidget(self._console)

        clear_btn = QPushButton("Clear Console")
        clear_btn.clicked.connect(self._console.clear)
        btn_bar = QHBoxLayout()
        btn_bar.addStretch()
        btn_bar.addWidget(clear_btn)
        console_layout.addLayout(btn_bar)

        splitter.addWidget(console_box)

        # Right: convergence plot
        conv_box = QGroupBox("Convergence Monitor")
        conv_layout = QVBoxLayout(conv_box)
        conv_layout.setContentsMargins(4, 4, 4, 4)

        self._conv_fig = Figure(figsize=(5, 4), facecolor=_BG)
        self._conv_ax  = self._conv_fig.add_subplot(111)
        self._conv_ax.set_facecolor(_AX_BG)
        self._conv_canvas = FigureCanvasQTAgg(self._conv_fig)
        self._conv_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        conv_layout.addWidget(self._conv_canvas)
        self._init_conv_plot()

        splitter.addWidget(conv_box)
        splitter.setSizes([550, 400])
        return splitter

    # ── Convergence plot ──────────────────────────────────────────────────────

    def _init_conv_plot(self):
        ax = self._conv_ax
        ax.clear()
        ax.set_facecolor(_AX_BG)
        ax.set_yscale('log')
        ax.set_xlabel('Iteration', color=_FG)
        ax.set_ylabel('L1 residual', color=_FG)
        ax.set_title('Convergence Monitor', color=_FG)
        ax.tick_params(colors=_FG)
        ax.spines[:].set_color(_GRID)
        ax.grid(True, which='both', color=_GRID, alpha=0.5)

        self._conv_text = ax.text(
            0.5, 0.5, 'Waiting for simulation…',
            transform=ax.transAxes,
            ha='center', va='center',
            fontsize=max(constants.BASE_FONT - 1, 9),
            color=_GRAY, style='italic',
        )
        self._conv_lines    = {}
        self._conv_tol_line = None
        self._conv_fig.tight_layout(pad=2.0)
        self._conv_canvas.draw_idle()

    def _reset_conv_plot(self):
        self._conv_iters = []
        self._conv_data  = {'N': [], 'P': [], 'T': [], 'F': []}
        self._init_conv_plot()

    def _parse_conv_line(self, line):
        m = _CONV_RE.search(line)
        if not m:
            return
        self._conv_iters.append(int(m.group(1)))
        self._conv_data['N'].append(float(m.group(2)))
        self._conv_data['P'].append(float(m.group(3)))
        self._conv_data['T'].append(float(m.group(4)))
        rf = float(m.group(5)) if m.group(5) is not None else float('nan')
        self._conv_data['F'].append(rf)
        self._update_conv_plot()

    def _update_conv_plot(self):
        ax    = self._conv_ax
        iters = self._conv_iters
        if not iters:
            return

        if self._conv_text is not None:
            self._conv_text.remove()
            self._conv_text = None

        need_legend = False
        for key, (color, label) in _CONV_STYLES.items():
            vals  = self._conv_data[key]
            valid = [(i, v) for i, v in zip(iters, vals) if not math.isnan(v)]
            if not valid:
                continue
            vi, vv = zip(*valid)
            if key not in self._conv_lines:
                line, = ax.plot(vi, vv, '-', color=color, linewidth=1.8, label=label)
                self._conv_lines[key] = line
                need_legend = True
            else:
                self._conv_lines[key].set_xdata(vi)
                self._conv_lines[key].set_ydata(vv)

        if self._conv_tol_line is None:
            self._conv_tol_line = ax.axhline(
                self._conv_tol, color=_FG, linestyle='--', linewidth=1.0,
                label=f'Tolerance  {self._conv_tol:.1e}',
            )
            need_legend = True

        if need_legend:
            ax.legend(
                fontsize=max(constants.BASE_FONT - 4, 8),
                loc='upper right',
                facecolor=_BG, edgecolor=_GRID, labelcolor=_FG,
            )

        ax.relim()
        ax.autoscale_view()
        self._conv_canvas.draw_idle()

    # ── Console ───────────────────────────────────────────────────────────────

    def _log(self, text: str):
        self._console.moveCursor(QTextCursor.End)
        self._console.insertPlainText(text)
        self._console.moveCursor(QTextCursor.End)

    # ── Parameter assembly ────────────────────────────────────────────────────

    def _build_temp_json(self):
        params_tab = self._app.params_tab if self._app else None

        if params_tab is not None and params_tab._raw_data is not None:
            raw = copy.deepcopy(params_tab._raw_data)
        else:
            files = find_param_files()
            if not files:
                raise RuntimeError(
                    "No parameter files found in params/.\n"
                    "Load a config in the Parameters tab first.")
            _, raw = load_params(files[0])
            raw = copy.deepcopy(raw)

        # Apply Parameters-tab edits
        if params_tab is not None:
            flat_params = params_tab.get_params()
            for section in raw.values():
                if not isinstance(section, dict):
                    continue
                for pk, pd in section.items():
                    if isinstance(pd, dict) and 'value' in pd and pk in flat_params:
                        old = pd['value']
                        new = flat_params[pk]
                        pd['value'] = int(new) if isinstance(old, int) and new == int(new) else new

        # Apply Simulation-tab solver overrides
        for key, entry in self._fields.items():
            s = entry.text().strip()
            if not s:
                continue
            try:
                val = float(s)
            except ValueError:
                continue
            for section in raw.values():
                if not isinstance(section, dict):
                    continue
                for pk, pd in section.items():
                    if pk == key and isinstance(pd, dict) and 'value' in pd:
                        old = pd['value']
                        pd['value'] = int(val) if isinstance(old, int) and val == int(val) else val

        # Inject solver mode
        mode_internal = (
            'fixed' if self._mode_combo.currentText() == 'Fixed iterations'
            else 'convergence'
        )
        raw['_solver_mode_override'] = {
            'solver_mode': {'value': mode_internal, 'unit': '', 'description': 'Solver mode'},
        }

        tmp = tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False,
            encoding='utf-8', dir=PARAMS_DIR, prefix='_run_',
        )
        json.dump(raw, tmp, ensure_ascii=False, indent=4)
        tmp.close()
        return tmp.name

    # ── Run / Stop ────────────────────────────────────────────────────────────

    def _run(self):
        try:
            tmp_path = self._build_temp_json()
        except Exception as exc:
            QMessageBox.critical(self, "Parameter Error", str(exc))
            return

        self._tmp_path        = tmp_path
        self._stopped_by_user = False

        try:
            self._conv_tol = float(self._fields['tol'].text().strip())
        except ValueError:
            self._conv_tol = 1e-6
        self._reset_conv_plot()

        self._console.clear()
        self._log("=" * 64 + "\n")
        self._log("  OpenEngine Simulation\n")
        self._log(f"  Config: {os.path.basename(tmp_path)}\n")
        self._log("=" * 64 + "\n\n")

        self._run_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._progress.setVisible(True)
        self._status_label.setText("Running…")
        self._status_label.setStyleSheet("color: #89b4fa;")

        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'

        self._worker = _SimWorker(
            cmd=[sys.executable, '-u',
                 os.path.join(_REPO_DIR, 'main.py'), tmp_path],
            cwd=_REPO_DIR,
            env=env,
        )
        self._worker.line_received.connect(self._on_line)
        self._worker.finished.connect(self._on_done)
        self._worker.start()

    def _stop(self):
        self._stopped_by_user = True
        if self._worker:
            self._worker.terminate_process()

    def _on_line(self, line: str):
        self._log(line)
        self._parse_conv_line(line)

    def _on_done(self, returncode: int):
        self._run_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._progress.setVisible(False)

        if self._stopped_by_user:
            self._status_label.setText("Stopped")
            self._status_label.setStyleSheet(f"color: {_GRAY};")
            self._log("\n[Stopped by user]\n")
        elif returncode == 0:
            self._status_label.setText("Done")
            self._status_label.setStyleSheet("color: #a6e3a1;")
            self._log("\n" + "=" * 64 + "\n")
            self._log("  Simulation completed successfully.\n")
            self._log("  Plot windows may still be open — close them when done.\n")
            self._log("=" * 64 + "\n")
            if self._app and hasattr(self._app, 'results_tab'):
                self._app.results_tab.refresh_file_list()
        else:
            self._status_label.setText(f"Error ({returncode})")
            self._status_label.setStyleSheet("color: #f38ba8;")
            self._log(f"\n[Process exited with code {returncode}]\n")

        self._cleanup_tmp()
        self._worker = None

    def _cleanup_tmp(self):
        if self._tmp_path and os.path.exists(self._tmp_path):
            try:
                os.remove(self._tmp_path)
            except OSError:
                pass
        self._tmp_path = None

    # ── Public API ────────────────────────────────────────────────────────────

    def terminate(self):
        """Called by the app on shutdown to kill any running subprocess."""
        if self._worker:
            self._worker.terminate_process()
        self._cleanup_tmp()
