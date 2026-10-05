#!/usr/bin/env python3
"""
build_report.py - mulesoft-estate-report skill, one-command report generator.

Validates an Anypoint network-graph export, runs build_data.py on it, injects
the resulting DATA object into mulesoft_arch_template.html, and writes
{masterOrgName}_Mule_Architecture.html.

Platform-independent by design: standard library only (no pip installs), the
same bytes are written on Windows, macOS and Linux (UTF-8, LF line endings),
console output is plain ASCII, and the output filename is safe on every OS.

Usage:
    python3 build_report.py <input.json> [-o OUTPUT_DIR] [--keep-data] [--open]
    python3 build_report.py <input.json> --check

    -o / --out-dir   where to write the HTML (default: same folder as the input)
    --keep-data      also write {name}_data.json (the raw DATA object) for audit
    --open           open the finished report in the default browser
    --check          validate the export only; don't build anything

Exit codes: 0 ok, 1 build failed (e.g. RECONCILIATION FAILED), 2 invalid input.
Nothing is written unless the build succeeds.
"""
import sys

if sys.version_info < (3, 8):
    sys.exit('build_report.py needs Python 3.8 or newer (found %d.%d).' % sys.version_info[:2])

import argparse
import json
import os
import re
import subprocess
import webbrowser
from pathlib import Path

# Consistent console output on every OS (Windows pipes default to cp1252).
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
BUILD_DATA = SCRIPT_DIR / 'build_data.py'
TEMPLATE = SKILL_DIR / 'mulesoft_arch_template.html'
MATRIX = SKILL_DIR / 'data' / 'ANA Industry Data Matrix - Golden Template.xlsx'
OU_MAP = SKILL_DIR / 'data' / 'customer_ou_map.json'
PLACEHOLDER = 'const DATA = /* DATA_PLACEHOLDER */ null;'
REQUIRED_KEYS = ('masterOrg', 'orgs', 'envs', 'apps', 'sandbox', 'production')


def log(msg=''):
    print(msg, file=sys.stderr)


def read_text(path):
    # newline=None: accept CRLF or LF on input, normalise to LF in memory.
    with open(path, encoding='utf-8', newline=None) as f:
        return f.read()


def write_text(path, text):
    # newline='\n': identical bytes on every OS.
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)


def safe_filename(name):
    """Keep letters, digits, '.', '_' and '-'; everything else -> '_'."""
    return re.sub(r'[^A-Za-z0-9._-]+', '_', name).strip('_.') or 'Customer'


def check_export(path):
    """Validate the export. Returns (raw_json, errors, warnings)."""
    errors, warnings = [], []
    try:
        raw = json.loads(read_text(path))
    except FileNotFoundError:
        return None, [f'input file not found: {path}'], []
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        return None, [f'input is not valid UTF-8 JSON: {e}'], []
    if not isinstance(raw, dict):
        return None, ['input JSON is not an object - is this an Anypoint network-graph export?'], []

    if raw.get('production') is None and 'nodes' not in raw:
        errors.append('no "production" graph (or top-level "nodes") - not a network-graph export?')
    missing = [k for k in REQUIRED_KEYS if k not in raw]
    if missing and not errors:
        warnings.append(f'missing top-level keys {missing} (nodes/edges-only export?)')

    dep = (raw.get('production') or {}).get('dependencies', raw)
    nodes, edges = dep.get('nodes') or [], dep.get('edges') or []
    if not nodes:
        errors.append('production graph has no nodes')
    ids = {n.get('id') for n in nodes}
    dangling = sum(1 for e in edges
                   if (e.get('sourceId') or e.get('source')) not in ids
                   or (e.get('targetId') or e.get('target')) not in ids)
    if dangling:
        warnings.append(f'{dangling} production edge(s) point at missing nodes (will count as unresolved)')

    if 'apps' in raw and not raw.get('apps'):
        rtf = any(n.get('deploymentTarget') == 'rtf' for n in nodes)
        warnings.append('apps[] is empty' + (' (Runtime Fabric estate)' if rtf else '') +
                        ' - Overview will treat each production Mule node as 1 running app in 1 environment;'
                        ' env chart and inventory will be empty')

    customer = ((raw.get('masterOrg') or {}).get('masterOrgName') or '').strip()
    if not customer:
        warnings.append('masterOrg.masterOrgName is empty - report will be titled "Customer"')
    try:
        ou_map = json.loads(read_text(OU_MAP))
        name = customer.lower()
        if not any(not k.startswith('_') and (k.lower() in name or name in k.lower())
                   for k in ou_map):
            warnings.append(f'"{customer}" is not in data/customer_ou_map.json - benchmark will '
                            'compare against all industries; add an entry for this customer')
    except (OSError, ValueError):
        warnings.append('data/customer_ou_map.json missing or unreadable - benchmark uses all industries')
    if not MATRIX.exists():
        warnings.append('data/ANA Industry Data Matrix missing - Reuse tab falls back to a generic 38% benchmark')
    return raw, errors, warnings


