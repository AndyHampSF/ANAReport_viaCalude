#!/usr/bin/env python3
"""
build_report.py — mulesoft-estate-report skill, one-command report generator.

Runs build_data.py on an Anypoint network-graph export, injects the resulting
DATA object into mulesoft_arch_template.html, and writes
{masterOrgName}_Mule_Architecture.html (spaces -> underscores).

This is the supported way to produce a report. Doing the injection by hand
(reading the template and re-writing the whole HTML) is slow and risks
truncating or altering a 100-350 KB file; this script makes every run
byte-for-byte reproducible.

Usage:
    python build_report.py <input.json> [-o OUTPUT_DIR] [--keep-data]

    -o / --out-dir   where to write the HTML (default: same folder as the input)
    --keep-data      also write {name}_data.json (the raw DATA object) for audit

The edge reconciliation and benchmark lines from build_data.py are passed
through to stderr. Exits non-zero (and writes nothing) if build_data.py fails,
e.g. RECONCILIATION FAILED.
"""
import argparse
import json
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
BUILD_DATA = os.path.join(SCRIPT_DIR, 'build_data.py')
TEMPLATE = os.path.join(SKILL_DIR, 'mulesoft_arch_template.html')
PLACEHOLDER = 'const DATA = /* DATA_PLACEHOLDER */ null;'


def main():
    ap = argparse.ArgumentParser(description='Generate a MuleSoft architecture HTML report.')
    ap.add_argument('input', help='Anypoint network-graph export (.json)')
    ap.add_argument('-o', '--out-dir', help='output folder (default: alongside the input)')
    ap.add_argument('--keep-data', action='store_true', help='also write the DATA JSON')
    args = ap.parse_args()

    # 1. Build DATA. stderr (reconciliation report) streams straight through.
    proc = subprocess.run([sys.executable, BUILD_DATA, args.input],
                          stdout=subprocess.PIPE)
    if proc.returncode != 0:
        sys.exit(f'build_data.py failed (exit {proc.returncode}) - no report written.')
    data_json = proc.stdout.decode('utf-8').strip()
    data = json.loads(data_json)

    # 2. Inject into the template.
    with open(TEMPLATE, encoding='utf-8') as f:
        tpl = f.read()
    if tpl.count(PLACEHOLDER) != 1:
        sys.exit(f'Template must contain the DATA placeholder exactly once: {TEMPLATE}')
    html = tpl.replace(PLACEHOLDER, 'const DATA = ' + data_json + ';')

    # 3. Write output.
    name = (data['meta'].get('masterOrg') or data['meta'].get('customer') or 'Customer').replace(' ', '_')
    out_dir = args.out_dir or os.path.dirname(os.path.abspath(args.input))
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f'{name}_Mule_Architecture.html')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)
    if args.keep_data:
        with open(os.path.join(out_dir, f'{name}_data.json'), 'w', encoding='utf-8') as f:
            f.write(data_json)

    # 4. Summary for a quick sanity check.
    k = data['kpis']
    bench = (data.get('reuseAnalysis') or {}).get('benchmarkAvg')
    reuse = (data.get('reuseAnalysis') or {}).get('production') or {}
    print(f"\nWritten: {out_path}", file=sys.stderr)
    print(f"  customer       : {data['meta'].get('customer')}  (extract {data['meta'].get('extractOn')})", file=sys.stderr)
    print(f"  apps           : {k['totalApps']} total, {k['running']} running, {k['stopped']} stopped, {k['envs']} environments", file=sys.stderr)
    print(f"  APIs           : {k['uniqueApis']} (Exp {k['expCount']} / Proc {k['procCount']} / Sys {k['sysCount']}), "
          f"{len(data.get('layerOther') or [])} unclassified", file=sys.stderr)
    print(f"  backends/flows : {k['backends']} backends, {k['flows']} flows ({k['flowsRaw']} raw edges)", file=sys.stderr)
    if reuse:
        print(f"  reuse (prod)   : rate {reuse['reuseRate']:.2%}, reusability {reuse['reusability']:.2%}, "
              f"index {reuse['reuseIndexApis']:.2f}", file=sys.stderr)
    print(f"  benchmark avg  : {f'{bench:.1%}' if bench is not None else 'NOT AVAILABLE (report falls back to 38% global)'}",
          file=sys.stderr)
    if not data.get('inventory'):
        print('  WARNING        : export has no apps[] - env chart and inventory will be empty', file=sys.stderr)


if __name__ == '__main__':
    main()
