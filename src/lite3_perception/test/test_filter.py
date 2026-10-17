"""几何语义检查：倾斜、地面、自身、低障碍、高处与最近距离投影。"""
import importlib.util
from pathlib import Path
import unittest
import sys

import numpy as np
from geometry_msgs.msg import Transform
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))

spec = importlib.util.spec_from_file_location(
    'pointcloud_obstacles', Path(__file__).parents[1] / 'scripts/pointcloud_obstacles.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Filtering(unittest.TestCase):
    def test_ground_and_low_obstacle(self):
        world = np.array([[1, 0, .005], [1, 0, .015], [1, 0, .08],
                          [1, 0, .65], [1, 0, .70], [0, 0, .35], [np.nan, 0, 0]])
        sensor = world - np.array([0, 0, .5])
        body = world - np.array([0, 0, .35])
        obstacles, clear, ground = module.classify(
            sensor, world, body, .005, .02, .65,
            np.array([-.38, -.28, -.5]), np.array([.38, .28, .18]), .12, 12)
        self.assertEqual(obstacles.tolist(), [False, False, True, True, False, False, False])
        self.assertEqual(ground.tolist(), [True, True, False, False, False, False, False])
        self.assertTrue(clear[0])  # 地面仍用于清除，不作为障碍。
        self.assertTrue(clear[4])  # 高处回波仍作为真实射线端点。
        self.assertFalse(clear[5])  # 自身不用于标记或清除。

    def test_tilt_transform(self):
        t = Transform()
        angle = np.deg2rad(20)
        t.rotation.y, t.rotation.w = np.sin(angle/2), np.cos(angle/2)
        t.translation.z = .5
        world = np.array([[2, 0, .005], [2, 0, .2]])
        rotation, translation = module.matrix(t)
        sensor = (world-translation) @ rotation
        self.assertTrue(np.allclose(module.apply(sensor, t), world))
        obstacles, _, floor = module.classify(
            sensor, module.apply(sensor, t), world, .005, .02, .65,
            np.array([-.38, -.28, -.5]), np.array([.38, .28, .18]), .12, 12)
        self.assertEqual(floor.tolist(), [True, False])
        self.assertEqual(obstacles.tolist(), [False, True])

    def test_projection(self):
        ranges = module.project(np.array([[2, 0, .1], [1, 0, .5],
                                          [0, 3, .3], [20, 0, .3]]), 720, .12, 12)
        self.assertAlmostEqual(float(ranges[360]), 1)
        self.assertAlmostEqual(float(ranges[540]), 3)
        self.assertTrue(np.isinf(ranges[0]))
        self.assertTrue(np.isinf(module.project(np.empty((0, 3)), 720, .12, 12)).all())


if __name__ == '__main__':
    unittest.main()
