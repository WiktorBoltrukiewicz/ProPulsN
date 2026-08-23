"""
constants.py - Shared UI constants for OpenEngine.

All modules import this module and read constants.BASE_FONT so that
when the user changes the font size in Settings, every module sees
the updated value immediately (Python module attributes are shared).
"""

# Font size that controls the scale of the entire interface.
# Raise it for larger screens / high-DPI displays.
#   8-10  : small
#   12-14 : comfortable
#   16    : large (default)
#   18-24 : very large
BASE_FONT = 8

# Default nozzle geometry (loaded from default.json on first run)
DEFAULT_R_THROAT = 0.01878  # m
DEFAULT_E_R      = 5.0
DEFAULT_N_GRID   = 100
