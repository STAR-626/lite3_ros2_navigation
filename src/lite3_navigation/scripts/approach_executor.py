"""Asynchronous temporary object-approach resolver using existing Nav2 planner.
Does not drive cmd_vel, modify maps, unlock navigation, or save waypoints.
"""
import json
import hashlib
import math
import time
import yaml
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import ComputePathToPose
from nav2_msgs.srv import GetCostmap
from rcl_interfaces.srv import GetParameters
from rclpy.action import ActionClient
from rclpy.time import Time
from std_srvs.srv import Trigger
from interaction_core import InvalidCommand
from language_context import navigation_problem
from approach_geometry import collision_bounds, candidates, Grid, same_object, validate_approach


class ApproachExecutor:
    def __init__(self,node):
        self.node=node;self.job=None;self.watch=None
        self.parameters=node.create_client(GetParameters,'/global_costmap/global_costmap/get_parameters')
        self.planner_parameters=node.create_client(GetParameters,'/planner_server/get_parameters')
        self.costmap=node.create_client(GetCostmap,'/global_costmap/get_costmap')
        self.planner=ActionClient(node,ComputePathToPose,'/compute_path_to_pose')

    def current(self,job):
        n=self.node
        return self.job is job and job['generation']==n.generation and job['owner']==n.owner and not n.closing and not n.stop_needed

    def object_now(self,name):
        scene=self.node.environment_reader.snapshot()
        return next((m for m in scene['models']if m['name']==name),None)if scene else None

    def start(self,c,request):
        validate_approach(c);n=self.node
        if self.job or n.busy or n.sending or n.stop_needed:raise InvalidCommand('已有任务或停止操作，请等待或输入停止。')
        if not n.environment:raise InvalidCommand(n.environment_error)
        scene=n.environment_reader.snapshot();record=n.environment.resolve(c['object'],n.places.points,scene)
        if record['kind']!='model':raise InvalidCommand('该对象是已保存地点，请直接使用“去点名”。')
        model=self.object_now(record['source_name'])
        if model is None or model.get('level')is not True:raise InvalidCommand('物体实时位姿不可用或已倾斜，不能生成平地接近点。')
        if hashlib.sha256(n.environment.world_file.read_bytes()).hexdigest()!=n.environment.world_digest:
            raise InvalidCommand('场景文件已改变，请重启后重新建立语义绑定。')
        bounds=collision_bounds(n.environment.world_file,record['source_name'])
        if not all(client.service_is_ready()for client in (self.parameters,self.planner_parameters,self.costmap,n.state))or not self.planner.server_is_ready():
            raise InvalidCommand('临时接近点需要任务状态、全局costmap及Smac规划器接口就绪。')
        job={'generation':n.generation,'owner':n.owner,'request':request,'model':model,'name':record['name'],
             'bounds':bounds,'side':c.get('side','any'),'clearance':c.get('clearance',.4),
             'deadline':time.monotonic()+35.,'handle':None,'plan_deadline':None,'attempts':0}
        self.job=job;n.busy=True
        n.emit('正在为“'+record['name']+'”计算临时接近位置；不会保存为长期地点。',request=request)
        def checked(rep):
            if not self.current(job):return
            try:
                if not rep.success:raise InvalidCommand('导航状态不可用。')
                problem=navigation_problem(json.loads(rep.message))
                if problem:raise InvalidCommand(problem)
            except (ValueError,KeyError,TypeError)as error:self.fail(job,str(error));return
            n.rpc(self.parameters,GetParameters.Request(names=['footprint','footprint_padding','global_frame']),
                  lambda rep:self.footprint(job,rep),lambda msg:self.fail(job,msg))
        n.rpc(n.state,Trigger.Request(),checked,lambda msg:self.fail(job,msg))

    def footprint(self,job,rep):
        if not self.current(job):return
        try:
            values=rep.values
            if len(values)!=3 or values[0].type!=4 or values[2].string_value!='map' or values[1].type!=3:raise ValueError()
            points=yaml.safe_load(values[0].string_value);padding=values[1].double_value
            if not isinstance(points,list)or not 3<=len(points)<=16 or not 0<=padding<=.5:raise ValueError()
            if any(not isinstance(p,list)or len(p)!=2 or any(type(x)not in (float,int)or not math.isfinite(x)for x in p)for p in points):raise ValueError()
            job['robot']=(max(abs(p[0])for p in points)+padding,max(abs(p[1])for p in points)+padding)
            if not .1<job['robot'][0]<2 or not .1<job['robot'][1]<2:raise ValueError()
        except (ValueError,TypeError,yaml.YAMLError):self.fail(job,'无法读取有效的map坐标系导航保护轮廓。');return
        self.node.rpc(self.planner_parameters,GetParameters.Request(names=['GridBased.plugin']),
                      lambda rep:self.profile(job,rep),lambda msg:self.fail(job,msg))

    def profile(self,job,rep):
        if not self.current(job):return
        if len(rep.values)!=1 or rep.values[0].string_value!='nav2_smac_planner::SmacPlannerLattice':
            self.fail(job,'本版自动接近点要求默认Smac Lattice全轮廓规划，当前规划器不匹配。');return
        self.fetch_map(job,False)

    def fetch_map(self,job,final):
        self.node.rpc(self.costmap,GetCostmap.Request(),lambda rep:self.map_ready(job,rep,final),lambda msg:self.fail(job,msg))

    def map_ready(self,job,rep,final):
        if not self.current(job):return
        n=self.node
        try:
            m=rep.map;info=m.metadata;q=info.origin.orientation;p=info.origin.position
            age=(n.get_clock().now()-Time.from_msg(info.update_time)).nanoseconds/1e9
            if m.header.frame_id!='map' or not -.2<=age<=2.5 or abs(q.x)+abs(q.y)+abs(q.z)>1e-6 or abs(abs(q.w)-1)>1e-6 or not math.isfinite(p.x+p.y):
                raise InvalidCommand('全局障碍图过期或坐标系不匹配。')
            grid=Grid(info.size_x,info.size_y,info.resolution,(p.x,p.y),m.data)
            if not same_object(job['model'],self.object_now(job['model']['name'])):raise InvalidCommand('物体已移动、消失或位姿失效，请重新请求。')
            if final:
                if not grid.clear(job['selected'],job['robot']):raise InvalidCommand('接近位置在规划期间出现新障碍，请重新请求。')
                self.commit(job);return
            start=n.pose()
            poses=candidates(job['bounds'],job['model']['pose'],job['robot'],job['clearance'],job['side'],start)
            job['candidates']=[pose for pose in poses if grid.clear(pose,job['robot'])]
            if not job['candidates']:raise InvalidCommand('指定方位没有能容纳机器狗保护轮廓的空闲接近位置；未发送导航。')
            job['candidates']=job['candidates'][:12]
            self.next_candidate(job)
        except (ValueError,TypeError,OverflowError)as error:self.fail(job,str(error))

    def next_candidate(self,job):
        if not self.current(job):return
        if not job['candidates']:
            self.fail(job,'候选接近位置均未通过规划器可达性验证；未发送导航。');return
        job['selected']=job['candidates'].pop(0);job['attempts']+=1
        x,y,angle=job['selected'];goal=ComputePathToPose.Goal();goal.planner_id='GridBased';goal.use_start=False
        goal.goal=PoseStamped();goal.goal.header.frame_id='map';goal.goal.header.stamp=self.node.get_clock().now().to_msg()
        goal.goal.pose.position.x=x;goal.goal.pose.position.y=y
        goal.goal.pose.orientation.z=math.sin(math.radians(angle)/2);goal.goal.pose.orientation.w=math.cos(math.radians(angle)/2)
        job['plan_deadline']=time.monotonic()+6
        self.node.emit(f"验证第{job['attempts']}个候选位置（{x:.2f}, {y:.2f}）。",'PROGRESS')
        future=self.planner.send_goal_async(goal)
        def accepted(f):
            try:handle=f.result()
            except Exception:
                self.fail(job,'规划目标提交异常。');return
            if not self.current(job):
                if handle.accepted:handle.cancel_goal_async()
                return
            if not handle.accepted:self.fail(job,'规划器拒绝候选验证。');return
            job['handle']=handle
            handle.get_result_async().add_done_callback(lambda f:self.planned(job,f))
        future.add_done_callback(accepted)

    def planned(self,job,future):
        if not self.current(job):return
        job['handle']=None;job['plan_deadline']=None
        try:
            reply=future.result();result=reply.result
            if reply.status!=4 or result.error_code!=0:
                if result.error_code not in (206,208):
                    self.fail(job,'规划器无法验证路线，错误码'+str(result.error_code)+'；请检查起点/定位/规划服务。');return
                self.next_candidate(job);return
            poses=result.path.poses;target=job['selected']
            if result.path.header.frame_id!='map' or not poses:raise InvalidCommand('规划器返回空路线或错误坐标系。')
            for p in poses:
                q=p.pose.orientation;v=p.pose.position
                if p.header.frame_id not in ('','map')or not all(math.isfinite(x)for x in (v.x,v.y,v.z,q.x,q.y,q.z,q.w))or abs(q.x*q.x+q.y*q.y+q.z*q.z+q.w*q.w-1)>.01:raise InvalidCommand('规划路线含无效位姿。')
            end=poses[-1].pose;q=end.orientation
            yaw=math.degrees(math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z)))
            if math.hypot(end.position.x-target[0],end.position.y-target[1])>.12 or abs((yaw-target[2]+180)%360-180)>15:raise InvalidCommand('规划终点与候选接近点不匹配。')
            start=self.node.pose();first=poses[0].pose.position
            if math.hypot(start[0]-first.x,start[1]-first.y)>.3:raise InvalidCommand('规划期间机器人位置变化，请重新请求。')
            self.fetch_map(job,True)
        except Exception:self.fail(job,'规划结果无效或处理异常，未发送导航。')

    def commit(self,job):
        if not self.current(job):return
        n=self.node;target=job['selected'];self.job=None;n.busy=False
        self.watch=job['model']
        n.emit(f"已选临时接近点：{job['name']}，x={target[0]:.2f}，y={target[1]:.2f}，朝向={target[2]:.1f}度；保护轮廓前缘与物体边界期望间距{job['clearance']:.2f}米。",'APPROACH_READY',job['request'],temporary_target=target,object_name=job['model']['name'])
        try:n.command({'action':'route','targets':[{'pose':target}]},'')
        except (ValueError,OSError)as error:self.watch=None;n.emit(str(error),'REJECTED')

    def fail(self,job,message):
        if not self.current(job):return
        handle=job.get('handle');self.job=None;self.node.busy=False
        if handle:handle.cancel_goal_async()
        self.node.emit('物体接近任务未启动：'+message,'REJECTED',job['request'])

    def cancel(self):
        job=self.job;self.job=None;self.watch=None
        if job and job.get('handle'):job['handle'].cancel_goal_async()

    def tick(self):
        job=self.job
        if job and self.current(job):
            now=time.monotonic()
            if now>job['deadline']or(job['plan_deadline']and now>job['plan_deadline']):
                self.fail(job,'候选规划验证超时；迟到结果不会启动运动。')
        if self.watch:
            if not self.node.busy:self.watch=None
            elif not same_object(self.watch,self.object_now(self.watch['name'])):
                self.node.stop('接近对象已移动、消失或实时位置失效，已取消本次临时导航。',agent_failure=True)
