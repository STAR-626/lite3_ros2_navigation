"""Native function-call capabilities; backend functions, never shell strings."""
from deepseek_parser import validate, DeepSeekError, strict_json
from interaction_core import place_name, InvalidCommand
from environment_catalog import CATEGORIES


def schema(properties=None,required=()):
    return {'type':'object','properties':properties or {},'required':list(required),'additionalProperties':False}

STR={'type':'string'}
POSE={'type':'array','items':{'type':['number','null']},'minItems':3,'maxItems':3}
SPECS={
 'get_environment':('读取Gazebo真值环境目录，可按类别/物体或地点筛选。包含真实ID、名称、别名、类别、当前存在状态和位置。+X东/+Y北；结合名称含义、位置和上下文自行识别用户对象，不要求用户使用原名或预设别名。',schema({'category':{'type':'string','enum':list(CATEGORIES)},'kind':{'type':'string','enum':['model','place']}})),
 'get_object':('查询一个真实物体/地点的详细信息，object优先用目录ID。模型原点不是导航站立点。',schema({'object':STR},['object'])),
 'get_robot_state':('查询当前导航开关、任务状态、机器人map位置、启动原点、本轮任务出发位置。',schema()),
 'list_places':('查询所有用户持久保存的地点及坐标；与环境物体不同。',schema()),
 'approach_object':('前往一个已知固定物体旁的临时安全位置；本机读取碰撞几何、costmap并规划，不存为长期地点。等待真实到达/失败结果后才能进行下一步。支持原场景固定货架和墙体，暂不支持运行时新增/动态/mesh。',schema({'object':STR,'side':{'type':'string','enum':['any','north','south','east','west']},'clearance':{'type':'number','minimum':.15,'maximum':1.5}},['object'])),
 'navigate_to':('前往一个已保存地点或用户明确给出的绝对坐标。name和pose必须只提供一个。pose为[x米,y米,yaw度或null]。不能用物体中心代替接近位置。',schema({'name':STR,'pose':POSE})),
 'return_to_start':('回到本轮用户任务开始时的位置，不是地图零点，不持久保存。',schema()),
 'return_home':('回本次启动记录的原点（家），不是地图零点。',schema()),
 'save_place':('仅按用户明确要求保存地点。name必填，current=true或pose二选一；同名覆盖需要用户在本地明确确认，模型不能代替确认。',schema({'name':STR,'current':{'type':'boolean'},'pose':POSE},['name'])),
 'delete_places':('仅按用户明确要求删除持久地点。names列表或all=true二选一；支持全部删除。家不属于持久地点。先查询真实地点，不猜名称。',schema({'names':{'type':'array','items':STR,'minItems':1,'maxItems':64},'all':{'type':'boolean'}})),
 'annotate_object':('仅按用户要求修改真实物体或地点的名称/类别/别名/用途；object必填，至少一个元数据字段。不改变Gazebo几何或坐标。',schema({'object':STR,'name':STR,'category':{'type':'string','enum':list(CATEGORIES)},'aliases':{'type':'array','items':STR},'description':STR},['object'])),
 'stop_task':('关闭导航并停止/取消任务。停止始终可由用户本地直接触发，无需模型。',schema()),
}
TOOLS=[{'type':'function','function':{'name':name,'description':description,'parameters':parameters}}for name,(description,parameters)in SPECS.items()]


def validate_call(name,args):
    if name not in SPECS or not isinstance(args,dict):raise DeepSeekError('工具不存在或参数不是对象。')
    spec=SPECS[name][1]
    if set(args)-set(spec['properties'])or set(spec['required'])-set(args):raise DeepSeekError('工具字段缺失或有未允许字段。')
    if name=='approach_object':validate({'action':'approach',**args})
    elif name in ('get_object','annotate_object'):
        validate({'action':'env_show'if name=='get_object'else'env_label',**args})
    elif name=='get_environment':
        validate({'action':'env_list',**({'category':args['category']}if'category'in args else{})})
        if args.get('kind','model')not in ('model','place'):raise DeepSeekError('环境对象类型不合法。')
    elif name=='navigate_to':
        if len(args)!=1:raise DeepSeekError('导航目标需要且仅有name或pose。')
        validate({'action':'route','targets':[args]})
    elif name=='save_place':validate({'action':'save',**args})
    elif name=='delete_places':
        if set(args)=={'all'}:
            if args['all']is not True:raise DeepSeekError('all只允许true。')
        elif set(args)=={'names'}:
            values=args['names']
            if not isinstance(values,list)or not 1<=len(values)<=64:raise DeepSeekError('删除名称数量不合法。')
            try:
                for value in values:
                    if not isinstance(value,str):raise InvalidCommand('名称不是字符串')
                    place_name(value)
                if len(set(values))!=len(values):raise InvalidCommand('名称重复')
            except (ValueError,TypeError):raise DeepSeekError('删除地点名称不合法。')from None
        else:raise DeepSeekError('删除需要names或all二选一。')
    return args


def parse_message(message,finish):
    if not isinstance(message,dict):raise DeepSeekError('模型消息格式错误。')
    content=message.get('content')or''
    if not isinstance(content,str)or len(content)>4000:raise DeepSeekError('模型文字格式或长度错误。')
    calls=message.get('tool_calls')or[]
    if not isinstance(calls,list)or len(calls)>8:raise DeepSeekError('单轮工具调用数量超过8。')
    if finish not in ('stop','tool_calls')or(finish=='tool_calls'and not calls):raise DeepSeekError('模型输出未正常完成。')
    result={'role':'assistant','content':content};clean=[];ids=set()
    for call in calls:
        try:
            ident=call['id'];fn=call['function'];name=fn['name'];raw=fn['arguments']
            if call.get('type')!='function' or not isinstance(ident,str)or not 0<len(ident)<=128 or any(ord(c)<32 for c in ident)or ident in ids:raise ValueError()
            if not isinstance(raw,str)or len(raw)>8192:raise ValueError()
            args=strict_json(raw);validate_call(name,args);ids.add(ident)
            clean.append({'id':ident,'type':'function','function':{'name':name,'arguments':raw}})
        except (KeyError,TypeError,ValueError)as error:raise DeepSeekError('工具调用不合法：'+str(error))from None
    if clean:result['tool_calls']=clean
    elif not content.strip():raise DeepSeekError('模型既未回复也未选择工具。')
    return result
