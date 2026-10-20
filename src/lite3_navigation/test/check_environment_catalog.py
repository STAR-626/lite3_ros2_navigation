#!/usr/bin/env python3
"""Domain221/GZ partition isolated real-world scene + installed ROS backend.
No robot/RL, live API or credentials; DeepSeek outputs are synthetic.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import uuid
import rclpy
from geometry_msgs.msg import TransformStamped
from std_msgs.msg import String
from std_srvs.srv import SetBool
from tf2_ros import TransformBroadcaster


def main():
    assert os.environ.get('ROS_DOMAIN_ID')=='221'
    assert os.environ.get('GZ_PARTITION')=='lite3_semantic_environment_20261020'
    root=Path(__file__).resolve().parents[3];out=Path(tempfile.mkdtemp(prefix='lite3-environment-'))
    installed=root/'install/lite3_navigation/lib/lite3_navigation'
    world=root/'install/lite3_gazebo/share/lite3_gazebo/worlds/large_warehouse.sdf'
    map_yaml=root/'install/lite3_gazebo/share/lite3_gazebo/maps/large_warehouse.yaml'
    processes=[];logs=[];events=[];checks=[]
    rclpy.init();node=rclpy.create_node('environment_fixture');tf=TransformBroadcaster(node)
    pub=node.create_publisher(String,'/lite3/interaction/input',40)
    node.create_subscription(String,'/lite3/interaction/events',lambda m:events.append(json.loads(m.data)),100)
    session=str(uuid.uuid4())
    def send(kind,text='',ident=None):
        ident=ident or uuid.uuid4().hex
        pub.publish(String(data=json.dumps({'session':session,'kind':kind,'id':ident,'text':text},ensure_ascii=False)));return ident
    def heartbeat():
        send('heartbeat')
        t=TransformStamped();t.header.frame_id='map';t.child_frame_id='base_footprint';t.header.stamp=node.get_clock().now().to_msg();t.transform.rotation.w=1.;tf.sendTransform(t)
    node.create_timer(.15,heartbeat)
    def stop(req,rep):rep.success=True;rep.message='test stop';return rep
    node.create_service(SetBool,'/lite3/set_navigation_enabled',stop);node.create_service(SetBool,'/lite3/set_stop',stop)
    def spawn(cmd,name):
        log=open(out/(name+'.log'),'w');logs.append(log)
        proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);processes.append(proc);return proc
    def kill(proc):
        if proc.poll() is None:
            os.killpg(proc.pid,signal.SIGINT)
            try:proc.wait(timeout=7)
            except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
    def wait(condition,seconds=12):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            rclpy.spin_once(node,timeout_sec=.03)
            if condition():return
        raise AssertionError(str(events[-5:])+'\nout='+str(out))
    def pause(seconds):
        end=time.monotonic()+seconds;wait(lambda:time.monotonic()>end,seconds+1)
    def command(text,code='OK'):
        ident=send('text',text)
        wait(lambda:any(e['id']==ident and e['code']not in ('PARSING','INTERPRETED')for e in events))
        reply=next(e for e in reversed(events)if e['id']==ident and e['code']not in ('PARSING','INTERPRETED'))
        assert reply['code']==code,reply;return reply
    def backend(mode):
        args=['--ros-args','-p','world_sdf:='+str(world),'-p','map_yaml:='+str(map_yaml),'-p','places_file:='+str(out/'places.json'),'-p','environment_file:='+str(out/'semantics.json'),'-p','language_mode:='+mode]
        if mode=='rules':cmd=[str(installed/'interaction_backend')]
        else:
            stub=out/'model_stub.py'
            stub.write_text('''import sys,time
from importlib.machinery import SourceFileLoader
sys.path.insert(0,sys.argv.pop(1))
b=SourceFileLoader('interaction_backend',sys.path[0]+'/interaction_backend').load_module()
def model(text,names,history=None,environment=None):
    assert environment['source']=='gazebo_truth_and_user_annotations'
    assert any(r['name']=='货架A' and '一号货架' in r['aliases'] for r in environment['objects'])
    assert not any('pose' in key for r in environment['objects'] for key in r)
    if text=='慢环境请求':
        time.sleep(1.2);return {'action':'env_show','object':'model:shelf_1'}
    if text=='请告诉我一号货架的情况':return {'action':'env_show','object':'model:shelf_1'}
    if text=='请把一号货架的用途改为设备巡检':return {'action':'env_label','object':'model:shelf_1','description':'设备巡检'}
    if text=='请去一号货架':return {'action':'route','targets':[{'name':'一号货架'}]}
    raise ValueError('unknown mock request')
b.interpret=model
b.main()
''')
            cmd=['/usr/bin/python3',str(stub),str(installed)]
        proc=spawn(cmd+args,'backend_'+mode)
        for _ in range(30):
            ident=send('connect');pause(.15)
            if any(e['id']==ident and e['code']=='OK'for e in events):return proc
            assert proc.poll() is None
        raise AssertionError('no backend connect')
    def service(op,reqtype,request):
        rep=subprocess.run(['gz','service','-s','/world/large_warehouse/'+op,'--reqtype',reqtype,'--reptype','gz.msgs.Boolean','--timeout','3000','--req',request],capture_output=True,text=True,timeout=5)
        assert rep.returncode==0 and 'data: true'in rep.stdout,(rep.stdout,rep.stderr)
    server=spawn(['gz','sim','-s','-r',str(world)],'gazebo')
    try:
        proc=backend('rules');pause(3)
        # Query until native scene has confirmed present models.
        for _ in range(15):
            reply=command('查询物体 shelf_1')
            if reply['environment']['present'] is True:break
            pause(.3)
        r=reply['environment'];assert r['present'] is True and abs(r['pose_world'][0]+2.2101)<.01
        objects=command('列出环境')['environment']
        assert sum(r['category']=='货架'for r in objects)==17
        assert not any(r['source_name']in ('ground_plane','concrete_floor','spawn_marker','Lite3','box_obstacle_1','destination_marker_1')for r in objects)
        checks.append('native Gazebo model directory: 17 shelves plus walls, filtered ground/markers/removed models')
        command('标注物体 shelf_1 名称=货架A 类别=货架 别名=一号货架,左侧货架 用途=到点巡检')
        assert command('查询物体 一号货架')['environment']['name']=='货架A'
        assert command('货架A在哪里')['environment']['id']=='model:shelf_1'
        checks.append('local labels/name/aliases query without model or API')
        command('把坐标-4、-4，朝向0度设成点1')
        command('标注地点 点1 类别=检查点 名称=设备区 别名=设备柜旁')
        assert command('列出类别 检查点')['environment'][0]['id']=='place:点1'
        assert '点1'in command('设备柜旁在哪里')['message']
        checks.append('existing place registry unchanged; semantic category and alias references work')
        command('去一号货架','INVALID')
        checks.append('model-centre navigation rejected locally before any task dispatch')
        service('set_pose','gz.msgs.Pose','name: "shelf_1", position: {x: -1.0, y: 3.0, z: 0.03}, orientation: {w: 1.0}')
        for _ in range(20):
            r=command('查询物体 货架A')['environment']
            if abs(r['pose_world'][0]+1.0)<.01:break
            pause(.2)
        assert abs(r['pose_world'][0]+1.0)<.01 and abs(r['pose_world'][1]-3.0)<.01,r
        checks.append('native model pose updates after set_pose, not cached initial SDF coordinates')
        sdf='<sdf version="1.8"><model name="semantic_test_box"><static>true</static><pose>3 -3 .3 0 0 0</pose><link name="link"><visual name="v"><geometry><box><size>.4 .4 .6</size></box></geometry></visual></link></model></sdf>'
        service('create','gz.msgs.EntityFactory','sdf: '+json.dumps(sdf))
        for _ in range(20):
            pause(.2)
            objects=command('列出环境')['environment']
            if any(r['source_name']=='semantic_test_box'for r in objects):break
        assert any(r['source_name']=='semantic_test_box'for r in objects)
        command('标注物体 semantic_test_box 名称=演示箱子 类别=箱子')
        service('remove','gz.msgs.Entity','name: "semantic_test_box", type: MODEL')
        for _ in range(20):
            pause(.2);r=command('查询物体 演示箱子')['environment']
            if r['present'] is False:break
        assert r['present'] is False and 'pose_world'not in r
        checks.append('runtime creation/removal: annotations retained but removed objects have no live pose')
        send('close');pause(.4);kill(proc);events.clear();session=str(uuid.uuid4())
        proc=backend('deepseek');pause(2)
        assert command('查询物体 一号货架')['environment']['name']=='货架A'
        checks.append('annotations survive backend restart; private file reused')
        assert command('请告诉我一号货架的情况')['environment']['id']=='model:shelf_1'
        command('请把一号货架的用途改为设备巡检')
        assert command('查询物体 shelf_1')['environment']['description']=='设备巡检'
        command('请去一号货架','INVALID')
        checks.append('synthetic model receives real semantic context and uses whitelist query/label; object route rejected')
        ident=send('text','慢环境请求')
        wait(lambda:any(e['id']==ident and e['code']=='PARSING'for e in events))
        command('标注物体 shelf_1 用途=更新后的巡检用途')
        wait(lambda:any(e['id']==ident and e['code']=='STALE_CONTEXT'for e in events))
        checks.append('annotations changed during model parsing invalidate the old semantic result')
        kill(server);pause(3)
        r=command('查询物体 货架A')['environment']
        assert r['present'] is None and 'pose_world'not in r
        checks.append('Gazebo unavailable: stale position withheld instead of reported as current')
        send('close');pause(.4);kill(proc)
        result={'passed':True,'checks':checks,'real_api_called':False,'robot_started':False,'rl_started':False,'out':str(out)}
        (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False),flush=True)
    finally:
        for proc in reversed(processes):kill(proc)
        for log in logs:log.close()
        node.destroy_node();rclpy.shutdown()

if __name__=='__main__':main()
