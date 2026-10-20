#!/usr/bin/env python3
"""Interactive console with wall-time lease; parsing mode is chosen by backend."""
import json
import os
import select
import sys
import time
import uuid
import rclpy
from rclpy.node import Node
from rclpy.signals import SignalHandlerOptions
from std_msgs.msg import String


def main():
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO);node=Node('lite3_ai_console_'+uuid.uuid4().hex[:8]);session=str(uuid.uuid4())
    pub=node.create_publisher(String,'/lite3/interaction/input',20)
    state={'connected':False,'stopped':False,'fatal':False,'last_event':time.monotonic(),'prompted':set()}
    def receive(msg):
        try:p=json.loads(msg.data)
        except ValueError:return
        if p.get('session')!=session:return
        state['last_event']=time.monotonic()
        print('\n系统：'+p.get('message',''),flush=True)
        if p.get('id')=='connect':
            state['connected']=p.get('code')=='OK'
            state['fatal']=not state['connected']
        if p.get('code')=='STOPPED':state['stopped']=True
        if p.get('code') in ('NO_SESSION','DISCONNECTED'):state['fatal']=True
        ident=p.get('id','')
        if state['connected'] and ident and not ident.startswith('tool_') and ident not in state['prompted'] and p.get('code')not in ('PARSING','INTERPRETED','PROGRESS'):
            if len(state['prompted'])>256:state['prompted'].clear()
            state['prompted'].add(ident);print('你：',end='',flush=True)
    node.create_subscription(String,'/lite3/interaction/events',receive,50)
    def send(kind,text='',ident=None):
        pub.publish(String(data=json.dumps({'session':session,'kind':kind,'id':ident or uuid.uuid4().hex,'text':text},ensure_ascii=False)))
    try:
        print('Lite3 自然语言控制入口（连接后显示后台模式）\n正在连接后台……',flush=True)
        deadline=time.monotonic()+8;retry=0
        while not state['connected'] and not state['fatal'] and time.monotonic()<deadline:
            now=time.monotonic()
            if now>retry:send('connect',ident='connect');retry=now+.5
            rclpy.spin_once(node,timeout_sec=.05)
        if not state['connected']:
            print('未连接。请确认使用 ai_control:=true 启动，并source同一工作空间。');return 1
        beat=0;buffer="";exit_requested=False
        while rclpy.ok() and not state['fatal'] and not exit_requested:
            now=time.monotonic()
            if now>beat:send('heartbeat');beat=now+.4
            rclpy.spin_once(node,timeout_sec=.03)
            if select.select([sys.stdin],[],[],0)[0]:
                chunk=os.read(sys.stdin.fileno(),4096)
                if not chunk:break
                buffer+=chunk.decode('utf-8',errors='replace')
                while '\n' in buffer:
                    line,buffer=buffer.split('\n',1)
                    if line.strip().lower() in ('exit','quit','退出'):
                        exit_requested=True;break
                    if line.strip():send('text',line.strip())
    except KeyboardInterrupt:print('\n正在退出并请求停止……',flush=True)
    finally:
        if state['connected'] and rclpy.ok():
            state['stopped']=False;send('close');deadline=time.monotonic()+8
            while time.monotonic()<deadline and not state['stopped']:
                rclpy.spin_once(node,timeout_sec=.05)
            if not state['stopped']:print('停止响应尚未确认；请查看bringup状态，必要时在启动终端按Ctrl+C。')
        node.destroy_node()
        if rclpy.ok():rclpy.shutdown()
    return 0


if __name__=='__main__':sys.exit(main())
