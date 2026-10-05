#!/usr/bin/env python3
"""
regression_check.py - snapshot and compare build_data.py output across every
local customer export. Run it before and after any change to the skill.

    python3 tools/regression_check.py snapshot <label>      # e.g. before
    python3 tools/regression_check.py compare <labelA> <labelB>

Exports are discovered automatically: every *.json in the repo root that has
'masterOrg' and 'production' keys. Snapshots go to _regress/<label>/ (ignored
by git, since they contain customer data). Standard library only; works the
same on Windows, macOS and Linux.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD_DATA = ROOT / 'mulesoft-estate-report' / 'scripts' / 'build_data.py'
REGRESS = ROOT / '_regress'


def exports():
    found = []
    for p in sorted(ROOT.glob('*.json')):
        try:
            with open(p, encoding='utf-8') as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        if isinstance(d, dict) and 'masterOrg' in d and 'production' in d:
            found.append(p)
    return found


def snapshot(label):
    out = REGRESS / label
    out.mkdir(parents=True, exist_ok=True)
    for p in exports():
        r = subprocess.run([sys.executable, str(BUILD_DATA), str(p)],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        status = 'ok' if r.returncode == 0 else f'FAILED (exit {r.returncode})'
        if r.returncode == 0:
            (out / (p.stem + '.json')).write_bytes(r.stdout)
        print(f'  {p.name}: {status}')
    print(f'snapshot written to {out}')


def compare(a, b):
    da, db = REGRESS / a, REGRESS / b
    for fa in sorted(da.glob('*.json')):
        fb = db / fa.name
        if not fb.exists():
            print(f'{fa.stem}: missing in {b}')
            continue
        x, y = json.loads(fa.read_text('utf-8')), json.loads(fb.read_text('utf-8'))
        if x == y:
            print(f'{fa.stem}: identical')
            continue
        keys = [k for k in set(x) | set(y) if x.get(k) != y.get(k)]
        kpis = {k: (x['kpis'].get(k), y['kpis'].get(k)) for k in set(x['kpis']) | set(y['kpis'])
                if x['kpis'].get(k) != y['kpis'].get(k)}
        print(f'{fa.stem}: CHANGED keys={sorted(keys)} kpi diffs={kpis}')


if __name__ == '__main__':
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == 'snapshot':
        snapshot(args[1])
    elif len(args) == 3 and args[0] == 'compare':
        compare(args[1], args[2])
    else:
        sys.exit(__doc__)