def main():
    ap = argparse.ArgumentParser(description='Generate a MuleSoft architecture HTML report.')
    ap.add_argument('input', help='Anypoint network-graph export (.json)')
    ap.add_argument('-o', '--out-dir', help='output folder (default: alongside the input)')
    ap.add_argument('--keep-data', action='store_true', help='also write the DATA JSON')
    ap.add_argument('--open', action='store_true', help='open the report in the default browser')
    ap.add_argument('--check', action='store_true', help='validate the export only')
    args = ap.parse_args()
    in_path = Path(args.input).expanduser().resolve()

    # 1. Validate.
    raw, errors, warnings = check_export(in_path)
    log(f'-- INPUT CHECK: {in_path.name}')
    for w in warnings:
        log(f'  WARNING: {w}')
    for e in errors:
        log(f'  ERROR  : {e}')
    if not errors and not warnings:
        log('  ok')
    if errors:
        sys.exit(2)
    if args.check:
        return

    # 2. Build DATA. build_data.py's reconciliation report streams through stderr.
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    proc = subprocess.run([sys.executable, str(BUILD_DATA), str(in_path)],
                          stdout=subprocess.PIPE, env=env)
    if proc.returncode != 0:
        log(f'build_data.py failed (exit {proc.returncode}) - no report written.')
        sys.exit(1)
    data_json = proc.stdout.decode('utf-8').strip()
    data = json.loads(data_json)

    # 3. Inject into the template.
    tpl = read_text(TEMPLATE)
    if tpl.count(PLACEHOLDER) != 1:
        log(f'Template must contain the DATA placeholder exactly once: {TEMPLATE}')
        sys.exit(1)
    html = tpl.replace(PLACEHOLDER, 'const DATA = ' + data_json + ';')

    # 4. Write output.
    meta = data.get('meta') or {}
    name = safe_filename(meta.get('masterOrg') or meta.get('customer') or 'Customer')
    out_dir = Path(args.out_dir).expanduser().resolve() if args.out_dir else in_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f'{name}_Mule_Architecture.html'
    write_text(out_path, html)
    if args.keep_data:
        write_text(out_dir / f'{name}_data.json', data_json)

    # 5. Summary for a quick sanity check.
    k = data['kpis']
    ra = data.get('reuseAnalysis') or {}
    bench, reuse = ra.get('benchmarkAvg'), ra.get('production') or {}
    log('')
    log(f'-- REPORT WRITTEN: {out_path}')
    log(f"  customer       : {meta.get('customer')}  (extract {meta.get('extractOn')})")
    log(f"  apps           : {k['totalApps']} total, {k['running']} running, {k['stopped']} stopped, "
        f"{k['envs']} environments")
    log(f"  APIs           : {k['uniqueApis']} (Exp {k['expCount']} / Proc {k['procCount']} / "
        f"Sys {k['sysCount']}), {len(data.get('layerOther') or [])} unclassified")
    log(f"  backends/flows : {k['backends']} backends, {k['flows']} flows ({k['flowsRaw']} raw edges)")
    if reuse:
        log(f"  reuse (prod)   : rate {reuse['reuseRate']:.2%}, reusability {reuse['reusability']:.2%}, "
            f"index {reuse['reuseIndexApis']:.2f}")
    log('  benchmark avg  : ' + (f'{bench:.1%}' if bench is not None
                                 else 'NOT AVAILABLE (report falls back to 38% global)'))
    for w in warnings:
        log(f'  WARNING        : {w}')

    if args.open:
        webbrowser.open(out_path.as_uri())


if __name__ == '__main__':
    main()
