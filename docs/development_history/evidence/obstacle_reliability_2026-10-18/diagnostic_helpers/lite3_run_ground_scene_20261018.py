import os,subprocess,socket,tempfile,signal,time,json
from pathlib import Path
for port in (20001,30010,30011):
 with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:s.bind(('127.0.0.1',port))
out=Path(tempfile.mkdtemp(prefix='lite3-ground-scene-20261018-'));root=Path('/home/ma/lite3_ws')
world=out/'warehouse.sdf';world.write_bytes((root/'src/lite3_gazebo/worlds/large_warehouse.sdf').read_bytes())
env=dict(os.environ,ROS_DOMAIN_ID='192',GZ_PARTITION='lite3_3d_validation_20261014')
log=(out/'simulation.log').open('w');proc=subprocess.Popen(['ros2','launch','lite3_gazebo','simulation.launch.py','gui:=false','rviz:=false','paused:=false','world:='+str(world)],env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
try:
 time.sleep(4)
 result=subprocess.run(['python3',str(root/'src/lite3_perception/test/check_costmap_scene.py')],env=env,stdout=(out/'probe.log').open('w'),stderr=subprocess.STDOUT,timeout=120)
 if Path('/tmp/lite3-3d-costmap-result.json').exists():
  data=json.loads(Path('/tmp/lite3-3d-costmap-result.json').read_text());(out/'result.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
 print('GROUND_SCENE',out,'EXIT',result.returncode,flush=True)
 print((out/'probe.log').read_text()[-4500:],flush=True)
finally:
 if proc.poll() is None:
  os.killpg(proc.pid,signal.SIGINT)
  try:proc.wait(timeout=15)
  except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=5)
 for p in Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:
   command=(p/'cmdline').read_bytes().replace(b'\0',b' ').split()
   if str(world).encode() in command and any(b'gz' in a for a in command):os.kill(int(p.name),signal.SIGTERM)
  except (FileNotFoundError,PermissionError,ProcessLookupError):pass
 log.close()
