"""Deterministic, fail-closed interaction protocol; no model or shell execution."""
import json
import math
import os
from pathlib import Path
import re
import tempfile
import unicodedata


class InvalidCommand(ValueError):
    pass


def number(text):
    text = text.strip().replace('负', '-').replace('正', '+')
    if re.fullmatch(r'[+-]?\d+(?:\.\d+)?', text):
        value = float(text)
    else:
        sign = -1 if text.startswith('-') else 1
        text = text.lstrip('+-'); parts = text.split('点')
        digits = '零一二三四五六七八九'
        def integer(s):
            s = s.replace('两', '二').replace('〇', '零')
            if not s or any(c not in digits+'十百' for c in s):
                raise InvalidCommand('数字格式不支持，请使用阿拉伯数字。')
            total = pending = 0
            for c in s:
                if c in '十百':
                    total += (pending or 1) * (10 if c == '十' else 100); pending = 0
                else:
                    pending = pending*10+digits.index(c)
            return total+pending
        if len(parts) > 2:
            raise InvalidCommand('数字格式不合法。')
        value = integer(parts[0])
        if len(parts) == 2:
            if not parts[1] or any(c not in digits for c in parts[1]):
                raise InvalidCommand('小数格式不合法。')
            value += float('0.'+''.join(str(digits.index(c)) for c in parts[1]))
        value *= sign
    if not math.isfinite(value):
        raise InvalidCommand('坐标和角度必须是有限数字。')
    return value


def place_name(name):
    name = name.strip()
    if not re.fullmatch(r'[\w\u4e00-\u9fff-]{1,24}', name) or name in ('原点', '初始位置', '家', '那里', '这里', '前面', '后面', '左边', '右边'):
        raise InvalidCommand('点名限1～24个汉字、字母、数字、下划线或短横线；原点为系统保留名称。')
    return name


def pose_values(text):
    text = re.sub(r'^(?:地图)?坐标', '', text.strip())
    text = re.sub(r'[,，、]?\s*(?:最后)?(?:朝向|角度|方向)\s*', ',', text)
    text = text.replace('度', '').replace('米', '')
    parts = [p for p in re.split(r'[,，、\s]+', text.strip()) if p]
    if len(parts) not in (2, 3):
        raise InvalidCommand('需要x、y两个坐标，朝向可选。例如：去坐标3、2，朝向90度。')
    values = [number(p) for p in parts]
    if len(values) == 3 and abs(values[2]) > 180:
        raise InvalidCommand('朝向范围为-180～180度。')
    return values+[None] if len(values) == 2 else values


def destination(text):
    if text in ('回家', '回到原点', '返回原点', '回到初始位置', '返回初始位置'):
        return {'home': True}
    m = re.fullmatch(r'(?:导航到|前往|去|到)(.+)', text)
    if not m:
        raise InvalidCommand('路线每一步需要“去点名”或“回到原点”。')
    target = m[1].strip()
    if target in ('原点', '初始位置', '家'):
        return {'home': True}
    if target.startswith(('坐标', '地图坐标')):
        return {'pose': pose_values(target)}
    return {'name': place_name(target)}


