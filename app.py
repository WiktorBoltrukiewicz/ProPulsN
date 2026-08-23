"""
app.py - OpenEngineApp (Qt): the main application window.

Creates the QApplication + QMainWindow, builds the menu and tab strip,
manages settings, and owns the top-level lifecycle.
"""

import os
import json

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget,
    QMenuBar, QMenu, QMessageBox, QDialog,
    QVBoxLayout, QLabel, QPushButton, QWidget,
)
from PySide6.QtGui import QAction, QIcon, QFont, QPixmap
from PySide6.QtCore import Qt

import constants
from tabs.geometry_tab   import GeometryTab
from tabs.parameters_tab import ParametersTab
from tabs.simulation_tab import SimulationTab
from tabs.results_tab    import ResultsTab
from settings_window     import SettingsWindow

_REPO_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Dark stylesheet — applied to the entire QApplication
# ---------------------------------------------------------------------------
_DARK_QSS = """
QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: "Segoe UI";
}

QMainWindow, QDialog {
    background-color: #1e1e2e;
}

/* ── Tab bar ── */
QTabWidget::pane {
    border: 1px solid #313244;
    background-color: #1e1e2e;
}
QTabBar::tab {
    background-color: #181825;
    color: #a6adc8;
    padding: 8px 20px;
    border: 1px solid #313244;
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}
QTabBar::tab:selected {
    background-color: #1e1e2e;
    color: #cdd6f4;
    border-bottom: 2px solid #89b4fa;
}
QTabBar::tab:hover:!selected {
    background-color: #252535;
    color: #cdd6f4;
}

/* ── Buttons ── */
QPushButton {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 5px 14px;
}
QPushButton:hover {
    background-color: #45475a;
}
QPushButton:pressed {
    background-color: #585b70;
}
QPushButton:disabled {
    color: #6c7086;
    background-color: #262637;
    border-color: #313244;
}

/* ── Inputs ── */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background-color: #181825;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 4px 8px;
    selection-background-color: #89b4fa;
    selection-color: #1e1e2e;
}
QLineEdit:focus, QComboBox:focus {
    border-color: #89b4fa;
}
QComboBox::drop-down {
    border: none;
    padding-right: 6px;
}
QComboBox QAbstractItemView {
    background-color: #181825;
    color: #cdd6f4;
    selection-background-color: #313244;
    border: 1px solid #45475a;
}

/* ── Labels ── */
QLabel#placeholderLabel {
    color: #6c7086;
    font-size: 14px;
}

/* ── Group boxes ── */
QGroupBox {
    border: 1px solid #45475a;
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 6px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
    color: #a6adc8;
}

/* ── Scroll bars ── */
QScrollBar:vertical {
    background: #181825;
    width: 10px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: #45475a;
    border-radius: 5px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover {
    background: #585b70;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background: #181825;
    height: 10px;
    border-radius: 5px;
}
QScrollBar::handle:horizontal {
    background: #45475a;
    border-radius: 5px;
    min-width: 20px;
}
QScrollBar::handle:horizontal:hover {
    background: #585b70;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ── Table / Tree views ── */
QTableView, QTreeView, QListView {
    background-color: #181825;
    alternate-background-color: #1e1e2e;
    color: #cdd6f4;
    gridline-color: #313244;
    border: 1px solid #45475a;
    border-radius: 4px;
}
QHeaderView::section {
    background-color: #313244;
    color: #a6adc8;
    border: none;
    border-right: 1px solid #45475a;
    padding: 4px 8px;
}
QTableView::item:selected, QTreeView::item:selected {
    background-color: #313244;
    color: #cdd6f4;
}

/* ── Menu bar ── */
QMenuBar {
    background-color: #181825;
    color: #cdd6f4;
    border-bottom: 1px solid #313244;
}
QMenuBar::item {
    padding: 4px 10px;
    background-color: transparent;
    border-radius: 3px;
}
QMenuBar::item:selected {
    background-color: #313244;
}
QMenu {
    background-color: #181825;
    color: #cdd6f4;
    border: 1px solid #45475a;
}
QMenu::item {
    padding: 5px 24px 5px 12px;
}
QMenu::item:selected {
    background-color: #313244;
    border-radius: 3px;
}

/* ── Separator ── */
QFrame[frameShape="4"], QFrame[frameShape="5"] {
    color: #45475a;
}

/* ── Splitter ── */
QSplitter::handle {
    background-color: #313244;
}

/* ── Status / plain text ── */
QPlainTextEdit, QTextEdit {
    background-color: #11111b;
    color: #a6e3a1;
    font-family: "Consolas", "Courier New", monospace;
    border: 1px solid #45475a;
    border-radius: 4px;
}

/* ── Check box / Radio ── */
QCheckBox, QRadioButton {
    color: #cdd6f4;
    spacing: 6px;
}
QCheckBox::indicator, QRadioButton::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #585b70;
    border-radius: 3px;
    background-color: #181825;
}
QCheckBox::indicator:checked {
    background-color: #89b4fa;
    border-color: #89b4fa;
}
QRadioButton::indicator {
    border-radius: 7px;
}
QRadioButton::indicator:checked {
    background-color: #89b4fa;
    border-color: #89b4fa;
}

/* ── Slider ── */
QSlider::groove:horizontal {
    background: #313244;
    height: 4px;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #89b4fa;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}
QSlider::sub-page:horizontal {
    background: #89b4fa;
    border-radius: 2px;
}

/* ── Progress bar ── */
QProgressBar {
    background-color: #313244;
    border: none;
    border-radius: 4px;
    text-align: center;
    color: #cdd6f4;
}
QProgressBar::chunk {
    background-color: #89b4fa;
    border-radius: 4px;
}

/* ── Tool tip ── */
QToolTip {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    padding: 4px;
}
"""


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About OpenEngine")
        self.setFixedSize(340, 180)
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        title = QLabel("OpenEngine")
        title.setAlignment(Qt.AlignCenter)
        f = title.font()
        f.setPointSize(constants.BASE_FONT + 2)
        f.setBold(True)
        title.setFont(f)

        sub = QLabel("Rocket nozzle flow simulation tool")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet("color: #6c7086;")

        stack = QLabel("Developed with Python · NumPy · SciPy · Matplotlib · PySide6")
        stack.setAlignment(Qt.AlignCenter)
        stack.setWordWrap(True)
        stack.setStyleSheet("color: #6c7086; font-size: 11px;")

        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(90)
        close_btn.clicked.connect(self.accept)

        close_wrap = QWidget()
        close_layout = QVBoxLayout(close_wrap)
        close_layout.setAlignment(Qt.AlignCenter)
        close_layout.addWidget(close_btn)

        layout.addWidget(title)
        layout.addWidget(sub)
        layout.addSpacing(10)
        layout.addWidget(stack)
        layout.addSpacing(10)
        layout.addWidget(close_wrap)


