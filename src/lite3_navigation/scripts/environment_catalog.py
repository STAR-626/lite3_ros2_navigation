"""Map/world-bound semantic annotations. Gazebo truth, not sensor recognition.
Only annotations are durable. Live existence and model-centre poses are never
navigation goals; saved-place coordinates remain owned by the original Places.
"""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import tempfile
import xml.etree.ElementTree as ET
from interaction_core import InvalidCommand

CATEGORIES = ('未分类', '货架', '箱子', '墙体', '检查点', '入口', '等待区', '充电区', '普通地点')


def text(value, limit=80):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or any(ord(c) < 32 for c in value):
        raise InvalidCommand('名称/语义字段为空、过长或含控制字符。')
    return value.strip()


def validate_command(c):
    action = c.get('action')
    if action == 'env_list':
        if set(c) - {'action', 'category'}:raise InvalidCommand('环境查询字段不合法。')
        if 'category' in c and c['category'] not in CATEGORIES:raise InvalidCommand('未知类别。')
    elif action == 'env_show':
        if set(c) != {'action', 'object'}:raise InvalidCommand('需指定物体或地点。')
        text(c['object'], 160)
    elif action == 'env_label':
        if set(c) - {'action', 'object', 'name', 'category', 'aliases', 'description'} or len(c) < 3:
            raise InvalidCommand('标注字段不合法。')
        text(c.get('object'), 160)
        if 'name' in c:text(c['name'], 40)
        if 'category' in c and c['category'] not in CATEGORIES:raise InvalidCommand('未知类别。')
        if 'description' in c:
            if c['description'] != '':text(c['description'], 200)
        if 'aliases' in c:
            a = c['aliases']
            if not isinstance(a, list) or len(a) > 8 or len(set(map(str, a))) != len(a):raise InvalidCommand('别名最多8个，不能重复。')
            for item in a:text(item, 40)
    else:raise InvalidCommand('未知环境操作。')
    return c


def parse_environment(value):
    """Explicit local controls are available in both language modes, no API."""
    value = value.strip().rstrip('。!！?？')
    if value in ('列出环境', '环境物体', '有哪些物体', '查询环境'):
        return {'action': 'env_list'}
    match = re.fullmatch(r'列出类别\s+(.+)', value)
    if match:return validate_command({'action':'env_list', 'category':match[1]})
    match = re.fullmatch(r'(?:查询物体|查询地点语义)\s+(.+)', value)
    if match:return validate_command({'action':'env_show', 'object':match[1]})
    if value.startswith(('标注物体 ', '标注地点 ')):
        parts = shlex.split(value)
        if len(parts) < 3:raise InvalidCommand('示例：标注物体 shelf_1 名称=货架A 类别=货架 别名=一号货架 用途=到点巡检')
        prefix = 'model:' if parts[0] == '标注物体' else 'place:'
        c = {'action':'env_label', 'object':prefix+parts[1]}
        fields = {'名称':'name', '类别':'category', '别名':'aliases', '用途':'description'}
        for part in parts[2:]:
            key, sep, val = part.partition('=')
            if not sep or key not in fields or fields[key] in c:raise InvalidCommand('标注请使用名称=、类别=、别名=、用途=，字段不能重复。')
            c[fields[key]] = [x for x in re.split('[,，]', val) if x] if key == '别名' else val
        return validate_command(c)
    return None


def visible(name):
    return (name not in ('ground_plane', 'concrete_floor', 'Lite3', 'lite3') and
            not name.startswith(('spawn_marker', 'destination_marker', 'lite3_places', 'lite3_goal')))


def category(name, kind):
    if kind == 'place':return '普通地点'
    if name.startswith('shelf_'):return '货架'
    if name.startswith('wall_'):return '墙体'
    if 'box' in name.lower():return '箱子'
    return '未分类'


