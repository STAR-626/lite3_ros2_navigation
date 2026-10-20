"""Geometry, full-area grid collision and temporary approach protocol checks."""
import math
from pathlib import Path
import sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from approach_geometry import collision_bounds,candidates,Grid,polygons_intersect,same_object,validate_approach,parse_approach
from deepseek_parser import validate,DeepSeekError
from interaction_core import InvalidCommand

class Geometry(unittest.TestCase):
    def test_known_shelf_real_collision(self):
        world=Path(__file__).resolve().parents[2]/'lite3_gazebo/worlds/large_warehouse.sdf'
        bounds=collision_bounds(world,'shelf_1')
        self.assertGreaterEqual(bounds[1]-bounds[0],.5)
        self.assertGreaterEqual(bounds[3]-bounds[2],1.56)
        self.assertLess(bounds[1]-bounds[0],1.)
    def test_four_sides_and_physical_edge_gap(self):
        poses=candidates((-.25,.25,-.8,.8),[0,0,0,0],(.47,.25),.4)
        self.assertEqual(len(poses),12)
        self.assertTrue(any(abs(p[0]-(.25+.47+.4+.05))<1e-6 and p[2]==-180 for p in poses))
        self.assertTrue(all(abs(p[0])>.25 or abs(p[1])>.8 for p in poses))
    def test_world_north_after_object_rotation(self):
        poses=candidates((-.25,.25,-.8,.8),[2,3,0,90],(.47,.25),.5,'north')
        self.assertEqual(len(poses),3)
        for x,y,yaw in poses:
            self.assertGreater(y,3+.25+.47+.5);self.assertAlmostEqual(yaw,-90,places=6)
    def test_near_candidates_ranked_first(self):
        poses=candidates((-.25,.25,-.8,.8),[0,0,0,0],(.47,.25),start=(-4,0))
        ds=[math.hypot(p[0]+4,p[1])for p in poses];self.assertEqual(ds,sorted(ds))
    def test_footprint_interior_obstacle_rejected(self):
        data=[0]*40000;data[100*200+100]=254
        g=Grid(200,200,.05,(-5,-5),data)
        self.assertFalse(g.clear([0,0,0],(.47,.25)))
    def test_rotated_corner_collision_rejected(self):
        data=[0]*40000;data[106*200+106]=254
        self.assertFalse(Grid(200,200,.05,(-5,-5),data).clear([0,0,45],(.47,.25)))
    def test_grid_unknown_and_outside_rejected(self):
        g=Grid(200,200,.05,(-5,-5),[0]*40000)
        self.assertTrue(g.clear([0,0,90],(.47,.25)));self.assertFalse(g.clear([4.9,0,0],(.47,.25)))
        g.data[100*200+100]=255;self.assertFalse(g.clear([0,0,0],(.47,.25)))
    def test_inflation_not_all_treated_lethal(self):
        data=[120]*40000;g=Grid(200,200,.05,(-5,-5),data)
        self.assertTrue(g.clear([0,0,0],(.47,.25)))
        data[100*200+100]=253;self.assertFalse(g.clear([0,0,0],(.47,.25)))
    def test_cell_edge_overlap_without_centre_inside(self):
        self.assertTrue(polygons_intersect([(0,0),(.3,0),(.3,.3),(0,.3)],[(.29,.29),(.4,.29),(.4,.4),(.29,.4)]))
    def test_side_and_distance_protocol(self):
        c=parse_approach('去货架A南侧 距离=0.5');self.assertEqual(c['side'],'south');self.assertEqual(c['clearance'],.5)
        self.assertEqual(parse_approach('去一号货架旁边')['object'],'一号货架')
        self.assertIsNone(parse_approach('停止'))
        validate({'action':'approach','object':'model:shelf_1'})
        for c in [{'action':'approach','object':'shelf_1','clearance':True},{'action':'approach','object':'shelf_1','clearance':.05},{'action':'approach','object':'shelf_1','side':'left'},{'action':'approach','object':'shelf_1','pose':[0,0,0]}]:
            with self.subTest(c=c),self.assertRaises(DeepSeekError):validate(c)
    def test_object_change_invalidates(self):
        old={'entity_id':1,'pose':[1,2,0,0],'level':True}
        self.assertTrue(same_object(old,dict(old)));self.assertFalse(same_object(old,None))
        self.assertFalse(same_object(old,{**old,'entity_id':2}));self.assertFalse(same_object(old,{**old,'pose':[1.1,2,0,0]}))
        self.assertFalse(same_object(old,{**old,'level':False}))
    def test_unknown_dynamic_mesh_and_relative_frames_refused(self):
        with tempfile.TemporaryDirectory()as d:
            p=Path(d)/'world.sdf'
            for body in ['<model name="x"><static>false</static></model>','<model name="x"><static>true</static><link name="l"><collision name="c"><geometry><mesh><uri>unknown</uri></mesh></geometry></collision></link></model>','<model name="x"><static>true</static><pose relative_to="y">0 0 0 0 0 0</pose></model>']:
                p.write_text('<sdf><world name="w">'+body+'</world></sdf>')
                with self.assertRaises(InvalidCommand):collision_bounds(p,'x')

if __name__=='__main__':unittest.main()
