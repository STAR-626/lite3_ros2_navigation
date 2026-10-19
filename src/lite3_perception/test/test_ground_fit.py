"""Flat ground must not turn into obstacles; low objects must survive fitting."""
import sys
from pathlib import Path
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from flat_ground_fit import fit_ground_plane, height_above_plane
from pointcloud_obstacles import classify


class GroundFit(unittest.TestCase):
    def floor(self, a=.006,b=-.004,c=.015):
        x,y=np.meshgrid(np.linspace(-4,4,60),np.linspace(-4,4,60))
        return np.column_stack([x.ravel(),y.ravel(),a*x.ravel()+b*y.ravel()+c])

    def test_misprojected_ground_not_obstacle(self):
        p=self.floor();plane=fit_ground_plane(p,[0,0,.5]);self.assertIsNotNone(plane)
        self.assertTrue(np.allclose(plane,[.006,-.004,.015],atol=1e-6))
        self.assertLess(np.max(np.abs(height_above_plane(p,plane)-.005)),1e-6)

    def test_low_and_overhead_objects_not_fitted_away(self):
        floor=self.floor();obj=np.array([[1,0,.08+.021],[1,1,.5+.017]])
        p=np.vstack([floor,obj]);plane=fit_ground_plane(p,[0,0,.5]);h=height_above_plane(p,plane)
        body=p.copy();body[:,0]+=10
        obs,clear,g=classify(p-[0,0,.5],p,body,.005,.02,.65,np.array([-.38,-.28,-.5]),np.array([.38,.28,.18]),.12,12,h)
        self.assertEqual(int(obs.sum()),2);self.assertTrue(g[:-2].all());self.assertFalse(g[-2:].any())

    def test_small_flat_box_not_accepted_as_floor(self):
        p=self.floor();p=p[(np.abs(p[:,0])<.5)&(np.abs(p[:,1])<.5)];p[:,2]=.08
        self.assertIsNone(fit_ground_plane(p,[0,0,.5]))

    def test_excessive_tilt_or_height_rejected(self):
        self.assertIsNone(fit_ground_plane(self.floor(a=.1),[0,0,.5]))
        self.assertIsNone(fit_ground_plane(self.floor(c=.12),[0,0,.5]))

    def test_outliers_and_nonfinite(self):
        floor=self.floor();rng=np.random.default_rng(2);bad=rng.uniform([-4,-4,-.1],[4,4,.17],(800,3))
        p=np.vstack([floor,bad,[[np.nan,0,0]]]);plane=fit_ground_plane(p,[0,0,.5]);self.assertIsNotNone(plane)
        self.assertTrue(np.allclose(plane,[.006,-.004,.015],atol=.002))

    def test_no_evidence(self):
        self.assertIsNone(fit_ground_plane(np.empty((0,3)),[0,0,.5]))


if __name__=='__main__':unittest.main()