def shelf_labels(name):
    match=re.fullmatch(r'shelf_([1-9][0-9]?)',name)
    if not match:return {}
    n=int(match[1]);digits='零一二三四五六七八九'
    chinese=digits[n] if n<10 else (digits[n//10] if n>=20 else '')+'十'+(digits[n%10] if n%10 else '')
    return {'name':'货架'+str(n),'aliases':[str(n)+'号货架',chinese+'号货架','货架'+chinese,'第'+str(n)+'号货架']}


class EnvironmentCatalog:
    def __init__(self, world_file, map_key, path=None):
        self.world_file = Path(world_file)
        content = self.world_file.read_bytes()
        self.world_digest=hashlib.sha256(content).hexdigest()
        world = ET.fromstring(content).find('world')
        if world is None or not re.fullmatch('[A-Za-z0-9_-]{1,80}', world.get('name', '')):
            raise InvalidCommand('语义目录需要有效的Gazebo world名称。')
        self.world = world.get('name')
        self.key = hashlib.sha256(map_key.encode()+content).hexdigest()
        self.path = Path(path) if path else Path.home()/'.local/share/lite3_navigation'/('environment_'+self.key[:16]+'.json')
        self.seeds = {m.get('name') for m in world.findall('model') if m.get('name') and visible(m.get('name'))}
        self.annotations = {}
        if self.path.exists():
            if self.path.stat().st_size > 262144:raise InvalidCommand('语义文件过大。')
            raw = json.loads(self.path.read_text())
            if not isinstance(raw, dict) or raw.get('version') != 1 or raw.get('environment_key') != self.key:
                raise InvalidCommand('语义文件与地图/场景不匹配；旧文件未覆盖，请更换environment_file。')
            data = raw.get('annotations')
            if not isinstance(data, dict) or len(data) > 320:raise InvalidCommand('语义标注格式或数量错误。')
            for ident, fields in data.items():
                text(ident, 160)
                if not ident.startswith(('model:', 'place:')) or not isinstance(fields, dict) or not fields or set(fields)-{'name','category','aliases','description'}:
                    raise InvalidCommand('语义标注对象不合法。')
                validate_command({'action':'env_label', 'object':ident, **fields})
            self.annotations = data

    def records(self, points, snapshot=None):
        live = {} if snapshot is None else {m['name']:m for m in snapshot['models'] if visible(m['name'])}
        models = self.seeds | set(live) | {k[6:] for k in self.annotations if k.startswith('model:')}
        records = []
        for kind, names in [('model', models), ('place', points)]:
            for name in sorted(names):
                ident = kind+':'+name; labels = self.annotations.get(ident, {})
                defaults=shelf_labels(name) if kind=='model' else {}
                display=labels.get('name',defaults.get('name',name))
                aliases=list(dict.fromkeys(labels.get('aliases',[])+defaults.get('aliases',[])+([defaults['name']] if defaults and defaults['name']!=display else [])))
                record = {'id':ident, 'source_name':name, 'kind':kind, 'name':display,
                          'category':labels.get('category', category(name, kind)), 'aliases':aliases,
                          'description':labels.get('description', ''), 'classification_source':'user' if 'category' in labels else 'name_rule',
                          'present':True if kind == 'place' else (name in live if snapshot is not None else None),
                          'navigable':kind == 'place'}
                if kind == 'place':record['pose_map'] = list(points[name])
                elif name in live:
                    # Current project map == Gazebo world; z is model origin, not a foot target.
                    record['pose_world'] = list(live[name]['pose']);record['entity_id'] = live[name]['entity_id']
                records.append(record)
        return records

    def resolve(self, query, points, snapshot=None):
        records = self.records(points, snapshot)
        exact = [r for r in records if query == r['id']]
        if exact:return exact[0]
        matches = [r for r in records if query in [r['name'], r['source_name'], *r['aliases']]]
        if len(matches) != 1:
            raise InvalidCommand('未找到该对象。' if not matches else '名称有歧义，请使用model:模型名或place:点名。')
        return matches[0]

    def label(self, query, fields, points, snapshot=None):
        validate_command({'action':'env_label', 'object':query, **fields})
        record = self.resolve(query, points, snapshot)
        if record['kind'] == 'model' and record['present'] is not True:
            raise InvalidCommand('物体尚未由当前Gazebo场景确认存在，暂不能修改标注。')
        updated = copy.deepcopy(self.annotations)
        updated[record['id']] = {**updated.get(record['id'], {}), **fields}
        if len(updated) > 320:raise InvalidCommand('语义标注数量超过320。')
        self.persist_annotations(updated)
        return self.resolve(record['id'], points, snapshot)

    def persist_annotations(self, updated):
        if len(updated)>320:raise InvalidCommand('语义标注数量超过320。')
        for ident, fields in updated.items():
            validate_command({'action':'env_label','object':ident,**fields})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.environment-', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump({'version':1, 'environment_key':self.key, 'annotations':updated}, f, ensure_ascii=False, indent=2)
                f.flush();os.fsync(f.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):os.unlink(temporary)
        self.annotations = updated

    def number_shelves(self):
        """Explicit setup for SDF-defined shelf numbering; never invent live poses."""
        updated=copy.deepcopy(self.annotations);mapped={name:shelf_labels(name)for name in self.seeds if shelf_labels(name)}
        reserved={alias:name for name,d in mapped.items()for alias in [d['name'],*d['aliases']]}
        for name,defaults in mapped.items():
            ident='model:'+name;old=updated.get(ident,{})
            extra=([old['name']] if old.get('name') and old['name']!=defaults['name'] else [])+old.get('aliases',[])
            aliases=list(dict.fromkeys(defaults['aliases']+[x for x in extra if reserved.get(x,name)==name and x!=defaults['name']]))[:8]
            updated[ident]={**old,'name':defaults['name'],'aliases':aliases}
        self.persist_annotations(updated)
        return sorted(mapped,key=lambda name:int(name.split('_')[-1]))

    def place_reference(self, name, points, snapshot=None):
        # Existing exact saved-point names retain their original meaning.
        if name in points:return name
        try:r = self.resolve(name, points, snapshot)
        except InvalidCommand:
            matches = [r for r in self.records(points, snapshot) if name in [r['name'], r['source_name'], *r['aliases']]]
            if matches:raise
            return name
        if r['kind'] != 'place':
            raise InvalidCommand('该名称对应环境物体，尚未配置安全接近点；不能导航到物体中心。请先另存可站立地点。')
        return r['source_name']

    def context(self, points, snapshot=None):
        # Do not upload arbitrary runtime coordinates: models answer env_show via local lookup.
        records = self.records(points, snapshot)
        return {'source':'gazebo_truth_and_user_annotations', 'live_scene_available':snapshot is not None,
                'objects':[{k:r[k] for k in ('id','source_name','kind','name','category','aliases','description','present','navigable')}
                           for r in records]}
