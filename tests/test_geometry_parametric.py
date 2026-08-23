"""Phase 0: the nozzle contour is parametric all the way up to the chamber.

Two things are guarded here:

1. Calling ``build_nozzle_geometry`` with no chamber arguments must reproduce
   the original hardcoded contour bit-for-bit, so every result produced before
   the chamber became parametric stays reproducible.
2. The chamber arguments must actually reshape the convergent section, and the
   large arc must stay tangent to the chamber wall.
"""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.core.geometry import (  # noqa: E402
    build_nozzle_geometry,
    R_CHAMBER_DEFAULT,
    L_CHAMBER_DEFAULT,
    R_CONV_ARC_DEFAULT,
)


def _legacy_contour(R_param=0.01878, E_r=5, n_grid=100):
    """The pre-Phase-0 implementation, constants and all, kept as the oracle."""
    X1 = 1.5 * R_param * np.cos(np.radians(-120))
    Y1 = 1.5 * R_param * np.sin(np.radians(-120)) + 2.5 * R_param
    m = X1 / np.sqrt((1.5 * R_param) ** 2 - X1 ** 2)
    Y3 = -0.0306 + 0.07265 / np.sqrt(1 + m ** 2)
    X3 = X1 + (Y3 - Y1) / m
    Xc = X3 - (-m * 0.07265) / np.sqrt(1 + m ** 2)

    X2 = 0.382 * R_param * np.cos(np.radians(-68))
    Y2 = 0.382 * R_param * np.sin(np.radians(-68)) + 1.382 * R_param
    Nx, Ny = X2, Y2
    m1, m2 = np.tan(np.radians(22)), np.tan(np.radians(12))
    c1 = Ny - m1 * Nx
    Ey = np.sqrt(E_r) * R_param
    Ex = 0.8 * (((np.sqrt(E_r) - 1) * R_param) / np.tan(np.radians(15)))
    c2 = Ey - m2 * Ex
    Qx = (c2 - c1) / (m1 - m2)
    Qy = (m1 * c2 - m2 * c1) / (m1 - m2)

    n = 500
    x1 = np.linspace(-0.14262, Xc, n)
    y1 = 0.04205 * np.ones(n)
    x2 = np.linspace(Xc, X3, n)
    y2 = -0.0306 + np.sqrt(0.07265 ** 2 - (x2 - Xc) ** 2)
    x3 = np.linspace(X3, X1, n)
    y3 = m * (x3 - X1) + Y1
    x4 = np.linspace(X1, 0, n)
    y4 = -np.sqrt((1.5 * R_param) ** 2 - x4 ** 2) + 2.5 * R_param
    x5 = np.linspace(0, X2, n)
    y5 = -np.sqrt((0.382 * R_param) ** 2 - x5 ** 2) + 1.382 * R_param
    t = np.linspace(0, 1, n)
    x6 = (1 - t) ** 2 * Nx + 2 * (1 - t) * t * Qx + t ** 2 * Ex
    y6 = (1 - t) ** 2 * Ny + 2 * (1 - t) * t * Qy + t ** 2 * Ey

    X_raw = np.concatenate([x1, x2[1:], x3[1:], x4[1:], x5[1:], x6[1:]])
    Y_raw = np.concatenate([y1, y2[1:], y3[1:], y4[1:], y5[1:], y6[1:]])
    X_raw = X_raw - X_raw[0]

    S = np.zeros(len(X_raw))
    S[1:] = np.cumsum(np.sqrt(np.diff(X_raw) ** 2 + np.diff(Y_raw) ** 2))
    S_n = np.linspace(0, S[-1], n_grid)
    x_grid = np.interp(S_n, S, X_raw)
    r_grid = np.interp(S_n, S, Y_raw)
    A_grid = np.pi * r_grid ** 2
    dA = 2 * np.pi * r_grid * np.gradient(r_grid, x_grid)
    return x_grid, r_grid, A_grid, dA


class TestDefaultContourUnchanged(unittest.TestCase):
    """The whole point of Phase 0: parametrise without moving the default."""

    def test_matches_legacy_across_grids(self):
        for n_grid in (50, 100, 250, 500):
            with self.subTest(n_grid=n_grid):
                x_o, r_o, A_o, dA_o = _legacy_contour(n_grid=n_grid)
                x_n, r_n, A_n, dA_n, _, _ = build_nozzle_geometry(n_grid=n_grid)
                np.testing.assert_allclose(x_n, x_o, rtol=0, atol=1e-12)
                np.testing.assert_allclose(r_n, r_o, rtol=0, atol=1e-12)
                np.testing.assert_allclose(A_n, A_o, rtol=0, atol=1e-12)
                np.testing.assert_allclose(dA_n, dA_o, rtol=0, atol=1e-9)

    def test_matches_legacy_for_other_throats(self):
        """Only the chamber was hardcoded — the rest must be untouched too."""
        for R, E in ((0.020, 5), (0.025, 8), (0.010, 3)):
            with self.subTest(R_throat=R, E_r=E):
                x_o, r_o, *_ = _legacy_contour(R_param=R, E_r=E)
                x_n, r_n, *_ = build_nozzle_geometry(R_param=R, E_r=E)
                np.testing.assert_allclose(x_n, x_o, rtol=0, atol=1e-12)
                np.testing.assert_allclose(r_n, r_o, rtol=0, atol=1e-12)

    def test_explicit_defaults_equal_implicit(self):
        implicit = build_nozzle_geometry()[1]
        explicit = build_nozzle_geometry(
            R_chamber=R_CHAMBER_DEFAULT,
            L_chamber=L_CHAMBER_DEFAULT,
            R_conv_arc=R_CONV_ARC_DEFAULT,
        )[1]
        np.testing.assert_array_equal(implicit, explicit)


