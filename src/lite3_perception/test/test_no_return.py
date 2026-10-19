"""No-return semantics, invalid/occluded rays and URDF/config geometry parity."""
import sys,unittest,math,xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
import yaml
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from lidar_no_return import clearing_no_returns,rays_intersect_body

class NoReturn(unittest.TestCase):
    def setUp(self):
        self.w,self.h=9,5
        h,v=np.meshgrid(np.linspace(-math.pi,math.pi,self.w),np.linspace(-math.pi/3,math.pi/6,self.h))
        self.d=np.column_stack((np.cos(v).ravel()*np.cos(h).ravel(),np.cos(v).ravel()*np.sin(h).ravel(),np.sin(v).ravel()))
        self.raw=np.copysign(np.full(self.d.shape,np.inf),self.d)
        self.raw[np.abs(self.d)<1e-10]=np.nan
    def decode(self,raw,w=None,h=None):
        return clearing_no_returns(raw,self.w if w is None else w,self.h if h is None else h,self.w,self.h,-math.pi,math.pi,-math.pi/3,math.pi/6,12.)
    def test_valid_infinity_range(self):
        out=self.decode(self.raw)
        self.assertEqual(len(out),len(self.d));self.assertTrue(np.allclose(out/np.linalg.norm(out,axis=1)[:,None],self.d,atol=1e-6))
        self.assertTrue((np.linalg.norm(out,axis=1)<12.).all())
    def test_all_nan_is_not_free_space(self):
        self.assertEqual(len(self.decode(np.full(self.raw.shape,np.nan))),0)
    def test_finite_hits_are_not_extended(self):
        self.assertEqual(len(self.decode(self.d*.8)),0)
    def test_inverted_range_is_invalid(self):
        self.assertEqual(len(self.decode(-self.raw)),0)
    def test_shape_mismatch(self):
        self.assertEqual(len(self.decode(self.raw,w=self.w*self.h,h=1)),0)
        self.assertEqual(len(self.decode(self.raw[:-1])),0)
    def test_partial_invalid_is_not_invented(self):
        raw=self.raw.copy();raw[0]=np.nan;raw[1]=[1,np.inf,np.inf]
        self.assertEqual(len(self.decode(raw)),len(raw)-2)
    def test_self_occlusion(self):
        origin=np.array([.3,0.,.15]);ends=np.array([[12.,0.,.15],[-12.,0.,.15],[.3,0.,12.]])
        d=ends-origin;blind=origin+d*(.12/np.linalg.norm(d,axis=1))[:,None]
        blocked=rays_intersect_body(ends,blind,[-.38,-.28,-.5],[.38,.28,.18])
        self.assertEqual(blocked.tolist(),[False,True,False])
    def test_urdf_matches_configured_scan(self):
        root=Path(__file__).resolve().parents[3]
        config=yaml.safe_load((root/'src/lite3_perception/config/flat_ground.yaml').read_text())['lite3_pointcloud_obstacles']['ros__parameters']
        urdf=ET.parse(root/'src/lite3_description/urdf/Lite3_gazebo.urdf')
        lidar=urdf.getroot().find(".//sensor[@name='lite3_lidar']/lidar")
        self.assertIsNotNone(lidar)
        for axis in ['horizontal','vertical']:
            self.assertEqual(int(lidar.findtext(f'scan/{axis}/samples')),config[f'lidar_{axis}_samples'])
            for key in ['min','max']:self.assertAlmostEqual(float(lidar.findtext(f'scan/{axis}/{key}_angle')),config[f'lidar_{axis}_{key}'])
        self.assertAlmostEqual(float(lidar.findtext('range/max')),config['max_range'])

if __name__=='__main__':unittest.main()
