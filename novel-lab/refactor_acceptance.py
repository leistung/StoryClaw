"""Run all regression/capacity/rolling-workflow checks in an isolated PostgreSQL database.

DATABASE_URL must name storyclaw_refactor_test. No model/network inference is used.
The database must exist; this script never creates/deletes production data.
"""
import os,sys,subprocess,argparse
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--pattern',default='test*.py');args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
url=os.environ.get('DATABASE_URL','')
if not url.endswith('/storyclaw_refactor_test'):
    sys.exit('Set DATABASE_URL to an isolated PostgreSQL database named storyclaw_refactor_test.')
env={**os.environ,'PYTHONPATH':os.pathsep.join([str(root/'backend'),str(root/'packages/storyclaw/src')])}
sys.exit(subprocess.call([sys.executable,'-m','unittest','discover','-s',str(root/'backend/tests'),'-p',args.pattern,'-v'],cwd=root,env=env))
