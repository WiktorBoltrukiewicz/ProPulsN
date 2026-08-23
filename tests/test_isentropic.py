"""Phase 0: N0 is derived from the area ratio, not hand-tuned per engine."""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.core.geometry import build_nozzle_geometry  # noqa: E402
from backend.app.core.isentropic import (  # noqa: E402
    area_ratio,
    inlet_N0_from_geometry,
    mach_from_area_ratio,
)

GAMMAS = (1.1869, 1.2, 1.3, 1.4, 1.66)


class TestAreaRatioRelation(unittest.TestCase):

    def test_minimum_at_sonic(self):
        for gamma in GAMMAS:
            with self.subTest(gamma=gamma):
                self.assertAlmostEqual(area_ratio(1.0, gamma), 1.0, places=12)
                self.assertGreater(area_ratio(0.5, gamma), 1.0)
                self.assertGreater(area_ratio(2.0, gamma), 1.0)

    def test_monotone_on_each_branch(self):
        for gamma in GAMMAS:
            with self.subTest(gamma=gamma):
                sub = [area_ratio(m, gamma) for m in np.linspace(0.05, 0.99, 40)]
                sup = [area_ratio(m, gamma) for m in np.linspace(1.01, 6.0, 40)]
                self.assertEqual(sub, sorted(sub, reverse=True))
                self.assertEqual(sup, sorted(sup))

    def test_known_value(self):
        """A/A* = 2 at M = 2.1972 for gamma = 1.4 (standard gas tables)."""
        self.assertAlmostEqual(area_ratio(2.1972, 1.4), 2.0, places=4)


class TestMachFromAreaRatio(unittest.TestCase):

    def test_round_trips_on_the_subsonic_branch(self):
        for gamma in GAMMAS:
            for M in (0.02, 0.1, 0.25, 0.5, 0.8, 0.95):
                with self.subTest(gamma=gamma, M=M):
                    recovered = mach_from_area_ratio(area_ratio(M, gamma), gamma)
                    self.assertAlmostEqual(recovered, M, places=9)

    def test_round_trips_on_the_supersonic_branch(self):
        for gamma in GAMMAS:
            for M in (1.2, 2.0, 3.5, 6.0):
                with self.subTest(gamma=gamma, M=M):
                    recovered = mach_from_area_ratio(
                        area_ratio(M, gamma), gamma, branch="supersonic")
                    self.assertAlmostEqual(recovered, M, places=9)

    def test_always_subsonic_by_default(self):
        for ratio in (1.0001, 1.5, 5.0, 50.0, 1000.0):
            with self.subTest(ratio=ratio):
                self.assertLess(mach_from_area_ratio(ratio, 1.1869), 1.0)

    def test_approaches_sonic_as_ratio_approaches_one(self):
        self.assertEqual(mach_from_area_ratio(1.0, 1.1869), 1.0)
        self.assertGreater(mach_from_area_ratio(1.000001, 1.1869), 0.99)

    def test_rejects_impossible_inputs(self):
        with self.assertRaises(ValueError):
            mach_from_area_ratio(0.5, 1.4)          # below the critical area
        with self.assertRaises(ValueError):
            mach_from_area_ratio(5.0, 1.0)          # gamma must exceed 1
        with self.assertRaises(ValueError):
            mach_from_area_ratio(float('nan'), 1.4)
        with self.assertRaises(ValueError):
            mach_from_area_ratio(5.0, 1.4, branch="transonic")


class TestInletN0FromGeometry(unittest.TestCase):

    def test_default_engine(self):
        """The default contour's own contraction ratio, on the solver grid."""
        _, r_grid, A_grid, *_ = build_nozzle_geometry()
        N0 = inlet_N0_from_geometry(float(A_grid[0]), float(A_grid.min()), 1.1869)
        self.assertAlmostEqual(N0, 0.014215, places=5)
        # The hand-tuned constant the parameter files used to pin.
        self.assertNotAlmostEqual(N0, 0.01535, places=4)

    def test_rises_as_the_nozzle_contracts_less(self):
        """The bug Phase 0 fixes: a bigger throat needs a faster inlet."""
        values = []
        for R_throat in (0.01878, 0.020, 0.025):
            _, _, A_grid, *_ = build_nozzle_geometry(R_param=R_throat)
            values.append(
                inlet_N0_from_geometry(float(A_grid[0]), float(A_grid.min()), 1.1869))
        self.assertEqual(values, sorted(values))
        # R_throat = 0.020 is the case that used to die with `Bad domain`.
        self.assertAlmostEqual(values[1], 0.018448, places=5)

    def test_rejects_a_diverging_inlet(self):
        with self.assertRaises(ValueError):
            inlet_N0_from_geometry(1.0e-4, 5.0e-4, 1.1869)
        with self.assertRaises(ValueError):
            inlet_N0_from_geometry(1.0e-4, 0.0, 1.1869)

    def test_matches_the_geometry_preview_service(self):
        """The Geometry section must show exactly what the solver will use."""
        from backend.app.services.geometry import preview_geometry
        stats = preview_geometry(0.01878, 5, 100)["stats"]
        _, _, A_grid, *_ = build_nozzle_geometry(R_param=0.01878, E_r=5, n_grid=100)
        expected = inlet_N0_from_geometry(
            float(A_grid[0]), float(A_grid.min()), 1.1869)
        self.assertAlmostEqual(stats["N0_isentropic"], expected, places=12)


if __name__ == '__main__':
    unittest.main()
