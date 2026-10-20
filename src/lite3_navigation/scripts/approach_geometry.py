"""Conservative flat-ground approach geometry; no model-generated coordinates."""
import math
import re
import xml.etree.ElementTree as ET
from interaction_core import InvalidCommand

SIDES=('any','north','south','east','west')


def validate_approach(c):
    if set(c)-{'action','object','side','clearance'} or c.get('action')!='approach' or 'object'not in c:
        raise InvalidCommand('物体接近任务字段不合法。')
    name=c['object']
    if not isinstance(name,str) or not 0<len(name)<=160 or any(ord(x)<32 for x in name):raise InvalidCommand('物体名称不合法。')
    if c.get('side','any')not in SIDES:raise InvalidCommand('方位仅支持任意侧或地图东南西北。')
    distance=c.get('clearance',.4)
    if type(distance)not in (float,int) or not math.isfinite(distance) or not .15<=distance<=1.5:
        raise InvalidCommand('期望机身与物体边缘间距需为0.15～1.5米。')
    return c


def parse_approach(value):
    value=value.strip().rstrip('。!！?？')
    match=re.fullmatch(r'(?:去|到|前往|导航到)(.+?)(旁边|附近|东侧|西侧|南侧|北侧)(?:\s+距离=([0-9.]+))?',value)
    if not match:return None
    sides={'旁边':'any','附近':'any','东侧':'east','西侧':'west','南侧':'south','北侧':'north'}
    c={'action':'approach','object':match[1].strip(),'side':sides[match[2]]}
    if match[3]:c['clearance']=float(match[3])
    return validate_approach(c)


def pose2(element):
    if element is None:return 0.,0.,0.
    if element.attrib:raise InvalidCommand('当前接近点计算不支持带相对坐标/特殊角度格式的碰撞位姿。')
    try:p=[float(x)for x in element.text.split()]
    except (ValueError,AttributeError):raise InvalidCommand('碰撞位姿格式错误。')from None
    if len(p)!=6 or not all(math.isfinite(x)for x in p) or abs(p[3])+abs(p[4])>1e-6:
        raise InvalidCommand('当前只支持平地、无俯仰横滚的固定物体几何。')
    return p[0],p[1],p[5]


def transform(p,frame):
    x,y,a=frame;c=math.cos(a);s=math.sin(a)
    return x+c*p[0]-s*p[1],y+s*p[0]+c*p[1]


def collision_bounds(world_file,name):
    """Use known SDF collision bodies, never visual bounding boxes or guessed size.
    First version supports rigid static top-level models with primitive geometry.
    Runtime-created / articulated / mesh geometry is explicitly unsupported.
    """
    world=ET.parse(world_file).getroot().find('world')
    matches=[m for m in world.findall('model')if m.get('name')==name]
    if len(matches)!=1:raise InvalidCommand('该对象没有已知场景碰撞几何；本版先支持原场景固定货架等物体。')
    model=matches[0]
    if model.findtext('static','false').strip().lower()not in ('true','1') or model.find('joint')is not None or model.find('model')is not None:
        raise InvalidCommand('本版物体接近暂只支持原场景中的固定刚性物体。')
    pose2(model.find('pose'));points=[]
    for link in model.findall('link'):
        frame=pose2(link.find('pose'))
        for collision in link.findall('collision'):
            cf=pose2(collision.find('pose'));g=collision.find('geometry')
            try:
                if g is None:raise ValueError()
                if g.find('box')is not None:
                    size=[float(x)for x in g.findtext('box/size','').split()]
                    if len(size)!=3 or any(not math.isfinite(x)or x<=0 for x in size):raise ValueError()
                    hx,hy=size[0]/2,size[1]/2
                elif any(g.find(kind)is not None for kind in ('cylinder','sphere','cone')):
                    kind=next(kind for kind in ('cylinder','sphere','cone')if g.find(kind)is not None)
                    radius=float(g.findtext(kind+'/radius'))
                    if kind!='sphere':
                        length=float(g.findtext(kind+'/length'))
                        if not math.isfinite(length)or length<=0:raise ValueError()
                    if not math.isfinite(radius)or radius<=0:raise ValueError()
                    hx=hy=radius
                else:raise InvalidCommand('当前碰撞几何含网格/未知形状，暂不自动计算接近点。')
            except (ValueError,TypeError):raise InvalidCommand('物体碰撞尺寸无效。')from None
            points.extend(transform(transform((x,y),cf),frame)for x in (-hx,hx)for y in (-hy,hy))
    if not points:raise InvalidCommand('该对象没有可用的碰撞体。')
    return min(p[0]for p in points),max(p[0]for p in points),min(p[1]for p in points),max(p[1]for p in points)


