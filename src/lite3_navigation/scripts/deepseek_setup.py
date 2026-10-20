#!/usr/bin/env python3
"""User-run hidden-input setup; never puts API keys in shell history or Git."""
import getpass
import json
import os
import sys
import tempfile
from deepseek_parser import CONFIG,MODEL


def main():
    if not sys.stdin.isatty():
        print('请在你自己的交互终端运行，以便隐藏输入密钥。');return 1
    path=CONFIG
    print('仅保存本机配置，不发起网络请求。文件：'+str(path))
    if path.exists() and input('配置已存在，更新它？输入 yes 确认：').strip()!='yes':
        print('保持原配置。');return 0
    key=getpass.getpass('粘贴DeepSeek API Key（不显示字符），然后回车：').strip()
    if not key or any(c.isspace()for c in key) or not key.isascii():
        print('密钥不能为空，且不能包含空白或非ASCII字符。');return 1
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.deepseek-',dir=path.parent)
    try:
        with os.fdopen(fd,'w')as f:
            os.fchmod(f.fileno(),0o600)
            json.dump({'api_key':key,'model':MODEL},f);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    print('已保存，文件权限600。没有验证API可用性。')
    print('下一步：python3 /home/ma/lite3_ws/src/lite3_navigation/scripts/deepseek_preview.py')
    return 0


if __name__=='__main__':sys.exit(main())
