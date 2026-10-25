#!/usr/bin/env python3
"""Check current handbook links, reading order and Git ignore policy without model calls."""
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote

ROOT=Path(__file__).resolve().parents[2]


def main():
    errors=[]
    handbook=sorted((ROOT/'docs').glob('[0-9][0-9]-*.md'))
    numbers=[int(p.name[:2]) for p in handbook]
    if numbers!=list(range(14)):
        errors.append('Handbook must contain exactly one numbered chapter for each number 00–13.')
    other=list((ROOT/'docs').glob('*.md'))
    if set(other)!=set(handbook):
        errors.append('Current docs root contains unnumbered Markdown outside the reading path.')
    entry=[ROOT/'README.md',ROOT/'backend/tests/README.md',ROOT/'backend/scripts/README.md',ROOT/'backend/evaluations/README.md',ROOT/'deploy/README.md']
    files=handbook+entry
    link_count=0
    for path in files:
        if not path.is_file():
            errors.append(f'Missing entry: {path.relative_to(ROOT)}');continue
        text=path.read_text(encoding='utf-8')
        # Fenced examples are documentation text, not live Markdown links.
        text=re.sub(r'```.*?```','',text,flags=re.S)
        for match in re.finditer(r'\]\(([^)]+)\)',text):
            url=match.group(1).strip()
            if url.startswith(('#','http:','https:','mailto:','data:')):
                continue
            url=url.split(' "',1)[0].strip('<>')
            target=unquote(url.split('#',1)[0])
            if not target:
                continue
            resolved=(path.parent/target).resolve()
            if not resolved.is_relative_to(ROOT) or not resolved.exists():
                errors.append(f'{path.relative_to(ROOT)}: invalid local link {url}')
            link_count+=1
    navigation=ROOT/'docs/03-源码目录与阅读路线.md'
    if navigation.exists():
        inventory=navigation.read_text(encoding='utf-8')
        for source_root in [ROOT/'backend/app',ROOT/'backend/packages/harness/storyclaw']:
            for source in source_root.rglob('*.py'):
                if '__pycache__' in source.parts:
                    continue
                if ']('+('../'+source.relative_to(ROOT).as_posix())+')' not in inventory:
                    errors.append(f'Source navigation missing module: {source.relative_to(ROOT)}')
    # Synthetic paths only: never print an environment file or a credential.
    ignored=['.env','.env.production','backend/.env.test','frontend/.env.local',
             'backend/evaluations/runs/probe/report.json','.pytest_cache/probe',
             'frontend/node_modules/probe','backend/__pycache__/probe.pyc','private.key']
    kept=['.env.example','.env.production.example','backend/.env.test.example',
          'README.md','backend/config/models.yaml','backend/tests/unit/test_quality.py',
          'backend/packages/harness/storyclaw/skills/resources/chapter-craft/SKILL.md',
          'backend/packages/harness/storyclaw/skills/resources/chapter-craft/manifest.json',
          'backend/tests/fixtures/example.json']
    for names,expected in [(ignored,True),(kept,False)]:
        result=subprocess.run(['git','check-ignore','--no-index','--stdin'],input='\n'.join(names)+'\n',cwd=ROOT,text=True,capture_output=True)
        if result.returncode not in (0,1):
            errors.append('Unable to verify Git ignore rules.');continue
        actual=set(result.stdout.splitlines())
        for name in names:
            if (name in actual)!=expected:
                errors.append(f'Ignore policy mismatch: {name}')
    if errors:
        print('\n'.join(errors),file=sys.stderr);return 1
    print(f'Validated {len(handbook)} ordered chapters, {len(files)} current documents, {link_count} local links and {len(ignored)+len(kept)} ignore probes.')
    print('Application/harness source navigation is complete.')
    print('Historical archives are preserved and excluded from current-API/command validation. No model or database calls.')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
