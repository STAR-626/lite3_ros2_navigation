"""Bounded background reader for a read-only Gazebo helper; never blocks ROS."""
import copy
import json
import math
import subprocess
import threading
import time


def validate_snapshot(raw, world):
    if not isinstance(raw, dict) or set(raw) != {'ok','world','models'} or raw['ok'] is not True or raw['world'] != world:
        raise ValueError('场景读取尚未就绪。')
    models = raw['models']
    if not isinstance(models, list) or len(models) > 256:raise ValueError('场景模型数量过多。')
    names = set()
    for m in models:
        if not isinstance(m, dict) or set(m) not in ({'name','entity_id','pose'},{'name','entity_id','pose','level'}):raise ValueError('模型字段不合法。')
        if 'level' in m and type(m['level']) is not bool:raise ValueError('物体姿态标志不合法。')
        name=m['name'];pose=m['pose'];ident=m['entity_id']
        if not isinstance(name,str) or not 0<len(name)<=128 or any(ord(c)<32 for c in name) or name in names:raise ValueError('模型名称不合法。')
        names.add(name)
        if type(ident) is not int or not 0<=ident<=2**32-1:raise ValueError('实体编号不合法。')
        if not isinstance(pose,list) or len(pose)!=4 or any(type(n)not in (float,int) or not math.isfinite(n) for n in pose) or abs(pose[3])>180:raise ValueError('模型位置不合法。')
    return raw


class EnvironmentReader:
    def __init__(self, helper, world):
        self.lock=threading.Lock();self.value=None;self.updated=0.;self.error='等待Gazebo场景';self.closed=False
        self.proc=subprocess.Popen([helper,world],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
        self.thread=threading.Thread(target=self.run,args=(world,),daemon=True);self.thread.start()

    def run(self, world):
        try:
            while not self.closed:
                line=self.proc.stdout.readline(131073)
                if not line:break
                try:
                    if len(line)>131072 or not line.endswith(b'\n'):raise ValueError('场景数据过长。')
                    value=validate_snapshot(json.loads(line),world)
                    with self.lock:self.value=value;self.updated=time.monotonic();self.error=''
                except (ValueError,TypeError,OverflowError):
                    with self.lock:self.value=None;self.error='当前Gazebo场景不可用，位置不作为实时数据。'
        finally:
            with self.lock:self.value=None;self.error='场景读取进程已退出。'

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.value) if time.monotonic()-self.updated<5 else None

    def close(self):
        self.closed=True
        if self.proc.poll() is None:
            self.proc.terminate()
            try:self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:self.proc.kill();self.proc.wait()
        self.thread.join(timeout=2);self.proc.stdout.close()