class TestChamberIsParametric(unittest.TestCase):

    def test_chamber_radius_reaches_the_inlet(self):
        for R_chamber in (0.035, 0.04205, 0.055):
            with self.subTest(R_chamber=R_chamber):
                _, r_grid, *_ = build_nozzle_geometry(R_chamber=R_chamber)
                self.assertAlmostEqual(r_grid[0], R_chamber, places=12)
                self.assertAlmostEqual(max(r_grid[:10]), R_chamber, places=12)

    def test_contraction_ratio_follows_the_chamber(self):
        """The defect Phase 0 fixes: A_chamber used to be frozen at pi*0.04205^2."""
        ratios = []
        for R_chamber in (0.035, 0.04205, 0.055):
            _, r_grid, *_ = build_nozzle_geometry(R_chamber=R_chamber)
            ratios.append((r_grid[0] / r_grid.min()) ** 2)
        self.assertEqual(ratios, sorted(ratios))
        self.assertGreater(ratios[-1] - ratios[0], 1.0)

    def test_chamber_length_moves_the_inlet(self):
        short = build_nozzle_geometry(L_chamber=0.10)[0]
        long_ = build_nozzle_geometry(L_chamber=0.20)[0]
        # x is re-zeroed at the inlet, so a longer chamber means a longer nozzle.
        self.assertAlmostEqual(long_[-1] - short[-1], 0.10, places=9)

    def test_convergent_arc_is_tangent_to_the_chamber_wall(self):
        """The arc centre is derived, not free: y = R_chamber - R_conv_arc."""
        for R_chamber, R_conv_arc in ((0.04205, 0.07265), (0.035, 0.050)):
            with self.subTest(R_chamber=R_chamber, R_conv_arc=R_conv_arc):
                _, r_grid, *_ = build_nozzle_geometry(
                    R_chamber=R_chamber, R_conv_arc=R_conv_arc, n_grid=800,
                )
                # No step at the chamber/arc junction: the contour only ever
                # narrows through the convergent, smoothly.
                dr = np.diff(r_grid[: int(0.6 * len(r_grid))])
                self.assertLessEqual(dr.max(), 1e-9)
                self.assertLess(abs(dr).max(), 0.05 * R_chamber)

    def test_arc_radius_changes_the_convergent_shape(self):
        a = build_nozzle_geometry(R_conv_arc=0.07265)[1]
        b = build_nozzle_geometry(R_conv_arc=0.050)[1]
        self.assertGreater(np.abs(a - b).max(), 1e-4)


class TestGeometryValidation(unittest.TestCase):

    def test_chamber_narrower_than_throat_is_rejected(self):
        with self.assertRaises(ValueError):
            build_nozzle_geometry(R_param=0.02, R_chamber=0.015)

    def test_chamber_equal_to_throat_is_rejected(self):
        with self.assertRaises(ValueError):
            build_nozzle_geometry(R_param=0.02, R_chamber=0.02)

    def test_too_short_a_chamber_is_rejected(self):
        """The convergent arc would start upstream of the inlet."""
        with self.assertRaises(ValueError) as ctx:
            build_nozzle_geometry(L_chamber=0.01)
        self.assertIn("too short", str(ctx.exception))

    def test_arc_too_large_for_the_chamber_is_rejected(self):
        """A small chamber with the default arc folds the contour back on itself."""
        with self.assertRaises(ValueError) as ctx:
            build_nozzle_geometry(R_chamber=0.030, R_conv_arc=R_CONV_ARC_DEFAULT)
        self.assertIn("fold back", str(ctx.exception))
        # ...but it is fine once the arc is scaled down to suit.
        build_nozzle_geometry(R_chamber=0.030, R_conv_arc=0.045)

    def test_nonpositive_radii_are_rejected(self):
        with self.assertRaises(ValueError):
            build_nozzle_geometry(R_param=0)
        with self.assertRaises(ValueError):
            build_nozzle_geometry(R_conv_arc=0)
        with self.assertRaises(ValueError):
            build_nozzle_geometry(E_r=1)


if __name__ == '__main__':
    unittest.main()
