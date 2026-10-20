import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from interaction_core import parse, number, Places, resolve, InvalidCommand


class Interaction(unittest.TestCase):
    def test_stop_exact(self):
        for text in ['停止','停下','关闭导航','取消这次导航']:
            self.assertEqual(parse(text)['action'],'stop')
    def test_enable(self):self.assertEqual(parse('开启导航'),{'action':'enable'})
    def test_named_save(self):
        p=parse('把坐标３、２，朝向９０度设成点1');self.assertEqual(p['pose'],[3,2,90]);self.assertEqual(p['name'],'点1')
    def test_chinese_number(self):
        self.assertEqual(number('负三点二'),-3.2);self.assertEqual(number('一百二十三'),123)
    def test_current(self):self.assertTrue(parse('把当前位置设成点2')['current'])
    def test_route(self):
        targets=parse('先去点1，再去点2，然后再回到原点')['targets']
        self.assertEqual(targets,[{'name':'点1'},{'name':'点2'},{'home':True}])
    def test_snapshot(self):
        points={'点1':[1,2,0]};route=resolve([{'name':'点1'}],points,None,0);points['点1'][0]=8
        self.assertEqual(route[0]['pose'][0],1)
    def test_missing_stops_whole_route(self):
        with self.assertRaises(InvalidCommand):resolve([{'name':'点1'},{'name':'点2'}],{'点1':[1,2,0]},None,0)
    def test_omitted_yaw(self):
        c=parse('去坐标3、2');self.assertEqual(resolve(c['targets'],{},None,42)[0]['pose'],[3,2,42])
    def test_invalid_commands(self):
        for text in ['去坐标3','去坐标nan、2','去坐标1、2，朝向181度','去点1; rm -rf /','执行ls','继续','前进两米','去那里']:
            with self.subTest(text=text),self.assertRaises(InvalidCommand):parse(text)
    def test_reserved_home(self):
        with self.assertRaises(InvalidCommand):parse('把坐标1、2设成原点')
    def test_place_operations(self):
        self.assertEqual(parse('点1在哪里')['action'],'show');self.assertEqual(parse('删除点1')['action'],'delete')
    def test_atomic_store_and_reload(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'places.json';p=Places(path,'map');p.save('点1',[1,2,3]);p=Places(path,'map')
            self.assertEqual(p.points['点1'],[1,2,3]);p.delete('点1');self.assertEqual(Places(path,'map').points,{})
    def test_map_mismatch_preserves_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'places.json';Places(path,'a').save('点1',[1,2,0]);old=path.read_bytes()
            with self.assertRaises(InvalidCommand):Places(path,'b')
            self.assertEqual(path.read_bytes(),old)
    def test_nonfinite_store(self):
        for pose in [[1,2,float('nan')],[True,2,3],[1,2,181]]:
            with self.assertRaises(InvalidCommand):Places.validate(pose)
    def test_home_not_map_zero(self):
        self.assertEqual(resolve(parse('回到原点')['targets'],{},[-3,-4,10],0)[0]['pose'],[-3,-4,10])


if __name__=='__main__':unittest.main()
