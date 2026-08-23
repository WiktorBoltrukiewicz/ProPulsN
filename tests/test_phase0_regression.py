"""Phase 0 end-to-end: engines that used to be unsolvable now solve.

Before Phase 0 the chamber was hardcoded and N0 was a constant tuned for
R_throat = 0.01878, so R_throat = 0.020 died with `ValueError: Bad domain`.
These tests drive the real CLI, the same way a user or the web app does.

`max_iterations` is capped for speed. Do not shrink `n_grid` instead — a
coarse grid makes the solver fail near the sonic point for unrelated reasons.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PARAMS_DIR = os.path.join(ROOT, 'params')
DEFAULT_FILE = os.path.join(PARAMS_DIR, 'default.json')


def _run(overrides, max_iterations=3, initial=None):
    """Write a temp parameter file into params/ and solve it. Returns stdout."""
    with open(DEFAULT_FILE, encoding='utf-8') as fh:
        raw = json.load(fh)
    for key, value in overrides.items():
        raw['nozzle_geometry'][key]['value'] = value
    for key, value in (initial or {}).items():
        raw['initial_conditions'][key]['value'] = value
    raw['solver']['max_iterations']['value'] = max_iterations

    fd, path = tempfile.mkstemp(suffix='.json', prefix='_test_phase0_', dir=PARAMS_DIR)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            json.dump(raw, fh, ensure_ascii=False, indent=4)
        proc = subprocess.run(
            [sys.executable, 'main.py', os.path.relpath(path, ROOT)],
            cwd=ROOT, capture_output=True, text=True, timeout=300,
        )
        return proc.stdout + proc.stderr
    finally:
        os.unlink(path)
        stem = os.path.splitext(os.path.basename(path))[0]
        results = os.path.join(ROOT, 'results')
        for name in os.listdir(results) if os.path.isdir(results) else []:
            if name.startswith(stem):
                os.unlink(os.path.join(results, name))


class TestPreviouslyUnsolvableEngines(unittest.TestCase):

    def assertSolved(self, out):
        self.assertNotIn('Bad domain', out)
        self.assertNotIn('Sonic point not reached', out)
        self.assertIn('completed successfully', out)

    def test_default_engine_still_solves(self):
        self.assertSolved(_run({}))

    def test_throat_020_solves(self):
        """The exact case CLAUDE.md recorded as broken."""
        self.assertSolved(_run({'R_throat': 0.020}))

    def test_throat_020_still_fails_with_the_old_pinned_N0(self):
        """Confirms the fix is the derived N0, not something incidental."""
        out = _run({'R_throat': 0.020},
                   initial={'N0_auto': False, 'N0': 0.01535})
        self.assertNotIn('completed successfully', out)
        self.assertTrue('Bad domain' in out or 'Sonic point not reached' in out)

    def test_a_range_of_throats_solves(self):
        for R_throat in (0.010, 0.015, 0.022, 0.025):
            with self.subTest(R_throat=R_throat):
                self.assertSolved(_run({'R_throat': R_throat}))

    def test_a_range_of_chambers_solves(self):
        for R_chamber in (0.035, 0.050, 0.070):
            with self.subTest(R_chamber=R_chamber):
                self.assertSolved(_run({'R_chamber': R_chamber}))

    def test_chamber_length_does_not_break_the_solve(self):
        for L_chamber in (0.09, 0.25):
            with self.subTest(L_chamber=L_chamber):
                self.assertSolved(_run({'L_chamber': L_chamber}))

    def test_a_fully_different_engine_solves(self):
        self.assertSolved(_run({
            'R_throat': 0.012, 'R_chamber': 0.030,
            'R_conv_arc': 0.045, 'L_chamber': 0.09,
        }))


class TestUnbuildableGeometryIsRejectedClearly(unittest.TestCase):
    """A bad contour must fail at the geometry step, not deep in the solver."""

    def test_arc_too_large_for_the_chamber(self):
        out = _run({'R_throat': 0.030})
        self.assertIn('fold back', out)
        self.assertNotIn('Bad domain', out)

    def test_chamber_too_short(self):
        out = _run({'L_chamber': 0.01})
        self.assertIn('too short', out)
        self.assertNotIn('Bad domain', out)


if __name__ == '__main__':
    unittest.main()