def parse(text):
    if not isinstance(text, str) or not 0 < len(text) <= 512:
        raise InvalidCommand('请输入1～512字符的指令。')
    text = unicodedata.normalize('NFKC', text).strip().rstrip('。!！?？')
    exact = {
        '开启导航':'enable', '打开导航':'enable', '允许选点导航':'enable',
        '关闭导航':'stop', '停止':'stop', '停下':'stop', '别走了':'stop', '取消导航':'stop',
        '取消这次导航':'stop', '取消任务':'stop', '状态':'state', '查询状态':'state',
        '现在什么状态':'state', '现在是什么状态':'state', '到哪了':'state',
        '帮助':'help', '你能做什么':'help', '有哪些已保存的点':'list',
        '列出地点':'list', '列出点位':'list', '查看所有点':'list',
    }
    if text in exact:
        return {'action': exact[text]}
    m = re.fullmatch(r'确认覆盖(.+)', text)
    if m:return {'action':'confirm', 'name':place_name(m[1])}
    m = re.fullmatch(r'(?:把|将)?(?:机器狗的?)?当前位置(?:设置|设|保存|记)(?:为|成)(.+)', text)
    if m:return {'action':'save', 'name':place_name(m[1]), 'current':True}
    m = re.fullmatch(r'(?:把|将)?((?:地图)?坐标.+?)(?:设置|设|保存)(?:为|成)(.+)', text)
    if m:return {'action':'save', 'name':place_name(m[2]), 'pose':pose_values(m[1])}
    m = re.fullmatch(r'(?:删除|移除)(.+)', text)
    if m:return {'action':'delete', 'name':place_name(m[1])}
    m = re.fullmatch(r'(.+)(?:在哪里|的坐标是什么)', text)
    if m:return {'action':'show', 'name':place_name(m[1])}
    m = re.fullmatch(r'查询(?:地点|点位)?(.+)', text)
    if m:return {'action':'show', 'name':place_name(m[1])}
    text = re.sub(r'^先', '', text)
    steps = [s.strip(' ,，') for s in re.split(r'[,，]?\s*(?:然后|接着|最后|再)\s*', text) if s.strip(' ,，')]
    if not 1 <= len(steps) <= 12:
        raise InvalidCommand('一次允许1～12个导航目标。')
    try:return {'action':'route', 'targets':[destination(s) for s in steps]}
    except InvalidCommand as error:
        if text.startswith(('去坐标', '去地图坐标', '导航到坐标')):raise
        raise InvalidCommand('当前表达不支持或有歧义。输入“帮助”查看规则；不会执行终端命令。') from error


HELP = ('规则模式，未接入大模型。支持：开启导航；关闭导航/停止；查询状态；'
        '把坐标3、2，朝向90度设成点1；把当前位置设成点2；点1在哪里；列出地点；'
        '删除点1；确认覆盖点1；去点1；去坐标3、2；先去点1，再去点2，然后回到原点。'
        '坐标为map米，角度为度；省略朝向取提交时当前朝向。退出输入exit或按Ctrl+C。')


class Places:
    def __init__(self, path, map_key):
        self.path = Path(path).expanduser(); self.map_key = map_key; self.points = {}
        if self.path.exists():
            raw = json.loads(self.path.read_text())
            if raw.get('version') != 1 or raw.get('map_key') != map_key:
                raise InvalidCommand('地点文件版本或地图不匹配，请使用该地图独立的places_file；不会覆盖旧文件。')
            points = raw.get('points')
            if not isinstance(points, dict) or len(points) > 64:
                raise InvalidCommand('地点文件损坏或超过64个地点。')
            for name, pose in points.items():
                place_name(name); self.validate(pose)
            self.points = points

    @staticmethod
    def validate(pose):
        if not isinstance(pose, list) or len(pose) != 3 or any(
            isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) for v in pose
        ) or abs(pose[2]) > 180:
            raise InvalidCommand('地点必须含有效的x、y、角度，角度限-180～180度。')

    def persist(self, points):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.places-', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump({'version':1, 'map_key':self.map_key, 'points':points}, f, ensure_ascii=False, indent=2)
                f.flush();os.fsync(f.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):os.unlink(temporary)
        self.points = points

    def save(self, name, pose):
        place_name(name);self.validate(pose)
        if name not in self.points and len(self.points) >= 64:
            raise InvalidCommand('最多保存64个地点。')
        self.persist(dict(self.points, **{name:list(pose)}))

    def delete(self, name):
        if name not in self.points:raise InvalidCommand('地点不存在：'+name)
        points = dict(self.points);del points[name];self.persist(points)


def resolve(targets, points, home, yaw):
    result = []
    for target in targets:
        if 'home' in target:
            if home is None:raise InvalidCommand('原点尚未记录，等待本次仿真的有效位置。')
            label, pose = '原点', list(home)
        elif 'name' in target:
            label = target['name']
            if label not in points:raise InvalidCommand('尚未设置：'+label+'；整组任务未启动。')
            pose = list(points[label])
        else:
            label, pose = '坐标目标', list(target['pose'])
            if pose[2] is None:pose[2] = yaw
        Places.validate(pose);result.append({'label':label, 'pose':pose})
    return result
