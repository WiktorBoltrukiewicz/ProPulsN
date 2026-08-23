"""Phase 0: N0 is shot for, not hand-tuned.

The exact isentropic value is a lower bound the discretised solver cannot
quite realise — see core/inlet_condition.py for why. These tests pin the two
properties the shooting relies on (a real threshold, and monotonicity of the
sonic point in N0) and check the result is usable for every geometry the
Geometry section can produce.
"""

import os
import sys
import unittest

import numpy as np
from scipy.interpolate import PchipInterpolator

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.core.geometry import build_nozzle_geometry  # noqa: E402
from backend.app.core.inlet_condition import (  # noqa: E402
    DEFAULT_MARGIN,
    _reaches_sonic,
    critical_inlet_N0,
    solve_inlet_N0,
)
from backend.app.core.isentropic import inlet_N0_from_geometry  # noqa: E402

GAMMA = 1.1869
P0, T0 = 6.0e6, 2941.58


def _setup(**kw):
    """Build the pieces the shooting needs, exactly as core/main.py does."""
    x, r, A, dA, A_interp, dA_interp = build_nozzle_geometry(**kw)
    ode_params = {
        'A_func': A_interp,
        'dA_func': dA_interp,
        'gamma_interp': PchipInterpolator(x, np.full_like(x, GAMMA)),
    }
    seed = inlet_N0_from_geometry(float(A[0]), float(A.min()), GAMMA)
    return x, A, ode_params, (x[0], x[-1]), seed


# The geometries the sweep in this change covered; all must produce a usable N0.
GEOMETRIES = {
    'default': {},
    'small throat': dict(R_param=0.012),
    'large throat': dict(R_param=0.025),
    'narrow chamber': dict(R_chamber=0.035),
    'wide chamber': dict(R_chamber=0.070),
    'long chamber': dict(L_chamber=0.25),
    'short chamber': dict(L_chamber=0.09),
    'tight chamber': dict(R_param=0.012, R_chamber=0.030,
                          R_conv_arc=0.045, L_chamber=0.09),
}


class TestChokingThreshold(unittest.TestCase):

    def test_isentropic_value_is_a_lower_bound(self):
        """The premise of the whole approach: discretisation only ever raises it."""
        for label, kw in GEOMETRIES.items():
            with self.subTest(label):
                _, _, params, span, seed = _setup(**kw)
                critical, _ = critical_inlet_N0(params, span, P0, T0, seed)
                self.assertGreaterEqual(critical, seed)
                # ...and not by much, or the seed would be a poor bracket.
                self.assertLess(critical / seed, 1.15)

    def test_threshold_is_sharp(self):
        """Just below it the nozzle never chokes; just above it always does."""
        for label, kw in GEOMETRIES.items():
            with self.subTest(label):
                _, _, params, span, seed = _setup(**kw)
                critical, _ = critical_inlet_N0(params, span, P0, T0, seed)
                self.assertFalse(_reaches_sonic(critical * 0.99, params, span, P0, T0)[0])
                self.assertTrue(_reaches_sonic(critical * 1.01, params, span, P0, T0)[0])

    def test_sonic_point_moves_upstream_with_N0(self):
        """Monotonicity is what makes the bisection well posed."""
        _, A, params, span, seed = _setup()
        critical, _ = critical_inlet_N0(params, span, P0, T0, seed)
        positions = []
        for factor in (1.005, 1.02, 1.05, 1.10):
            ok, x_sonic = _reaches_sonic(critical * factor, params, span, P0, T0)
            self.assertTrue(ok)
            positions.append(x_sonic)
        self.assertEqual(positions, sorted(positions, reverse=True))

    def test_rejects_a_nonsensical_seed(self):
        _, _, params, span, _ = _setup()
        for bad in (0.0, -1.0, 1.0, 5.0):
            with self.subTest(seed=bad), self.assertRaises(ValueError):
                critical_inlet_N0(params, span, P0, T0, bad)


class TestSolveInletN0(unittest.TestCase):

    def test_every_geometry_gets_a_choking_N0(self):
        for label, kw in GEOMETRIES.items():
            with self.subTest(label):
                _, _, params, span, seed = _setup(**kw)
                info = solve_inlet_N0(params, span, P0, T0, seed)
                self.assertTrue(_reaches_sonic(info['N0'], params, span, P0, T0)[0])
                self.assertGreater(info['N0'], info['N0_critical'] - 1e-12)
                self.assertEqual(info['N0_isentropic'], seed)

    def test_sonic_point_lands_near_the_throat(self):
        """A few mm upstream is expected; anything more means a bad N0."""
        for label, kw in GEOMETRIES.items():
            with self.subTest(label):
                x, A, params, span, seed = _setup(**kw)
                info = solve_inlet_N0(params, span, P0, T0, seed)
                self.assertIsNotNone(info['x_sonic'])
                x_throat = float(x[int(np.argmin(A))])
                offset = info['x_sonic'] - x_throat
                length = float(x[-1] - x[0])
                self.assertLess(offset, 0.0)              # always upstream
                self.assertGreater(offset, -0.05 * length)

    def test_larger_margin_moves_the_sonic_point_upstream(self):
        _, _, params, span, seed = _setup()
        tight = solve_inlet_N0(params, span, P0, T0, seed, margin=0.005)
        loose = solve_inlet_N0(params, span, P0, T0, seed, margin=0.05)
        self.assertLess(tight['N0'], loose['N0'])
        self.assertGreater(tight['x_sonic'], loose['x_sonic'])

    def test_zero_margin_sits_on_the_threshold(self):
        _, _, params, span, seed = _setup()
        info = solve_inlet_N0(params, span, P0, T0, seed, margin=0.0)
        self.assertAlmostEqual(info['N0'], info['N0_critical'], places=12)

    def test_negative_margin_is_rejected(self):
        _, _, params, span, seed = _setup()
        with self.assertRaises(ValueError):
            solve_inlet_N0(params, span, P0, T0, seed, margin=-0.1)

    def test_default_engine_beats_the_old_hand_tuned_constant(self):
        """The value Phase 0 replaces: 0.01535, ~4 mm off the throat."""
        x, A, params, span, seed = _setup()
        info = solve_inlet_N0(params, span, P0, T0, seed)
        x_throat = float(x[int(np.argmin(A))])
        _, x_old = _reaches_sonic(0.01535, params, span, P0, T0)
        self.assertLess(abs(info['x_sonic'] - x_throat), abs(x_old - x_throat))
        self.assertEqual(DEFAULT_MARGIN, 0.02)


if __name__ == '__main__':
    unittest.main()
