#!/usr/bin/env python3
"""Standalone DeepSeek preview: no ROS connection and no execution path."""
import json
from pathlib import Path
from deepseek_parser import interpret, DeepSeekError
from language_context import ClarificationContext,normalize_names
from interaction_core import parse,InvalidCommand,place_name


def saved_names():
    p=Path.home()/'.local/share/lite3_navigation/places.json'
    if not p.exists():return []
    try:
        points=json.loads(p.read_text())['points']
        if not isinstance(points,dict)or len(points)>64:raise ValueError()
        for name in points:place_name(name)
        return list(points)
    except (ValueError,KeyError,TypeError,OSError):raise DeepSeekError('地点文件格式不合法，未发送其内容。')from None


def main():
    print('DeepSeek只解析预览：不连接ROS，不执行任务。输入exit退出。')
    print('每条非停止输入会向DeepSeek发送该句话和已保存地点名称，产生API调用。')
    dialogue=ClarificationContext()
    while True:
        try:
            text=input('你：').strip()
            if text.lower() in ('exit','quit','退出'):return
            if not text:continue
            try:local=parse(text)
            except InvalidCommand:local=None
            if local and local['action']=='stop':
                dialogue.clear();print('本地识别：停止（预览模式未执行，也没有调用API）。');continue
            names=saved_names();result=normalize_names(interpret(text,names,history=dialogue.messages()),names)
            if result['action']=='clarify':dialogue.remember(text,result['message'])
            else:dialogue.clear()
            print('DeepSeek解析结果（未执行）：\n'+json.dumps(result,ensure_ascii=False,indent=2))
            if result['action']=='route':
                missing=[t['name']for t in result['targets']if 'name'in t and t['name']not in names]
                if missing:print('本地检查：以下地点尚未保存，实际执行时应拒绝整组任务：'+','.join(missing))
        except DeepSeekError as error:dialogue.clear();print('未执行：'+str(error))
        except (KeyboardInterrupt,EOFError):print('\n已退出预览。');return


if __name__=='__main__':main()
