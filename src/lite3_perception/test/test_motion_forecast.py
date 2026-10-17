"""Forecast geometry and stale-history boundaries, without Gazebo or ROS graph."""
from pathlib import Path
import sys
import unittest
import numpy as np

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from motion_forecast import MotionForecast


def box(y=0):
    x, yy = np.meshgrid(np.arange(-.2, .21, .04), np.arange(-.2, .21, .04)+y)
    return np.column_stack([x.ravel(), yy.ravel(), np.full(x.size, .3)])


class ForecastTests(unittest.TestCase):
    def test_stationary_no_forecast(self):
        tracker = MotionForecast()
        for i in range(15):
            self.assertEqual(len(tracker.update(box(), i*.1)), 0)

    def test_consistent_motion_projects_forward(self):
        tracker = MotionForecast()
        for i in range(10):
            forecast = tracker.update(box(.18*i*.1), i*.1)
        self.assertEqual(len(tracker.moving), 1)
        self.assertAlmostEqual(tracker.moving[0]['velocity'][1], .18, delta=.04)
        self.assertGreater(forecast[:, 1].max(), .7)
        self.assertLess(forecast[:, 0].max(), .4)

    def test_new_cluster_not_instantly_moving(self):
        tracker = MotionForecast()
        self.assertEqual(len(tracker.update(box(), 0)), 0)
        self.assertEqual(len(tracker.update(box(.05), .1)), 0)

    def test_disappearance_and_clock_jump_reset(self):
        tracker = MotionForecast()
        for i in range(10):
            tracker.update(box(.18*i*.1), i*.1)
        self.assertEqual(len(tracker.update(np.empty((0, 3)), 1.)), 0)
        self.assertEqual(len(tracker.update(box(), 1.1)), 0)
        self.assertEqual(len(tracker.update(box(.1), .1)), 0)
        self.assertEqual(len(tracker.update(box(.2), 2.)), 0)

    def test_large_wall_not_forecast(self):
        tracker = MotionForecast()
        p = np.column_stack([np.arange(-2, 2, .03), np.zeros(134)[:len(np.arange(-2, 2, .03))],
                             np.ones(134)[:len(np.arange(-2, 2, .03))]*.4])
        for i in range(10):
            self.assertEqual(len(tracker.update(p + [0, .18*i*.1, 0], i*.1)), 0)

    def test_changing_visible_surface_is_not_translation(self):
        tracker = MotionForecast()
        for i in range(10):
            points = box()
            # One edge fixed, opposite edge retreats with occlusion.
            points = points[points[:, 1] >= -.2 + .018*i]
            self.assertEqual(len(tracker.update(points, i*.1)), 0)


if __name__ == '__main__':
    unittest.main()
