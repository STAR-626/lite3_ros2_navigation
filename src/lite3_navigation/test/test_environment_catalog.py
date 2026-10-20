"""Semantic data/alias/protocol regression; no network, Gazebo or credentials."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from environment_catalog import EnvironmentCatalog, parse_environment, validate_command
from environment_reader import validate_snapshot
from interaction_core import InvalidCommand
from deepseek_parser import validate, interpret, DeepSeekError

WORLD='<sdf><world name="large_warehouse"><model name="ground_plane"/><model name="spawn_marker"/><model name="destination_marker_1"/><model name="Lite3"/><model name="shelf_1"/><model name="shelf_2"/><model name="wall_north"/></world></sdf>'
SCENE={'ok':True,'world':'large_warehouse','models':[{'name':'shelf_1','entity_id':42,'pose':[1.,2.,.03,90.]}]}

class Catalog(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)
        self.world=self.path/'world.sdf';self.world.write_text(WORLD);self.file=self.path/'semantic.json'
        self.c=EnvironmentCatalog(self.world,'map-key',self.file);self.points={'点1':[3.,4.,0.]}
    def label(self,query='shelf_1',**kwargs):return self.c.label(query,kwargs,self.points,SCENE)
    def test_filter_and_categories(self):
        records=self.c.records(self.points,SCENE)
        self.assertEqual({r['source_name']for r in records},{'shelf_1','shelf_2','wall_north','点1'})
        self.assertEqual(self.c.resolve('shelf_1',self.points,SCENE)['category'],'货架')
    def test_persistent_atomic_labels_and_permissions(self):
        self.label(name='货架A',aliases=['一号货架'],description='到点访问')
        other=EnvironmentCatalog(self.world,'map-key',self.file)
        self.assertEqual(other.resolve('一号货架',self.points,SCENE)['name'],'货架A')
        self.assertEqual(self.file.stat().st_mode&0o777,0o600)
        self.assertEqual(list(self.path.glob('.environment-*')),[])
    def test_patch_preserves_fields(self):
        self.label(name='货架A',aliases=['一号货架']);self.label(category='检查点')
        self.assertEqual(self.c.resolve('一号货架',self.points,SCENE)['category'],'检查点')
    def test_unobserved_and_removed_no_pose(self):
        for snapshot,status in [(None,None),({'models':[]},False)]:
            r=self.c.resolve('shelf_1',self.points,snapshot)
            self.assertIs(r['present'],status);self.assertNotIn('pose_world',r)
            with self.assertRaises(InvalidCommand):self.c.label('shelf_1',{'name':'货架A'},self.points,snapshot)
    def test_current_position_is_not_persisted(self):
        self.label(name='货架A');self.assertNotIn('pose',self.file.read_text())
        moved={'models':[{'name':'shelf_1','entity_id':42,'pose':[5.,6.,.03,0.]}]}
        self.assertEqual(self.c.resolve('货架A',self.points,moved)['pose_world'][:2],[5.,6.])
    def test_runtime_created_model(self):
        snapshot={'models':[{'name':'test_box','entity_id':80,'pose':[0.,0.,0.,0.]}]}
        r=self.c.label('test_box',{'name':'临时箱子'},self.points,snapshot)
        self.assertEqual(r['category'],'箱子');self.assertFalse(r['navigable'])
    def test_map_and_world_binding(self):
        self.label(name='货架A');before=self.file.read_bytes()
        with self.assertRaises(InvalidCommand):EnvironmentCatalog(self.world,'other-map',self.file)
        self.world.write_text(WORLD.replace('shelf_2','shelf_3'))
        with self.assertRaises(InvalidCommand):EnvironmentCatalog(self.world,'map-key',self.file)
        self.assertEqual(self.file.read_bytes(),before)
    def test_duplicate_alias_is_ambiguous(self):
        self.label(name='重名');self.c.label('点1',{'name':'重名'},self.points,SCENE)
        with self.assertRaises(InvalidCommand):self.c.resolve('重名',self.points,SCENE)
        self.assertEqual(self.c.resolve('model:shelf_1',self.points,SCENE)['source_name'],'shelf_1')
    def test_no_object_centre_navigation(self):
        self.label(name='货架A')
        with self.assertRaisesRegex(InvalidCommand,'不能导航到物体中心'):self.c.place_reference('货架A',self.points,SCENE)
    def test_place_alias_navigation_and_exact_name_priority(self):
        self.c.label('点1',{'name':'设备区','aliases':['设备柜旁'],'category':'检查点'},self.points,SCENE)
        self.assertEqual(self.c.place_reference('设备柜旁',self.points,SCENE),'点1')
        self.assertEqual(self.c.place_reference('点1',self.points,SCENE),'点1')
    def test_no_coordinate_upload_in_context(self):
        self.label(name='货架A')
        context=self.c.context(self.points,SCENE)
        self.assertNotIn('pose',json.dumps(context));self.assertTrue(context['live_scene_available'])
    def test_explicit_commands_both_sources(self):
        self.assertEqual(parse_environment('列出类别 货架'),{'action':'env_list','category':'货架'})
        self.assertEqual(parse_environment('查询物体 一号货架')['object'],'一号货架')
        c=parse_environment('标注物体 shelf_1 名称=货架A 类别=货架 别名=一号货架,左侧货架 用途=到点巡检')
        self.assertEqual(c['object'],'model:shelf_1');self.assertEqual(c['aliases'],['一号货架','左侧货架'])
        self.assertEqual(parse_environment('标注地点 点1 类别=检查点')['object'],'place:点1')
        self.assertIsNone(parse_environment('停止'))
    def test_malformed_labels_fail(self):
        for c in [{'action':'env_label','object':'shelf_1'}, {'action':'env_label','object':'shelf_1','category':'捏造类别'},
                  {'action':'env_label','object':'shelf_1','aliases':['a','a']}, {'action':'env_label','object':'shelf_1','shell':'ls'},
                  {'action':'env_label','object':'shelf_1','name':'a\nb'}, {'action':'env_list','extra':True}]:
            with self.subTest(c=c),self.assertRaises(InvalidCommand):validate_command(c)
    def test_scene_protocol(self):
        self.assertEqual(validate_snapshot(SCENE,'large_warehouse'),SCENE)
        for change in [{'ok':False},{'world':'other'},{'models':[{'name':'shelf_1','entity_id':42,'pose':[0.,0.,float('nan'),0.]}]}, {'models':SCENE['models']*2}]:
            with self.subTest(change=change),self.assertRaises(ValueError):validate_snapshot({**SCENE,**change},'large_warehouse')
    def test_model_whitelist(self):
        validate({'action':'env_label','object':'model:shelf_1','name':'货架A','category':'货架'})
        with self.assertRaises(DeepSeekError):validate({'action':'env_label','object':'shelf_1','pose':[1,2,0]})
    def test_context_is_sent_as_user_data_without_coordinates(self):
        context=self.c.context(self.points,SCENE)
        class Fake:
            def open(s,request,timeout):
                body=json.loads(request.data);data=json.loads(body['messages'][-1]['content'])
                self.assertEqual(data['environment'],context)
                return io.BytesIO(json.dumps({'choices':[{'finish_reason':'stop','message':{'content':'{"action":"env_show","object":"model:shelf_1"}'}}]}).encode())
        config=self.path/'fake.json';config.write_text('{"api_key":"test-only"}');config.chmod(0o600)
        result=interpret('一号货架在哪里',list(self.points),config,Fake(),environment=context)
        self.assertEqual(result['action'],'env_show')

if __name__=='__main__':unittest.main()
