#!/usr/bin/env python3
"""在后台启动可恢复的长篇生成，凭据仅通过进程环境传递。"""
import argparse
import fcntl
import getpass
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--through',type=int,default=40)
p.add_argument('--max-credits',type=int,default=4000)
p.add_argument('--output',type=Path,default=ROOT/'runs/borrowed-fire-v1')
a=p.parse_args();a.output=a.output.resolve();a.output.mkdir(parents=True,exist_ok=True)
lock=(a.output/'.launch.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX)
job_path=a.output/'job.json'
if job_path.exists():
    previous=json.loads(job_path.read_text())
    try:os.kill(previous['pid'],0)
    except ProcessLookupError:pass
    else:raise SystemExit(f"已有后台进程 PID {previous['pid']}，请先查看 status.py，避免重复运行")
env=os.environ.copy();env['STORYCLAW_PASSWORD']=env.get('STORYCLAW_PASSWORD') or getpass.getpass('StoryClaw 密码: ')
log_path=a.output/'worker.log'
with log_path.open('a') as log:
    process=subprocess.Popen([sys.executable,str(ROOT/'run.py'),'--phase','write','--through',str(a.through),'--max-credits',str(a.max_credits),'--output',str(a.output)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,env=env,start_new_session=True)
job={'pid':process.pid,'started_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'through':a.through,'log':str(log_path)}
job_path.write_text(json.dumps(job,ensure_ascii=False,indent=2));print(json.dumps(job,ensure_ascii=False,indent=2))
