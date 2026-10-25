#!/usr/bin/env python3
"""Run deterministic tests; database integration requires an explicitly isolated database."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / 'backend'
HARNESS = BACKEND / 'packages/harness'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', choices=['offline', 'integration', 'all'], default='offline')
    parser.add_argument('--pattern', default='test*.py')
    args = parser.parse_args()
    if args.suite != 'offline' and not os.environ.get('DATABASE_URL', '').endswith('/storyclaw_refactor_test'):
        parser.error('DATABASE_URL must point to an isolated database named storyclaw_refactor_test; production is forbidden.')
    env = {**os.environ, 'PYTHONPATH': os.pathsep.join([str(BACKEND), str(HARNESS)])}
    groups = []
    if args.suite in ('offline', 'all'):
        groups.extend([('harness', HARNESS / 'tests', None), ('application-unit', BACKEND / 'tests/unit', BACKEND)])
    if args.suite in ('integration', 'all'):
        groups.extend([('application-integration', BACKEND / 'tests/integration', BACKEND), ('end-to-end', BACKEND / 'tests/e2e', BACKEND)])
    count = 0
    for name, start, top in groups:
        print(f'\n[{name}]', flush=True)
        cmd = [sys.executable, '-m', 'unittest', 'discover', '-s', str(start), '-p', args.pattern, '-v']
        if top:
            cmd.extend(['-t', str(top)])
        result = subprocess.run(cmd, cwd=ROOT, env=env)
        if result.returncode:
            return result.returncode
        count += 1
    print(f'\nPassed {count} test suites. No paid model calls.', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
