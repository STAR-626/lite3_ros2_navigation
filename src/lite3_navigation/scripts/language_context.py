"""Short-lived clarification memory and conservative saved-place aliases."""
from collections import deque
import copy
import json
import re
import time
from interaction_core import number,InvalidCommand


class ClarificationContext:
    def __init__(self,clock=time.monotonic):
        self.clock=clock;self.turns=deque(maxlen=3);self.updated=0.

    def clear(self):self.turns.clear();self.updated=0.

    def messages(self):
        if self.clock()-self.updated>90:self.clear()
        result=[]
        for text,question in self.turns:
            result.extend([{'role':'user','content':text},
                {'role':'assistant','content':json.dumps({'action':'clarify','message':question},ensure_ascii=False)}])
        return result

    def remember(self,text,question):
        self.turns.append((text,question));self.updated=self.clock()


def normalize_names(value,names):
    """Exact names win. Only reference aliases; never silently rename a new save."""
    value=copy.deepcopy(value);names=set(names)
    def alias(name):
        if name in names:return name
        match=re.fullmatch(r'(?:点)?([0-9]{1,3}|[零一二三四五六七八九十百两〇]{1,6})',name)
        if not match:return name
        try:target='点'+str(int(number(match[1])))
        except (InvalidCommand,ValueError):return name
        return target if target in names else name
    if value['action'] in ('show','delete'):value['name']=alias(value['name'])
    if value['action']=='route':
        for target in value['targets']:
            if 'name'in target:target['name']=alias(target['name'])
    return value


def describe(value):
    action=value['action']
    def point(p):
        angle='，朝向保持当前值'if p[2]is None else f'，朝向{p[2]:g}度'
        return f'坐标({p[0]:g}, {p[1]:g})'+angle
    if action=='approach':return '前往物体“'+value['object']+'”旁的临时安全位置'
    if action=='env_list':return '列出环境'+('，类别为'+value['category'] if 'category' in value else '')
    if action=='env_show':return '查询环境对象“'+value['object']+'”'
    if action=='env_label':return '更新环境对象“'+value['object']+'”的语义标注'
    if action=='route':
        return '依次前往：'+' → '.join(t.get('name')or('原点'if t.get('home')else point(t['pose']))for t in value['targets'])
    if action=='save':return ('把当前位置'if value.get('current')else'把'+point(value['pose']))+'保存为“'+value['name']+'”'
    if action in ('show','delete'):return ('查询'if action=='show'else'删除')+'地点“'+value['name']+'”'
    return {'enable':'开启导航入口','stop':'停止并取消任务','state':'查询运行状态','help':'查看帮助','list':'列出地点'}.get(action,'处理请求')


def navigation_problem(state):
    fields=('navigation_enabled','busy','fault_latched','switch_pending')
    if not isinstance(state,dict) or any(type(state.get(k))is not bool for k in fields):
        raise ValueError('导航状态格式错误')
    if state['fault_latched']:return '系统仍有故障锁定，请先检查启动终端中的具体故障'
    if state['switch_pending']:return '导航开关或停止操作尚未完成，请稍候再试'
    if state['busy']:return '机器狗已有其他任务正在执行，请等待或先输入“停止”'
    if not state['navigation_enabled']:return '导航总开关当前关闭。请先输入“开启导航”，看到开启成功后再重新发送目标'
    return None
