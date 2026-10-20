#!/usr/bin/env python3
"""Domain219: actual Gazebo lidar rendering, GUI-only place markers and no world models."""
import json, os, signal, subprocess, tempfile, time, math, sys
from pathlib import Path
import numpy as np
import rclpy
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import PointCloud2
from sensor_msgs_py import point_cloud2
from google.protobuf import text_format
from gz.msgs10.marker_pb2 import Marker
from gz.msgs10.marker_v_pb2 import Marker_V
from ament_index_python.packages import get_package_prefix


def main():
    assert os.environ.get('ROS_DOMAIN_ID')=='219'
    assert os.environ.get('GZ_PARTITION')=='lite3_markers_20261020'
    root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root/'src/lite3_navigation/scripts'))
    from place_markers import messages
    out=Path(tempfile.mkdtemp(prefix='lite3-markers-'));procs=[];logs=[]
    def spawn(cmd,label,**kw):
        f=(out/(label+'.log')).open('w');logs.append(f);p=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT,start_new_session=True,**kw);procs.append(p);return p
    rclpy.init();n=rclpy.create_node('place_marker_fixture');clouds=[]
    n.create_subscription(PointCloud2,'/clearing_fixture/lidar/points',lambda m:clouds.append(m),qos_profile_sensor_data)
    def wait(pred,seconds=20):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            rclpy.spin_once(n,timeout_sec=.03)
            if pred():return
        raise AssertionError('timeout '+str(out))
    def pause(seconds):
        now=time.monotonic();wait(lambda:time.monotonic()-now>seconds,seconds+2)
    def near_hits():
        a=point_cloud2.read_points(clouds[-1],field_names=('x','y','z'),skip_nans=True)
        return int(np.sum((a['x']>.6)&(a['x']<1.4)&(abs(a['y'])<.35)&(abs(a['z'])<.25)))
    try:
        spawn(['gz','sim','-s','-r','--headless-rendering',str(root/'src/lite3_perception/test/fixtures/clearing_lidar.sdf')],'gazebo')
        spawn(['ros2','run','ros_gz_bridge','parameter_bridge','/clearing_fixture/lidar/points@sensor_msgs/msg/PointCloud2[gz.msgs.PointCloudPacked'],'bridge')
        config=out/'gui.config'
        config.write_text('<window><width>650</width><height>450</height></window><plugin filename="MinimalScene" name="3D View"><engine>ogre2</engine><scene>scene</scene><camera_pose>-2 -2 3 0 .6 .7</camera_pose></plugin><plugin filename="GzSceneManager" name="Scene Manager"/><plugin filename="MarkerManager" name="Marker manager"/>')
        spawn(['gz','sim','-g','--gui-config',str(config)],'gui')
        wait(lambda:len(clouds)>10)
        pause(5)
        before=near_hits();assert before==0
        helper=spawn([str(Path(get_package_prefix('lite3_navigation'))/'lib/lite3_navigation/place_marker_transport'),'--audit'],'markers',stdin=subprocess.PIPE,text=True)
        payload=messages({'点1':[1.,0.,90.]},set(),'lite3_places/test/')
        # A deliberately elevated GUI-only sphere intersects otherwise empty
        # lidar beams: it must stay invisible to sensors despite visible shape.
        sphere=Marker(ns='lite3_places/test/点1',id=4,action=Marker.ADD_MODIFY,type=Marker.SPHERE,visibility=Marker.GUI)
        sphere.pose.position.x=1.;sphere.pose.position.z=.5;sphere.pose.orientation.w=1.
        sphere.scale.x=sphere.scale.y=sphere.scale.z=.4
        payload.append(sphere)
        for m in payload:helper.stdin.write(text_format.MessageToString(m,as_one_line=True,as_utf8=True)+'\n')
        helper.stdin.flush();pause(2)
        assert near_hits()==before
        # Query MarkerManager to ensure absence of hits was not just unsent data.
        result=subprocess.run(['gz','service','-s','/marker/list','--reqtype','gz.msgs.Empty','--reptype','gz.msgs.Marker_V','--timeout','3000','--req',''],capture_output=True,text=True,timeout=5)
        assert result.returncode==0 and 'lite3_places/test/'in result.stdout,result.stdout+result.stderr
        (out/'marker_list.txt').write_text(result.stdout)
        listed=Marker_V();text_format.Parse(result.stdout,listed)
        assert any(m.ns=='lite3_places/test/点1' and m.id==2 for m in listed.marker)
        forwarded=[]
        for line in (out/'markers.log').read_text().splitlines():
            if 'ns: "lite3_places/test/' in line:
                m=Marker();text_format.Parse(line,m);forwarded.append(m)
        label=[m for m in forwarded if m.id==2]
        assert len(label)==1 and label[0].type==Marker.LINE_LIST and len(label[0].point)>20
        assert all(m.visibility==Marker.GUI for m in forwarded)
        assert 'Invalid Marker type' not in (out/'gui.log').read_text()
        scene=subprocess.run(['gz','service','-s','/world/clearing_fixture/scene/info','--reqtype','gz.msgs.Empty','--reptype','gz.msgs.Scene','--timeout','3000','--req',''],capture_output=True,text=True,timeout=5)
        assert scene.returncode==0 and 'lite3_places/'not in scene.stdout
        for m in messages({}, {'点1'},'lite3_places/test/'):
            helper.stdin.write(text_format.MessageToString(m,as_one_line=True,as_utf8=True)+'\n')
        helper.stdin.flush();pause(.5)
        listed=subprocess.run(['gz','service','-s','/marker/list','--reqtype','gz.msgs.Empty','--reptype','gz.msgs.Marker_V','--timeout','3000','--req',''],capture_output=True,text=True,timeout=5)
        remaining=Marker_V();text_format.Parse(listed.stdout,remaining)
        assert not any(m.ns=='lite3_places/test/点1' and m.id in (1,2,3) for m in remaining.marker)
        result={'passed':True,'robot_started':False,'rl_started':False,'checks':['actual MarkerManager contains GUI marker namespace','Chinese label converted to rendered line geometry; no Ogre2 invalid marker type','GUI sphere intersects rays but adds zero lidar obstacle hits','no world models created','place ring/label/arrow removed from actual MarkerManager'], 'before_near_hits':before,'after_near_hits':near_hits(),'out':str(out)}
        (out/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
    finally:
        for p in reversed(procs):
            if p.poll()is None:
                os.killpg(p.pid,signal.SIGINT)
                try:p.wait(timeout=5)
                except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=5)
        for f in logs:f.close()
        n.destroy_node();rclpy.shutdown()


if __name__=='__main__':main()
