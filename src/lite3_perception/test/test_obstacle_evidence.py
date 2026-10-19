import sys
from pathlib import Path
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from obstacle_evidence import ObstacleEvidence


class Evidence(unittest.TestCase):
    def surface(self):
        return np.array([[1,y,z]for y in np.arange(0,.3,.04)for z in np.arange(.05,.6,.06)])

    def test_confirm_surface_and_reject_isolated(self):
        f=ObstacleEvidence();p=np.vstack([self.surface(),[[4,3.5,.05],[4.4,3.6,.4]]])
        self.assertFalse(f.filter(p,1.).any());m=f.filter(p,1.1)
        self.assertTrue(m[:-2].all());self.assertFalse(m[-2:].any())

    def test_moving_object_confirmed_without_trail(self):
        f=ObstacleEvidence();p=self.surface();f.filter(p,1.)
        self.assertTrue(f.filter(p+[0,.018,0],1.1).all())
        self.assertFalse(f.filter(np.empty((0,3)),1.2).any())
        self.assertFalse(f.filter(p,1.3).any())

    def test_time_jump_or_gap_resets_confirmation(self):
        f=ObstacleEvidence();p=self.surface();f.filter(p,1.)
        self.assertFalse(f.filter(p,2.).any());self.assertTrue(f.filter(p,2.1).all())
        self.assertFalse(f.filter(p,.5).any())

    def test_supported_low_box_remains(self):
        p=np.array([[1,y,.06]for y in np.arange(0,.2,.025)]);f=ObstacleEvidence()
        f.filter(p,1.);self.assertTrue(f.filter(p,1.1).all())


if __name__=='__main__':unittest.main()
