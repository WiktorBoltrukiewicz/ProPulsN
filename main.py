"""
main.py — CLI entry point for the rocket engine nozzle simulation.

The solver itself lives in backend/app/core/. This shim keeps the standalone
CLI working and is also what the web backend spawns as a subprocess.

Usage:
  python main.py                        — interactive mode (select parameter file)
  python main.py params/default.json    — load a specific file
  python main.py --default              — run with built-in default parameters
"""

import sys

from backend.app.core.main import main

if __name__ == '__main__':
    main(param_file=sys.argv[1] if len(sys.argv) > 1 else None)
