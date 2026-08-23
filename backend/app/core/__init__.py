"""Solver core, relocated from the repo root. Behavior is unchanged."""

import os

# backend/app/core/paths.py -> core -> app -> backend -> repo root
REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

PARAMS_DIR = os.path.join(REPO_ROOT, 'params')
RESULTS_DIR = os.path.join(REPO_ROOT, 'results')
