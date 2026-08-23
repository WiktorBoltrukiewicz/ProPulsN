"""
ui.py - OpenEngine entry point.

Run this file to start the application:
    python ui.py

The application is split across several modules:
    app.py                   - main window and lifecycle (OpenEngineApp)
    tabs/geometry_tab.py     - Geometry tab
    tabs/parameters_tab.py   - Parameters tab
    tabs/simulation_tab.py   - Simulation tab
    tabs/results_tab.py      - Results tab
    settings_window.py       - Settings dialog
    constants.py             - shared UI constants (BASE_FONT, defaults)
"""

from app import OpenEngineApp

if __name__ == '__main__':
    app = OpenEngineApp()
    app.run()