def candidates(bounds,world_pose,robot,clearance=.4,side='any',start=(0,0)):
    lo,hi,bottom,top=bounds;hx,hy=robot
    if hi<=lo or top<=bottom or not .05<hx<2 or not .05<hy<2:raise InvalidCommand('物体或机器人轮廓尺寸无效。')
    angle=math.radians(world_pose[3]);frame=(world_pose[0],world_pose[1],angle)
    directions={'north':(0,1),'south':(0,-1),'east':(1,0),'west':(-1,0)}
    result=[]
    for normal,bound,tangent in [((1,0),hi,(bottom,top)),((-1,0),lo,(bottom,top)),((0,1),top,(lo,hi)),((0,-1),bottom,(lo,hi))]:
        nx,ny=normal;c=math.cos(angle);s=math.sin(angle);wx=c*nx-s*ny;wy=s*nx+c*ny
        if side!='any' and wx*directions[side][0]+wy*directions[side][1]<.707-1e-6:continue
        for fraction in (.5,.25,.75):
            t=tangent[0]+fraction*(tangent[1]-tangent[0])
            # Facing normal to the object side: front extent hx plus desired body-edge gap.
            offset=hx+clearance+.05  # 5cm numerical/discretization margin, not saved as a waypoint.
            p=(bound+nx*offset,t)if nx else(t,bound+ny*offset)
            x,y=transform(p,frame);yaw=math.degrees(math.atan2(-wy,-wx))
            if math.hypot(x-start[0],y-start[1])>30:continue
            result.append([x,y,yaw])
    return sorted(result,key=lambda p:math.hypot(p[0]-start[0],p[1]-start[1]))


def polygons_intersect(a,b):
    for poly in (a,b):
        for i,p in enumerate(poly):
            q=poly[(i+1)%len(poly)];nx,ny=-(q[1]-p[1]),q[0]-p[0]
            pa=[x*nx+y*ny for x,y in a];pb=[x*nx+y*ny for x,y in b]
            if max(pa)<min(pb)-1e-10 or max(pb)<min(pa)-1e-10:return False
    return True


class Grid:
    def __init__(self,width,height,resolution,origin,data):
        if not 0<width*height<=4000000 or len(data)!=width*height or not .01<=resolution<=.2:
            raise InvalidCommand('全局障碍地图尺寸/分辨率无效。')
        self.width=width;self.height=height;self.res=resolution;self.origin=origin;self.data=data

    def clear(self,pose,robot):
        x,y,yaw=pose;hx,hy=robot;r=self.res;ox,oy=self.origin
        polygon=[transform(p,(x,y,math.radians(yaw)))for p in [(-hx,-hy),(hx,-hy),(hx,hy),(-hx,hy)]]
        left=math.floor((min(p[0]for p in polygon)-ox)/r);right=math.floor((max(p[0]for p in polygon)-ox)/r)
        bottom=math.floor((min(p[1]for p in polygon)-oy)/r);top=math.floor((max(p[1]for p in polygon)-oy)/r)
        if left<0 or bottom<0 or right>=self.width or top>=self.height:return False
        cx=int((x-ox)/r);cy=int((y-oy)/r)
        if self.data[cy*self.width+cx]>=253:return False
        for row in range(bottom,top+1):
            for col in range(left,right+1):
                if self.data[row*self.width+col]<254:continue
                px=ox+col*r;py=oy+row*r
                square=[(px,py),(px+r,py),(px+r,py+r),(px,py+r)]
                if polygons_intersect(polygon,square):return False
        return True


def same_object(old,new):
    if new is None or old['entity_id']!=new['entity_id'] or new.get('level')is not True:return False
    a=old['pose'];b=new['pose']
    return math.dist(a[:3],b[:3])<=.03 and abs((a[3]-b[3]+180)%360-180)<=2.
