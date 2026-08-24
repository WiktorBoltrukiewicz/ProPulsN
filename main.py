"""
main.py — CLI entry point for the rocket engine nozzle simulation.

The solver itself lives in backend/app/core/. This shim keeps the standalone
CLI working and is also what the web backend spawns as a subprocess.

Usage:
  python main.py                        — interactive mode (select parameter file)
  python main.py params/default.json    — load a specific file

There are no built-in parameter values. Every number the solver uses comes
from the parameter file, so an incomplete file is refused before anything is
computed. See backend/app/core/param_schema.REQUIRED_PARAMS.
"""

import sys

from backend.app.core.main import main
from backend.app.core.param_schema import MissingParameters

if __name__ == '__main__':
    try:
        main(param_file=sys.argv[1] if len(sys.argv) > 1 else None)
    except MissingParameters as exc:
        # A missing parameter is a fact about the file, not a crash. The web
        # app streams this stdout straight into its console, so it has to read
        # as an instruction rather than a traceback.
        print()
        print("Cannot run: " + str(exc))
        sys.exit(2)
