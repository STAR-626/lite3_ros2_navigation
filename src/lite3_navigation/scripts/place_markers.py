"""GUI-only Gazebo markers. No models, collision geometry or sensor visuals."""
import math
import queue
import subprocess
import threading
from google.protobuf import text_format
from gz.msgs10.marker_pb2 import Marker


def messages(points, old_names, namespace):
    result = []
    for name in old_names-set(points):
        for ident in (1, 2, 3):
            result.append(Marker(ns=namespace+name, id=ident, action=Marker.DELETE_MARKER, visibility=Marker.GUI))
    for name, (x, y, yaw) in points.items():
        for ident, kind in [(1, Marker.LINE_STRIP), (2, Marker.TEXT), (3, Marker.LINE_LIST)]:
            m = Marker(ns=namespace+name, id=ident, action=Marker.ADD_MODIFY, type=kind, visibility=Marker.GUI)
            m.pose.orientation.w = 1.;m.scale.x = m.scale.y = m.scale.z = .16 if ident == 2 else .025
            color = m.material.diffuse;color.r=.1;color.g=.9;color.b=.3;color.a=1.
            m.material.ambient.CopyFrom(color)
            if ident == 1:
                for k in range(33):
                    a=2*math.pi*k/32;m.point.add(x=x+.16*math.cos(a),y=y+.16*math.sin(a),z=.035)
            elif ident == 2:
                m.text=name;m.pose.position.x=x;m.pose.position.y=y;m.pose.position.z=.24
            else:
                a=math.radians(yaw);tx=x+.35*math.cos(a);ty=y+.35*math.sin(a)
                for px,py in [(x,y),(tx,ty),(tx,ty),(tx-.12*math.cos(a-.55),ty-.12*math.sin(a-.55)),(tx,ty),(tx-.12*math.cos(a+.55),ty-.12*math.sin(a+.55))]:
                    m.point.add(x=px,y=py,z=.04)
            result.append(m)
    return result


class MarkerWriter:
    def __init__(self, helper, map_key):
        self.helper=helper;self.namespace='lite3_places/'+map_key[:12]+'/'
        self.queue=queue.Queue(maxsize=1);self.error='';self.closed=False
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()

    def update(self, points):
        try:self.queue.get_nowait()
        except queue.Empty:pass
        self.queue.put_nowait({n:list(p) for n,p in points.items()})

    def run(self):
        old=set();proc=None
        try:
            proc=subprocess.Popen([self.helper],stdin=subprocess.PIPE,text=True)
            while not self.closed:
                try:points=self.queue.get(timeout=.2)
                except queue.Empty:continue
                for m in messages(points,old,self.namespace):
                    proc.stdin.write(text_format.MessageToString(m,as_one_line=True,as_utf8=True)+'\n')
                proc.stdin.flush();old=set(points)
        except Exception as error:self.error=str(error)
        finally:
            if proc:
                try:proc.stdin.close();proc.wait(timeout=2)
                except Exception:proc.kill();proc.wait()

    def close(self):
        self.closed=True;self.thread.join(timeout=3)
