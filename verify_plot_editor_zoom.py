"""Non-UI checks for worksheet zoom math (no Qt)."""

import unittest

from src.plot_editor.zoom import ZOOM_MAX, ZOOM_MIN, ZOOM_STEP, next_zoom


class NextZoomTests(unittest.TestCase):

    def test_identity_at_zero_steps(self):
        self.assertEqual(next_zoom(1.0, 0), 1.0)
        self.assertEqual(next_zoom(1.7, 0), 1.7)

    def test_step_up_and_down(self):
        self.assertAlmostEqual(next_zoom(1.0, 1), ZOOM_STEP)
        self.assertAlmostEqual(next_zoom(1.0, -1), 1.0 / ZOOM_STEP)

    def test_clamps_high(self):
        self.assertEqual(next_zoom(ZOOM_MAX, 1), ZOOM_MAX)
        self.assertEqual(next_zoom(2.9, 2), ZOOM_MAX)
        self.assertEqual(next_zoom(1.0, 100), ZOOM_MAX)

    def test_clamps_low(self):
        self.assertEqual(next_zoom(ZOOM_MIN, -1), ZOOM_MIN)
        self.assertEqual(next_zoom(0.6, -5), ZOOM_MIN)
        self.assertEqual(next_zoom(1.0, -100), ZOOM_MIN)

    def test_symmetric_in_out(self):
        z = 1.0
        for _ in range(3):
            z = next_zoom(z, 1)
        for _ in range(3):
            z = next_zoom(z, -1)
        self.assertAlmostEqual(z, 1.0)

    def test_fractional_steps(self):
        # High-resolution wheels deliver e.g. 0.25 steps per event.
        z = next_zoom(1.0, 0.25)
        self.assertAlmostEqual(z, ZOOM_STEP ** 0.25)
        z = next_zoom(z, -0.25)
        self.assertAlmostEqual(z, 1.0)


if __name__ == '__main__':
    unittest.main()