class OpenEngineApp:
    """Owns the QApplication and QMainWindow lifecycle."""

    _SETTINGS_FILE = os.path.join(_REPO_DIR, 'settings.json')

    def __init__(self):
        self._qt_app = QApplication.instance() or QApplication([])
        self._qt_app.setApplicationName("OpenEngine")

        # Default settings — overridden by _load_settings() if a file exists
        self.settings = {
            'dxf_n_grid':  500,
            'dxf_mirror':  True,
            'dxf_spline':  False,
            'dxf_labels':  True,
            'base_font':   constants.BASE_FONT,
        }
        self._load_settings()

        # Apply dark stylesheet globally
        self._qt_app.setStyleSheet(_DARK_QSS)
        self._apply_fonts()

        self._win = QMainWindow()
        self._win.setWindowTitle("OpenEngine")
        self._set_icon()
        self._build_menu()
        self._build_tabs()
        self._win.showMaximized()

    # ── Settings ──────────────────────────────────────────────────────────────

    def _load_settings(self):
        try:
            with open(self._SETTINGS_FILE, 'r', encoding='utf-8') as f:
                saved = json.load(f)
            self.settings.update(saved)
            constants.BASE_FONT = int(self.settings.get('base_font', constants.BASE_FONT))
        except (OSError, json.JSONDecodeError, ValueError):
            pass

    def save_settings(self):
        try:
            with open(self._SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=2)
        except OSError:
            pass

    def _apply_fonts(self, old_base: int = None):
        """Update fonts across every widget.

        *old_base* is the BASE_FONT value that was in effect when the widgets
        were last built.  Each widget's current point-size offset relative to
        that value is preserved, so titles (BASE_FONT+2), mono labels
        (BASE_FONT-1), etc., all scale proportionally.

        When called from __init__ (before any widgets exist) *old_base* is
        omitted — the application default is simply set for future widgets.
        """
        new_base = constants.BASE_FONT
        if old_base is None:
            old_base = new_base

        # Set default for widgets created in the future
        self._qt_app.setFont(QFont("Segoe UI", new_base))

        # Walk every existing widget and rescale its point size proportionally
        for w in self._qt_app.allWidgets():
            f = w.font()
            pt = f.pointSize()
            if pt <= 0:          # widget uses pixel size — leave it alone
                continue
            offset = pt - old_base
            new_pt = max(6, new_base + offset)
            if new_pt == pt:
                continue         # already correct
            new_f = QFont(f)
            new_f.setPointSize(new_pt)
            w.setFont(new_f)

    # ── Icon ──────────────────────────────────────────────────────────────────

    def _set_icon(self):
        icon_path = os.path.join(_REPO_DIR, 'icon.png')
        if os.path.isfile(icon_path):
            self._win.setWindowIcon(QIcon(icon_path))

    # ── Menu ──────────────────────────────────────────────────────────────────

    def _build_menu(self):
        mb = self._win.menuBar()

        file_menu = mb.addMenu("File")
        exit_act = QAction("Exit", self._win)
        exit_act.setShortcut("Alt+F4")
        exit_act.triggered.connect(self._win.close)
        file_menu.addAction(exit_act)

        settings_act = QAction("Settings", self._win)
        settings_act.triggered.connect(self._open_settings)
        mb.addAction(settings_act)

        help_menu = mb.addMenu("Help")
        about_act = QAction("About OpenEngine", self._win)
        about_act.triggered.connect(self._show_about)
        help_menu.addAction(about_act)

    def _open_settings(self):
        if (hasattr(self, '_settings_win')
                and self._settings_win is not None
                and self._settings_win.isVisible()):
            self._settings_win.raise_()
            self._settings_win.activateWindow()
            return
        self._settings_win = SettingsWindow(self._win, self)
        self._settings_win.show()

    def _show_about(self):
        dlg = AboutDialog(self._win)
        dlg.exec()

    # ── Tabs ──────────────────────────────────────────────────────────────────

    def _build_tabs(self):
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        self._win.setCentralWidget(tabs)

        self.geo_tab     = GeometryTab(tabs, app=self)
        self.params_tab  = ParametersTab(tabs)
        self.sim_tab     = SimulationTab(tabs, app=self)
        self.results_tab = ResultsTab(tabs)

        tabs.addTab(self.geo_tab,     "  Geometry  ")
        tabs.addTab(self.params_tab,  "  Parameters  ")
        tabs.addTab(self.sim_tab,     "  Simulation  ")
        tabs.addTab(self.results_tab, "  Results  ")

        self._tabs = tabs

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _on_close(self):
        """Clean shutdown: stop any running simulation before exiting."""
        if hasattr(self, 'sim_tab'):
            self.sim_tab.terminate()
        self._qt_app.quit()

    def run(self):
        self._win.closeEvent = lambda event: (self._on_close(), event.accept())
        self._win.show()
        self._qt_app.exec()
