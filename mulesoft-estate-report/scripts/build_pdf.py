#!/usr/bin/env python3
"""
build_pdf.py - mulesoft-estate-report skill: shareable PDF review for a customer.

Builds a print-designed A4 landscape review from the same DATA as the HTML report,
following the report's tab order:
  cover · executive summary · overview · business groups · API-led · flows ·
  inventory · backends · insights · reuse analysis · next steps.

Every number and observation is derived from the data, so the PDF can always be
regenerated when the data or the report logic changes. Customer-specific wording can
be layered on with an optional notes file (local only; it may name customer apps):

    pdf_notes/<customer-slug>.json
    {
      "insights":   { "<slot>": {"title": "...", "body": "..."} | null, ... },
      "extra":      { "<page>": [ {"title": "...", "body": "..."} ] },
      "recs":       [ {"title": "...", "body": "..."} ],      # replaces the recommendations
      "goal":       "...",                                     # replaces the suggested goal
      "lede":       "...",                                     # replaces the cover sentence
      "good":       ["<b>...</b> ...", ...],                   # replaces "What's working well"
      "gains":      ["<b>...</b> ...", ...],                   # replaces "Where the next gains are"
      "reuse_opportunity": "...",                              # replaces the Reuse page callout
      "asOf":       "28_10_2026"                               # extract date the wording was written for
    }
  slot ids are printed by --list-slots. null hides an auto insight. Text may use
  {placeholders} from the data (see --list-slots).

Usage:
    python3 build_pdf.py <input.json> [-o OUTPUT_DIR] [--customer NAME]
                         [--notes FILE] [--browser PATH] [--keep-html] [--list-slots]

Needs Chrome or Edge to print the PDF (found automatically on Windows, macOS, Linux,
or pass --browser). Everything else is the Python standard library.
"""
import sys

if sys.version_info < (3, 8):
    sys.exit('build_pdf.py needs Python 3.8 or newer.')

import argparse
import html
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
BUILD_DATA = SCRIPT_DIR / 'build_data.py'
TEMPLATE = SKILL_DIR / 'mulesoft_arch_template.html'
CSS_FILE = SKILL_DIR / 'assets' / 'pdf_review.css'
OU_MAP = SKILL_DIR / 'data' / 'customer_ou_map.json'
RUN_STATES = ('RUNNING', 'STARTED', 'SCALING')

# Palettes validated with the dataviz validator (light surface #ffffff)
# One colour, one job (validated with the dataviz validator):
#   LAYER identity only ...... EXP / PROC / SYS / OTHER
#   VALUE (plain magnitude) .. VAL
#   ORDINAL buckets .......... ORD1 > ORD2 > ORD3 (2+/1/0 consumers, platform tiers)
#   STATUS (with a label) .... RUN (ok) / STOP (warning)
EXP, PROC, SYS = '#1E64B0', '#0BA49B', '#5E66F9'
OTHER = '#9AA5B1'
VAL = '#052D60'
ORD1, ORD2, ORD3 = '#052D60', '#5A6B82', '#A7B2C1'
RUN, STOP = '#0B8A3E', '#F2B33D'
GOOD, FAIR, POOR = '#0B8A3E', '#F2B33D', '#D64545'   # verdict: green good, amber could be better, red poor
FAIR_SOFT, POOR_SOFT = '#E3BE70', '#D4877F'   # softer improvement flags for consumer distribution
ACCENT = '#0B7A3B'   # page accents (section numbers, ticks) - not a data colour
NAVY, INK, MUTED, LINE, BAND = '#052D60', '#1B2733', '#5F6B78', '#E3EAF2', '#F3F8FD'
LAYER_COL = {'experience': EXP, 'process': PROC, 'system': SYS, 'other': OTHER}
MONTHS = 'January February March April May June July August September October November December'.split()

e = lambda s: html.escape(str(s))


def log(msg=''):
    print(msg, file=sys.stderr)


# ─────────────────────────────── SVG / HTML helpers ───────────────────────────────
def hbar_rows(rows, maxv, width=470, label_w=170, unit=''):
    h_row, bar_h = 26, 14
    H = h_row * len(rows) + 6
    bw = width - label_w - 48
    out = [f'<svg viewBox="0 0 {width} {H}" width="{width}" height="{H}">']
    for i, (lab, v, col) in enumerate(rows):
        y = i * h_row + 6
        w = max(4, bw * v / maxv) if maxv else 4
        out.append(f'<text x="{label_w-8}" y="{y+bar_h-3}" text-anchor="end" class="t-lab">{e(lab)}</text>')
        out.append(f'<rect x="{label_w}" y="{y}" width="{bw}" height="{bar_h}" fill="{BAND}" rx="2"/>')
        out.append(f'<path d="M{label_w},{y} h{w-4} a4,4 0 0 1 4,4 v{bar_h-8} a4,4 0 0 1 -4,4 h-{w-4} z" fill="{col}"/>')
        out.append(f'<text x="{label_w+w+6}" y="{y+bar_h-3}" class="t-val">{e(v)}{unit}</text>')
    out.append('</svg>')
    return ''.join(out)


def run_stop_rows(rows, width=470, label_w=110, sub=None):
    """rows: [(label, running, total, tag)] -> running/stopped stacked bars."""
    BW = width - label_w - 90
    mx = max([r[2] for r in rows] + [1])
    H = 24 * len(rows) + 4
    out = [f'<svg viewBox="0 0 {width} {H}" width="{width}" height="{H}">']
    for i, (lab, run, tot, tag) in enumerate(rows):
        y = i * 24 + 4
        wr, ws = BW * run / mx, BW * (tot - run) / mx
        out.append(f'<text x="{label_w-8}" y="{y+11}" text-anchor="end" class="t-lab">{e(lab)}</text>')
        if tag:
            out.append(f'<text x="{label_w-8}" y="{y+21}" text-anchor="end" class="t-tag">{e(tag)}</text>')
        if wr > 2:
            out.append(f'<rect x="{label_w}" y="{y}" width="{wr-2:.1f}" height="14" rx="3" fill="{RUN}"/>')
        if ws > 2:
            out.append(f'<rect x="{label_w+wr:.1f}" y="{y}" width="{ws:.1f}" height="14" rx="3" fill="{STOP}"/>')
        extra = f' · {sub[i]}' if sub and sub[i] else ''
        out.append(f'<text x="{label_w+wr+ws+6:.1f}" y="{y+11}" class="t-val">{run}/{tot}{e(extra)}</text>')
    out.append('</svg>')
    return ''.join(out)


def stacked_bar(parts, width=430, height=16):
    tot = sum(v for v, _ in parts) or 1
    x, out = 0, [f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}">']
    for v, c in parts:
        w = width * v / tot
        if w > 2:
            out.append(f'<rect x="{x:.1f}" y="0" width="{w-2:.1f}" height="{height}" rx="3" fill="{c}"/>')
        x += w
    out.append('</svg>')
    return ''.join(out)


def donut(segs, size=150, stroke=24, top='', bot=''):
    r = (size - stroke) / 2; c = size / 2; circ = 2 * math.pi * r
    tot = sum(v for v, _ in segs) or 1
    out = [f'<svg viewBox="0 0 {size} {size}" width="{size}" height="{size}">',
           f'<circle cx="{c}" cy="{c}" r="{r}" fill="none" stroke="{BAND}" stroke-width="{stroke}"/>']
    off = 0
    for v, col in segs:
        frac = v / tot; dash = max(0, frac * circ - 2)
        out.append(f'<circle cx="{c}" cy="{c}" r="{r}" fill="none" stroke="{col}" stroke-width="{stroke}" '
                   f'stroke-dasharray="{dash:.2f} {circ-dash:.2f}" stroke-dashoffset="{-off*circ:.2f}" '
                   f'transform="rotate(-90 {c} {c})"/>')
        off += frac
    out.append(f'<text x="{c}" y="{c-2}" text-anchor="middle" class="d-top">{e(top)}</text>'
               f'<text x="{c}" y="{c+16}" text-anchor="middle" class="d-bot">{e(bot)}</text></svg>')
    return ''.join(out)


def bench_bar(value, bench, name, width=760):
    H = 92; x0, x1 = 10, width - 10; sc = lambda p: x0 + (x1 - x0) * min(max(p, 0), 1)
    bands = [(0, .2, 'Incubating'), (.2, .4, 'Developing'), (.4, .5, 'Industrialised'), (.5, 1, 'Mature API-led')]
    shade = ['#FBE7E7', '#FFF4DE', '#E6F4EC', '#E6F4EC']
    out = [f'<svg viewBox="0 0 {width} {H}" width="{width}" height="{H}">']
    for (a, b, lab), s in zip(bands, shade):
        out.append(f'<rect x="{sc(a)}" y="30" width="{sc(b)-sc(a)-2}" height="22" fill="{s}" rx="3"/>')
        out.append(f'<text x="{(sc(a)+sc(b))/2}" y="66" text-anchor="middle" class="t-band">{lab}</text>')
    out.append(f'<rect x="{sc(0)}" y="36" width="{max(4, sc(value)-sc(0))}" height="10" rx="4" fill="{GOOD if value >= bench else FAIR if value >= bench - .10 else POOR}"/>')
    bx = sc(bench)
    out.append(f'<line x1="{bx}" y1="24" x2="{bx}" y2="56" stroke="{INK}" stroke-width="2"/>')
    out.append(f'<text x="{bx}" y="18" text-anchor="middle" class="t-lab">Peer average {bench:.1%}</text>')
    lab = f'{name} {value:.1%}'
    if value > 0.75:   # label inside the bar end when the bar is long
        out.append(f'<text x="{sc(value)-6}" y="45" text-anchor="end" class="t-val-inv">{e(lab)}</text>')
    else:
        out.append(f'<text x="{sc(value)+6}" y="45" class="t-val">{e(lab)}</text>')
    for p in (0, .25, .5, .75, 1):
        out.append(f'<text x="{sc(p)}" y="84" text-anchor="middle" class="t-axis">{int(p*100)}%</text>')
    out.append('</svg>')
    return ''.join(out)


def kpi(value, label, sub=''):
    return (f'<div class="kpi"><div class="kv">{value}</div><div class="kl">{e(label)}</div>'
            + (f'<div class="ks">{sub}</div>' if sub else '') + '</div>')


def card(title, body):
    return f'<div class="ins"><div class="ins-t">{title}</div><div class="ins-b">{body}</div></div>'


def plural(n, one, many=None):
    return one if n == 1 else (many or one + 's')


def find_browser(explicit=None):
    if explicit:
        return explicit
    cands = []
    if os.name == 'nt':
        for base in (os.environ.get('PROGRAMFILES', r'C:\Program Files'),
                     os.environ.get('PROGRAMFILES(X86)', r'C:\Program Files (x86)'),
                     os.environ.get('LOCALAPPDATA', '')):
            cands += [Path(base) / 'Google/Chrome/Application/chrome.exe',
                      Path(base) / 'Microsoft/Edge/Application/msedge.exe']
    elif sys.platform == 'darwin':
        cands += [Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'),
                  Path('/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'),
                  Path('/Applications/Chromium.app/Contents/MacOS/Chromium')]
    for c in cands:
        if c and Path(c).exists():
            return str(c)
    for name in ('google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser',
                 'microsoft-edge', 'chrome', 'msedge'):
        p = shutil.which(name)
        if p:
            return p
    return None


# ───────────────────────────────── the review ─────────────────────────────────
class Review:
    def __init__(self, D, RAW, notes, logo):
        self.D, self.RAW, self.N, self.logo = D, RAW, notes or {}, logo
        self.name = D['meta']['customer']
        K = self.K = D['kpis']
        RA = D['reuseAnalysis'] or {}
        self.RP = RA.get('production') or {}
        self.bench = RA.get('benchmarkAvg')
        self.by_bg = RA.get('byBG') or []
        apps = self.apps = RAW.get('apps') or []
        self.has_apps = bool(apps)
        org = {o['orgId']: o['orgName'] for o in RAW.get('orgs', [])}
        prod = [a for a in apps if a.get('envtype') == 'production']
        self.prod_total = len(prod) if apps else K['totalApps']
        self.prod_run = sum(1 for a in prod if a.get('status') in RUN_STATES) if apps else K['running']
        self.ch2 = sum(1 for a in apps if str(a.get('target', '')).startswith('CH2'))
        self.targets = Counter(a.get('target') or 'Unknown' for a in apps)
        self.stopped_by_bg = Counter(org.get(a.get('orgid'), '?') for a in apps if a.get('status') not in RUN_STATES)
        self.dups = sum(1 for c in Counter((a.get('appname'), a.get('envid')) for a in apps).values() if c > 1)
        self.vc_total = round(sum(r.get('runningVcores') or 0 for r in D['envRows']), 1)
        self.vc_prod = round(sum(r.get('runningVcores') or 0 for r in D['envRows'] if r['type'] == 'production'), 1)
        self.layers, self.other = D['layers'], D.get('layerOther') or []
        self.idle = [n['label'] for n in D['nodes'] if n['kind'] == 'mule' and n['in'] == 0 and n['out'] == 0]
        self.shared = sorted([n for n in D['nodes'] if n['kind'] == 'mule' and n['in'] > 1],
                             key=lambda n: (-n['in'], n['label']))
        self.DC, self.AD, self.CF, self.RM = (D.get('deploymentCoverage'), D.get('adoption'),
                                              D.get('confidence'), D.get('reuseMetrics'))
        self.BGS = D.get('businessGroups') or []
        self.PH = D.get('platformHealth')
        self.client_total = sum(n.get('numberOfClientApplications', 1) for n in
                                (RAW.get('production', {}).get('dependencies', {}).get('nodes') or [])
                                if n.get('type') == 'clientGroup')
        ext = [c for c in D.get('consumers', []) if not c['key'].startswith('consumer-merged')]
        self.ext_traffic = ext[0] if ext else None
        # integration/batch apps
        lbls = {n['label'] for n in self.other}; byl = {n['label']: n for n in D['nodes']}
        self.int_reached, self.int_calls = set(), 0
        for x in D['edges']:
            if x['source'] in lbls:
                t = byl.get(x['target'])
                if t and t['kind'] == 'backend':
                    self.int_reached.add(x['target'])
                elif t and t['kind'] == 'mule':
                    self.int_calls += 1
        # shared name prefix (e.g. pro-whs-) for compact tiles
        mule = [n['label'] for n in D['nodes'] if n['kind'] == 'mule']
        pc = Counter(m.group(1) for m in (re.match(r'^([^-]+-[^-]+-)', x) for x in mule) if m)
        top = pc.most_common(1)
        self.prefix = top[0][0] if top and len(mule) >= 5 and top[0][1] >= 0.6 * len(mule) else ''
        # extract date
        m = re.match(r'(\d{2})_(\d{2})_(\d{4})', D['meta'].get('extractOn') or '')
        self.extract = f'{int(m.group(1))} {MONTHS[int(m.group(2))-1]} {m.group(3)}' if m else (D['meta'].get('extractOn') or '')
        # industry label for the benchmark text
        self.industry = self._industry()
        self.slots = {}          # slot id -> default text (for --list-slots)

    # ---- notes / slots ----
    def fields(self):
        K, RP = self.K, self.RP
        return {'customer': self.name, 'apps': K['totalApps'], 'running': K['running'],
                'stopped': K['stopped'], 'envs': K['envs'], 'flows': K['flows'],
                'backends': K['backends'], 'reuse_rate': f"{RP.get('reuseRate', 0):.1%}",
                'benchmark': f'{self.bench:.1%}' if self.bench is not None else 'n/a',
                'extract': self.extract}

    def ins(self, slot, title, body):
        """An auto insight that notes can replace (dict) or hide (null)."""
        self.slots[slot] = title
        over = (self.N.get('insights') or {})
        if slot in over:
            o = over[slot]
            if o is None:
                return ''
            title, body = o.get('title', title), o.get('body', body)
            try:
                title, body = title.format(**self.fields()), body.format(**self.fields())
            except (KeyError, IndexError, ValueError):
                pass
        return card(title, body)

    def extra(self, page):
        return ''.join(card(x.get('title', ''), x.get('body', '')) for x in ((self.N.get('extra') or {}).get(page) or []))

    def short(self, label):
        return label[len(self.prefix):] if self.prefix and label.startswith(self.prefix) else label

    def _industry(self):
        try:
            ou = json.loads(OU_MAP.read_text('utf-8'))
            low = self.name.lower()
            for k, v in ou.items():
                if not k.startswith('_') and (k.lower() in low or low in k.lower()):
                    v = v if isinstance(v, list) else [v]
                    v = [(lambda t: ' and '.join(t.rsplit(', ', 1)) if ', ' in t else t)(x.replace(', &', ' &'))
                         for x in v]
                    return v[0] if len(v) == 1 else ', '.join(v[:-1]) + ' and ' + v[-1]
        except (OSError, ValueError):
            pass
        return None

    def maturity(self, r):
        return ('Mature API-led' if r >= .5 else 'Industrialised' if r >= .4 else
                'Developing' if r >= .2 else 'Incubating')

    # ---------------------------------- pages ----------------------------------
    def cover(self):
        K, RP = self.K, self.RP
        lede = self.N.get('lede') or ('How the MuleSoft estate is built, how it is used, and where '
                                       'the next gains in API reuse will come from.')
        plat = (f'<div><b>{self.ch2/len(self.apps):.0%}</b><span>on CloudHub 2.0</span></div>'
                if self.has_apps and self.ch2 else
                f'<div><b>{K["envs"]}</b><span>environments</span></div>')
        return f'''
<section class="page cover">
  <div class="cover-top"><img class="logo" src="{self.logo}"><span class="brand">MuleSoft · Anypoint Platform</span></div>
  <div class="cover-mid">
    <div class="eyebrow">Integration Architecture Review</div>
    <h1>{e(self.name)}</h1>
    <p class="lede">{e(lede)}</p>
  </div>
  <div class="cover-stats">
    <div><b>{K['running']}</b><span>applications running</span></div>
    {plat}
    <div><b>{K['flows']}</b><span>production integration flows</span></div>
    <div><b>{RP.get('reuseRate', 0):.0%}</b><span>production reuse rate</span></div>
  </div>
  <div class="cover-foot">Based on the Anypoint Platform network-graph export of {e(self.extract)} · {len(self.RAW.get('orgs', []))} business {plural(len(self.RAW.get('orgs', [])), 'group')} · {K['envs']} active environments</div>
</section>'''

    def good_points(self):
        K, RP, out = self.K, self.RP, []
        if self.has_apps:
            out.append(f'<b>Production is {"fully" if self.prod_run == self.prod_total else "largely"} healthy</b>: '
                       f'{self.prod_run} of {self.prod_total} production deployments are running.')
        if self.has_apps and self.ch2 / max(len(self.apps), 1) >= .8:
            out.append(f'<b>The platform is modern</b>: {self.ch2} of {len(self.apps)} deployments '
                       f'({self.ch2/len(self.apps):.0%}) are on CloudHub 2.0.')
        if self.bench is not None and RP.get('reuseRate', 0) >= self.bench:
            out.append(f'<b>Reuse is ahead of peers</b>: a {RP["reuseRate"]:.1%} production reuse rate against '
                       f'a {self.bench:.1%} peer average ({self.maturity(RP["reuseRate"])} stage).')
        if self.shared:
            out.append(f'<b>Shared services are in place</b>: {len(self.shared)} '
                       f'{plural(len(self.shared), "API is", "APIs are")} called by two or more components, led by '
                       f'{e(self.short(self.shared[0]["label"]))}.')
        layered = K['uniqueApis']; mule_n = RP.get('apisTotal') or layered
        if mule_n and layered / mule_n >= .7:
            out.append(f'<b>A clear API-led structure</b>: {layered} of {mule_n} production apps follow the '
                       f'Experience / Process / System pattern.')
        if self.DC and self.DC['coveragePct'] >= 95:
            out.append(f'<b>Everything is connected</b>: {self.DC["mapped"]} of {self.DC["prodTotal"]} production apps '
                       f'appear in the dependency graph.')
        return out[:4]

    def gain_points(self):
        K, RP, out = self.K, self.RP, []
        if self.bench is not None and RP.get('reuseRate', 0) < self.bench:
            out.append(f'<b>Close the gap to peers.</b> {e(self.name)}\'s {RP["reuseRate"]:.1%} reuse rate compares '
                       f'with a {self.bench:.1%} average for comparable customers.')
        if K['stopped']:
            out.append(f'<b>Retire what isn\'t used.</b> {K["stopped"]} stopped {plural(K["stopped"], "application")}'
                       + (f' and {self.dups} duplicate {plural(self.dups, "deployment")}' if self.dups else '')
                       + ' could be decommissioned.')
        if self.DC and self.DC['isolated']:
            out.append(f'<b>Review isolated apps.</b> {self.DC["isolated"]} production {plural(self.DC["isolated"], "app has", "apps have")} '
                       f'no mapped dependencies.')
        ch1 = self.targets.get('CH1.0', 0)
        if self.has_apps and ch1 / len(self.apps) >= .5:
            out.append(f'<b>Plan the move to CloudHub 2.0.</b> {ch1} of {len(self.apps)} deployments '
                       f'({ch1/len(self.apps):.0%}) still run on CloudHub 1.0.')
        if len(self.other) >= 3:
            out.append(f'<b>Bring more apps into the API-led pattern.</b> {len(self.other)} production apps sit outside '
                       f'the Experience / Process / System layers.')
        bl = RP.get('byLayer') or {}
        if bl.get('process', {}).get('total', 0) >= 3 and bl['process']['reuseRate'] < .3:
            out.append(f'<b>Build reusable Process APIs.</b> Process-layer reuse is {bl["process"]["reuseRate"]:.0%}; '
                       f'design orchestration to serve several channels.')
        if self.AD and self.AD['coveragePct'] < 30:
            out.append(f'<b>Manage more consumers.</b> Only {self.AD["consumedApis"]} of {self.AD["totalApis"]} APIs '
                       f'are consumed by registered client apps.')
        busy = (self.PH or {}).get('singleReplicaBusy') or []
        if busy:
            out.insert(min(1, len(out)), f'<b>Protect shared APIs.</b> {len(busy)} production {plural(len(busy), "API")} '
                       f'used by 3+ consumers {plural(len(busy), "runs", "run")} on a single replica.')
        if (self.PH or {}).get('java8'):
            out.append(f'<b>Upgrade from Java 8.</b> {len(self.PH["java8"])} production '
                       f'{plural(len(self.PH["java8"]), "app")} still run on Java 8.')
        if self.idle:
            out.append(f'<b>Confirm quiet APIs.</b> {len(self.idle)} production {plural(len(self.idle), "app")} had no '
                       f'observed traffic.')
        return out[:4]

    def default_goal(self):
        RP = self.RP; r = RP.get('reuseRate', 0)
        if self.bench is not None and r < self.bench:
            tgt = min(self.bench, r + .10)
            return (f'Lift the production reuse rate from {r:.1%} to <b>{tgt:.0%}+</b> by the next review, '
                    f'by pointing new builds at existing shared APIs and retiring unused applications. '
                    f'Re-running this report will show the progress.')
        return (f'Keep the reuse rate above <b>{math.floor(r*20)/20:.0%}</b> while simplifying: retire superseded '
                f'or unused APIs and lift reusability (the share of APIs with more than one consumer) from '
                f'{RP.get("reusability", 0):.1%}.')

    def exec_summary(self):
        K = self.K
        good = ''.join(f'<li>{x}</li>' for x in (self.N.get('good') or self.good_points()))
        gain = ''.join(f'<li>{x}</li>' for x in (self.N.get('gains') or self.gain_points()))
        conf = (f'<div class="note" style="margin-top:10px">Data confidence: <b>{e(self.CF["band"])}</b>. '
                f'{e(". ".join(r.rstrip(".") for r in self.CF["reasons"]))}.</div>' if self.CF else '')
        return f'''
<section class="page">
  <div class="sec-head"><span class="sec-no">At a glance</span><h2>Executive summary</h2></div>
  <div class="cols2">
    <div><h3 class="good">What's working well</h3><ul class="ticks">{good}</ul></div>
    <div><h3 class="next">Where the next gains are</h3><ul class="arrows">{gain}</ul></div>
  </div>
  <div class="callout"><div class="callout-k">Suggested goal</div><div>{self.N.get('goal') or self.default_goal()}</div></div>
  <div class="mini-kpis">
    {kpi(K['totalApps'], 'Deployments', f'{K["running"]} running · {K["stopped"]} stopped')}
    {kpi(K['envs'], 'Active environments')}
    {kpi(K['uniqueApis'], 'Layered APIs', f'{K["expCount"]} Exp · {K["procCount"]} Proc · {K["sysCount"]} Sys')}
    {kpi(K['backends'], 'Backend systems')}
  </div>
  {conf}
</section>'''

    def overview(self):
        K, D = self.K, self.D
        rows = [r for r in D['envRows'] if r['total'] >= 3] or D['envRows']
        rows = sorted(rows, key=lambda r: (r['type'] != 'production', -r['total']))[:14]
        chart = (run_stop_rows([(r['name'], r['running'], r['total'], 'production' if r['type'] == 'production' else '')
                                for r in rows], sub=[f'{r["runningVcores"]} vC' if r.get('runningVcores') else '' for r in rows])
                 if rows else '<p class="note">No deployment data in this export.</p>')
        prod_rows = [r for r in D['envRows'] if r['type'] == 'production']
        biggest = max(D['envRows'], key=lambda r: r['total']) if D['envRows'] else None
        cards = [
            self.ins('overview.health', 'Production health',
                     f'{self.prod_run} of {self.prod_total} production applications are running'
                     + ('. ' + (f'All production environments ({", ".join(e(r["name"]) for r in prod_rows)}) are fully running.'
                                if prod_rows and all(r['stopped'] == 0 for r in prod_rows) else
                                'Some production environments have stopped apps to review.') if prod_rows else '.')),
            self.ins('overview.stopped', 'Where stopped apps sit',
                     (f'{K["stopped"]} of {K["totalApps"]} deployments are stopped, mostly in '
                      f'{e(max(D["envRows"], key=lambda r: r["stopped"])["name"])}.' if K['stopped'] else
                      'Every deployment is running, with no idle capacity to reclaim.')),
            self.ins('overview.capacity', 'Capacity',
                     (f'{self.vc_total} vCores are in use, {self.vc_prod} of them in production.' if self.vc_total else
                      f'{K["envs"]} environments, the largest being {e(biggest["name"])} with {biggest["total"]} apps.'
                      if biggest else 'No capacity data in this export.')),
        ]
        return f'''
<section class="page">
  <div class="sec-head"><span class="sec-no">1 · Overview</span><h2>The estate at a glance</h2></div>
  <div class="kpis">
    {kpi(K['totalApps'], 'Deployed applications')}
    {kpi(f'{K["running"]}<small>/{K["totalApps"]}</small>', 'Running')}
    {kpi(K['envs'], 'Active environments')}
    {kpi(K['flows'], 'Production flows')}
    {kpi(K['backends'], 'Backend systems')}
    {kpi(self.vc_total or '—', 'vCores in use', f'{self.vc_prod} in production' if self.vc_total else '')}
  </div>
  <div class="cols2 top">
    <div class="card">
      <h4>Applications by environment <span class="leg"><i style="background:{RUN}"></i>Running <i style="background:{STOP}"></i>Stopped</span></h4>
      {chart}
      <div class="note">Values show running / total{" and the vCores (vC) in use" if self.vc_total else ""}.</div>
    </div>
    <div>{''.join(cards)}{self.extra('overview')}</div>
  </div>
</section>'''

    def business_groups(self):
        if len(self.BGS) < 2:
            return ''
        def bgc(b):
            seg = lambda v, c: f'<i style="flex:{v};background:{c}"></i>' if v else ''
            pills = ((f'<span class="pill-p">{b["prod"]} prod</span>' if b['prod'] else '')
                     + (f'<span class="pill-s">{b["sandbox"]} sandbox</span>' if b['sandbox'] else ''))
            return (f'<div class="bgc"><div class="bgc-h"><b>{e(b["name"])}</b><span>{pills}</span></div>'
                    f'<div class="bgc-r"><span>Applications</span><b>{b["running"]} running / {b["total"]}</b></div>'
                    f'<div class="bgc-bar"><i style="width:{round(b["running"]/b["total"]*100) if b["total"] else 0}%"></i></div>'
                    f'<div class="bgc-r"><span>Layer mix</span><span class="mut">Exp {b["experience"]} · Proc {b["process"]} · Sys {b["system"]} · Other {b["other"]}</span></div>'
                    f'<div class="bgc-mix">{seg(b["experience"], EXP)}{seg(b["process"], PROC)}{seg(b["system"], SYS)}{seg(b["other"], OTHER)}</div></div>')
        biggest = self.BGS[0]
        most_led = max(self.BGS, key=lambda b: (b['experience'] + b['process'] + b['system']))
        most_stop = max(self.BGS, key=lambda b: b['total'] - b['running'])
        cards = [
            self.ins('bg.largest', f'{e(biggest["name"])} is the largest group',
                     f'{biggest["total"]} deployments, {biggest["running"]} running.'),
            self.ins('bg.apiled', f'{e(most_led["name"])} leads on API-led',
                     f'{most_led["experience"] + most_led["process"] + most_led["system"]} of its {most_led["total"]} '
                     f'deployments sit in the three API layers.'),
            self.ins('bg.cleanup', 'Where the clean-up is',
                     (f'{e(most_stop["name"])} has the most stopped deployments '
                      f'({most_stop["total"] - most_stop["running"]} of {most_stop["total"]}).'
                      if most_stop['total'] > most_stop['running'] else 'No group has stopped deployments.')),
        ]
        return f'''
<section class="page">
  <div class="sec-head"><span class="sec-no">1 · Overview, continued</span><h2>{len(self.BGS)} business groups</h2></div>
  <p class="intro">Applications, operational health and API-led layer mix for each Anypoint business group, across all environments.</p>
  <div class="bgc-grid">{''.join(bgc(b) for b in self.BGS)}</div>
  <div class="cols3" style="margin-top:12px">{''.join(cards)}{self.extra('business_groups')}</div>
</section>'''

    def api_led(self):
        K, L = self.K, self.layers
        total = sum(len(L[k]) for k in ('experience', 'process', 'system')) + len(self.other)
        compact = total > 70
        def tiles(nodes, col, cap=None):
            more = ''
            if cap and len(nodes) > cap:
                more = f'<span class="tile more">+ {len(nodes) - cap} more</span>'
                nodes = sorted(nodes, key=lambda n: (-n['in'], n['label']))[:cap]
            return ''.join(f'<span class="tile" style="border-left-color:{col}">{e(self.short(n["label"]))}'
                           + (f'<b class="badge">{n["in"]}</b>' if n['in'] > 1 else '') + '</span>' for n in nodes) + more
        lanes = ''.join(f'<div class="lane"><div class="lane-l" style="background:{c}">{t}<small>{len(L[k])} {plural(len(L[k]), "API")}</small></div>'
                        f'<div class="lane-r">{tiles(L[k], c)}</div></div>'
                        for k, t, c in (('experience', 'Experience', EXP), ('process', 'Process', PROC), ('system', 'System', SYS)))
        if self.other:
            lanes += (f'<div class="lane"><div class="lane-l" style="background:{OTHER}">Integration &amp; batch<small>{len(self.other)} apps</small></div>'
                      f'<div class="lane-r">{tiles(self.other, OTHER, 14 if compact else None)}</div></div>'
                      f'<p class="note" style="margin:2px 0 8px">Integration &amp; batch apps sit outside the Experience / Process / System naming pattern'
                      + ('; nothing calls them. ' if not any(n['in'] for n in self.other) else
                         f'; {sum(1 for n in self.other if n["in"])} of them are called by other components. ')
                      + f'Between them they reach {len(self.int_reached)} backend {plural(len(self.int_reached), "system")} directly'
                      + (f' and call Mule APIs {self.int_calls} {plural(self.int_calls, "time")}' if self.int_calls else '') + '.</p>')
        widest = max(('experience', 'process', 'system'), key=lambda k: len(L[k]))
        top_sys = [n for n in self.shared if n['layer'] == 'system'][:2]
        cards = [
            self.ins('api.widest', f'The {widest.capitalize()} layer is the widest',
                     f'{len(L[widest])} {widest.capitalize()} APIs, against '
                     + ', '.join(f'{len(L[k])} {k.capitalize()}' for k in ('experience', 'process', 'system') if k != widest) + '.'),
            self.ins('api.shared', 'Shared building blocks',
                     (', '.join(f'{e(self.short(n["label"]))} ({n["in"]} callers)' for n in top_sys)
                      + ' are the most-called System APIs.' if top_sys else
                      'No System API is called by more than one component yet.')),
            self.ins('api.pattern', 'How much follows the pattern',
                     f'{K["uniqueApis"]} of {self.RP.get("apisTotal", K["uniqueApis"])} production apps sit in a clear layer'
                     + (f'; {len(self.other)} are integration or batch apps.' if self.other else '.')),
        ]
        pfx = f' Names are shown without the shared prefix <b>{e(self.prefix)}</b>.' if self.prefix else ''
        cls = 'page compact' if compact else 'page'
        return f'''
<section class="{cls}">
  <div class="sec-head"><span class="sec-no">2 · API-Led Architecture</span><h2>The three-layer view</h2></div>
  <p class="intro">Experience APIs serve channels and partners, Process APIs orchestrate, and System APIs connect the systems of record. A badge shows how many other components call that API.{pfx}</p>
  {lanes}
  <div class="cols3">{''.join(cards)}{self.extra('api_led')}</div>
</section>'''

    def flows(self):
        K, RP = self.K, self.RP
        top = (RP.get('perApp') or [])[:8]
        chart = (hbar_rows([(self.short(a['name']), a['consumers'], LAYER_COL.get(a['layer'], OTHER)) for a in top],
                           max(a['consumers'] for a in top), label_w=210) if top else '<p class="note">No consumers recorded.</p>')
        share = sum(a['consumers'] for a in RP.get('perApp', [])[:4]) / RP['consumers'] if RP.get('consumers') else 0
        ext = self.ext_traffic
        cards = [
            self.ins('flows.demand', 'Where demand concentrates',
                     (f'The four most-consumed APIs carry {share:.0%} of all {RP["consumers"]} consumers, '
                      f'led by {e(self.short(top[0]["name"]))} ({top[0]["consumers"]}).' if top else 'No consumer data.')),
            self.ins('flows.clients', 'Managed consumers',
                     f'{self.client_total} client {plural(self.client_total, "application")} '
                     f'{plural(self.client_total, "is", "are")} registered in API Manager'
                     + (f' ({len(self.D["clientApps"])} named in the export)' if len(self.D['clientApps']) != self.client_total else '')
                     + '. Managed contracts add visibility, SLAs and measurable reuse.'),
            self.ins('flows.unidentified', 'Unidentified inbound traffic',
                     (f'"{e(ext["label"])}" stands for callers without a recognised client ID; it calls {ext["out"]} '
                      f'{plural(ext["out"], "API")}. Registering these callers in API Manager would make them visible.'
                      if ext else 'All inbound traffic comes from registered client applications.')),
            self.ins('flows.quiet', 'APIs with no traffic',
                     (f'{len(self.idle)} production {plural(len(self.idle), "app")} had no observed calls in the period. '
                      f'They may be new or low-volume, and are worth confirming.' if self.idle else
                      'Every production app had observed traffic in the period.')),
        ]
        return f'''
<section class="page">
  <div class="sec-head"><span class="sec-no">3 · Integration Flows</span><h2>How the estate is used</h2></div>
  <div class="kpis k4">
    {kpi(K['flows'], 'Unique production flows', f'{K["flowsRaw"]} raw connections')}
    {kpi(self.client_total, 'Registered client apps')}
    {kpi(RP.get('apisTotal', 0), 'Production Mule apps')}
    {kpi(RP.get('consumedNone', 0), 'APIs with no consumers')}
  </div>
  <div class="cols2 top">
    <div class="card">
      <h4>Most-consumed production APIs <span class="leg"><i style="background:{EXP}"></i>Exp <i style="background:{PROC}"></i>Proc <i style="background:{SYS}"></i>Sys <i style="background:{OTHER}"></i>Other</span></h4>
      {chart}
      <div class="note">Number of consumers: client applications plus calling APIs.</div>
    </div>
    <div>{''.join(cards)}{self.extra('flows')}</div>
  </div>
</section>'''

    def inventory(self):
        K = self.K
        bg_rows = [(b['name'], b['running'], b['total'], '') for b in self.BGS][:10]
        bg_chart = run_stop_rows(bg_rows, label_w=150) if bg_rows else ''
        tg = self.targets
        order = [('CH2.0 - private-space', ORD1, 'CH2.0 private space'), ('CH2.0 - shared-space', ORD2, 'CH2.0 shared space'),
                 ('CH1.0', ORD3, 'CloudHub 1.0'), ('SERVER', '#D5DCE5', 'Customer-hosted')]
        parts = [(tg[k], c) for k, c, _ in order if tg.get(k)]
        legend = ''.join(f'<span><i style="background:{c}"></i>{lab} · {tg[k]}</span>' for k, c, lab in order if tg.get(k))
        platform = (f'<h4 style="margin-top:18px">Runtime platform</h4>{stacked_bar(parts)}<div class="leg2">{legend}</div>'
                    if parts else '')
        ch1 = tg.get('CH1.0', 0)
        cards = [
            self.ins('inv.platform', 'Runtime platform',
                     (f'All {len(self.apps)} deployments run on CloudHub 1.0. Moving to CloudHub 2.0 is the next platform step.'
                      if self.has_apps and ch1 == len(self.apps) else
                      f'{self.ch2} of {len(self.apps)} deployments run on CloudHub 2.0'
                      + (f'; {ch1} {plural(ch1, "remains", "remain")} on CloudHub 1.0.' if ch1 else '.')
                      if self.has_apps else 'No deployment data in this export.')),
            self.ins('inv.stopped', 'Stopped applications',
                     (f'{K["stopped"]} {plural(K["stopped"], "deployment is", "deployments are")} stopped'
                      + (f', most in {e(self.stopped_by_bg.most_common(1)[0][0])} ({self.stopped_by_bg.most_common(1)[0][1]})'
                         if self.stopped_by_bg and len(self.BGS) > 1 else '')
                      + '. A clean-up sprint would simplify governance.' if K['stopped'] else 'No stopped deployments.')),
            self.ins('inv.duplicates', 'Duplicate deployments',
                     (f'{self.dups} {plural(self.dups, "app is", "apps are")} deployed twice in the same environment, '
                      f'usually an old stopped copy beside a running one. These can be removed.' if self.dups else None) or None)
            if self.dups else '',
            self.ins('inv.isolated', (f'{self.DC["isolated"]} isolated production {plural(self.DC["isolated"], "app")}'
                                      if self.DC['isolated'] else 'Full deployment coverage') if self.DC else 'Isolated apps',
                     (f'{self.DC["mapped"]} of {self.DC["prodTotal"]} production apps appear in the dependency graph. The other '
                      f'{self.DC["isolated"]} ({", ".join(e(x["name"]) for x in self.DC["isolatedApps"][:5])}'
                      f'{" and more" if self.DC["isolated"] > 5 else ""}) have no mapped dependencies.'
                      if self.DC and self.DC['isolated'] else 'Every production app is connected into the integration graph.'))
            if self.DC else '',
            self.ins('inv.health', 'Platform health', self.health_text()) if self.health_text() else '',
        ]
        return f'''
<section class="page">
  <div class="sec-head"><span class="sec-no">4 · Application Inventory</span><h2>{K['totalApps']} deployments{f" across {len(self.BGS)} business groups" if len(self.BGS) > 1 else ""}</h2></div>
  <div class="cols2 top">
    <div class="card">
      <h4>Deployments by business group <span class="leg"><i style="background:{RUN}"></i>Running <i style="background:{STOP}"></i>Stopped</span></h4>
      {bg_chart}{platform}
    </div>
    <div>{''.join(c for c in cards if c)}{self.extra('inventory')}</div>
  </div>
</section>'''

    def backends(self):
        K = self.K
        be = [b for b in self.D['backends'] if b['in'] > 0][:14]
        chart = (hbar_rows([(b['label'], b['in'], VAL) for b in be], max(b['in'] for b in be), label_w=200)
                 if be else '<p class="note">No backend connections recorded.</p>')
        cats = Counter(b['category'] for b in self.D['backends'] if b['in'] > 0)
        single = sum(1 for b in self.D['backends'] if b['in'] == 1)
        cards = [
            self.ins('backends.hub', f'{e(be[0]["label"])} is the most-connected system' if be else 'Backends',
                     (f'{be[0]["in"]} production flows end at {e(be[0]["label"])}'
                      + (f', followed by {e(be[1]["label"])} ({be[1]["in"]}).' if len(be) > 1 else '.')) if be else 'None.'),
            self.ins('backends.mix', 'The systems behind the APIs',
                     ', '.join(f'{c}: {n}' for c, n in cats.most_common(4)) + '.' if cats else 'No backends.'),
            self.ins('backends.single', 'Single-connection systems',
                     f'{single} {plural(single, "system has", "systems have")} a single connection. If other teams need the '
                     f'same data, these are candidates for shared System APIs.'),
        ]
        return f'''
<section class="page">
  <div class="sec-head"><span class="sec-no">5 · Backend Systems</span><h2>{K['backends']} systems of record and partners</h2></div>
  <div class="cols2 top">
    <div class="card">
      <h4>Connections per backend system</h4>{chart}
      <div class="note">Number of production integration flows that end at each system (top {len(be)} of {K['backends']}).</div>
    </div>
    <div>{''.join(cards)}{self.extra('backends')}</div>
  </div>
</section>'''

    def health_text(self):
        """Platform Health observation (resilience, runtime, test apps) or '' if no data."""
        PH = self.PH
        if not PH or not (PH['replicaKnown'] or PH['runtimeKnown'] or PH['testAppsInProd']):
            return ''
        parts = []
        if PH['replicaKnown']:
            busy = PH['singleReplicaBusy']
            if PH['singleReplica'] == 0:
                parts.append('Every production API runs on two or more replicas.')
            elif busy:
                parts.append(f'{PH["singleReplica"]} of {PH["replicaKnown"]} production apps run on one replica, including '
                             f'{len(busy)} shared by 3+ consumers (led by {e(self.short(busy[0]["name"]))}, '
                             f'{busy[0]["consumers"]}). An outage there affects every caller.')
            else:
                parts.append(f'{PH["singleReplica"]} of {PH["replicaKnown"]} production apps run on one replica, '
                             f'none of them widely shared.')
        if PH['runtimeKnown']:
            parts.append(f'{len(PH["java8"])} of {PH["runtimeKnown"]} production apps still run on Java 8.' if PH['java8']
                         else 'All production apps with a known runtime are on Java 17 or later.')
        if PH['testAppsInProd']:
            parts.append(f'Test apps in production: {", ".join(e(x) for x in PH["testAppsInProd"][:3])}.')
        return ' '.join(parts)

    def default_recs(self):
        K, RP, out = self.K, self.RP, []
        if K['stopped'] or self.dups:
            out.append(('Decommission unused applications', f'Review the {K["stopped"]} stopped'
                        + (f' and {self.dups} duplicate' if self.dups else '') + ' deployments, starting with proofs of concept and test projects.'))
        top_sys = [n for n in self.shared if n['layer'] == 'system'][:3]
        if top_sys:
            out.append(('Promote the shared System APIs', 'Publish ' + ', '.join(e(self.short(n['label'])) for n in top_sys)
                        + ' in Exchange with clear documentation and SLAs.'))
        top = (RP.get('perApp') or [])[:4]
        if top and top[0]['consumers'] >= 20:
            out.append(('Protect the busiest APIs', 'Apply SLA tiers and rate limits in API Manager to the most-consumed APIs ('
                        + ', '.join(e(self.short(a['name'])) for a in top[:3]) + ').'))
        if self.AD and self.AD['coveragePct'] < 50:
            out.append(('Manage consumers through API Manager', f'Only {self.AD["consumedApis"]} of {self.AD["totalApis"]} APIs '
                        f'({self.AD["coveragePct"]}%) are consumed by registered client apps. Register clients and contracts.'))
        if self.ext_traffic:
            out.append(('Identify unregistered callers', f'Traffic shown as "{e(self.ext_traffic["label"])}" has no recognised '
                        f'client ID. Registering these callers adds visibility and policy control.'))
        if len(self.other) >= 3:
            out.append(('Extend API-led delivery', f'{len(self.other)} production apps sit outside the API layers. '
                        f'New builds should reuse existing System APIs rather than connect point-to-point.'))
        if self.DC and self.DC['isolated']:
            out.append(('Triage isolated production apps', f'{self.DC["isolated"]} production apps have no mapped dependencies. '
                        f'Retire, document or connect them.'))
        PH = self.PH or {}
        busy = PH.get('singleReplicaBusy') or []
        if busy:
            out.insert(min(2, len(out)), ('Add a second replica to shared APIs',
                       f'{len(busy)} production {plural(len(busy), "API is", "APIs are")} used by 3 or more consumers but run on '
                       f'one replica, led by {e(self.short(busy[0]["name"]))} ({busy[0]["consumers"]} consumers).'))
        if PH.get('java8'):
            out.append(('Move the Java 8 apps to Java 17', f'{len(PH["java8"])} production '
                        f'{plural(len(PH["java8"]), "app")} still run on Java 8. Plan them with the next runtime upgrade.'))
        if PH.get('testAppsInProd'):
            out.append(('Remove test apps from production', ', '.join(e(x) for x in PH['testAppsInProd'][:3])
                        + f' {plural(len(PH["testAppsInProd"]), "looks", "look")} like test or proof-of-concept deployments.'))
        if self.targets.get('CH1.0'):
            out.append(('Complete the move to CloudHub 2.0', f'{self.targets["CH1.0"]} deployments remain on CloudHub 1.0.'))
        return out[:6]

    def insights(self):
        K, RP = self.K, self.RP
        recs = [(r.get('title', ''), r.get('body', '')) for r in self.N['recs']] if self.N.get('recs') else self.default_recs()
        rec_html = ''.join(f'<div class="rec"><b>{i}</b><div><strong>{t}.</strong> {b}</div></div>' for i, (t, b) in enumerate(recs, 1))
        tiles = [kpi(len(self.shared), 'APIs called by 2+ components', 'the shared platform assets'),
                 kpi(f'{K["running"]/K["totalApps"]:.0%}' if K['totalApps'] else '—', 'Of deployments running',
                     f'{self.prod_run}/{self.prod_total} in production'),
                 kpi(self.client_total, 'Managed client applications')]
        if self.AD:
            tiles.append(kpi(f'{self.AD["coveragePct"]}%', 'Platform adoption', f'{self.AD["consumedApis"]} of {self.AD["totalApis"]} APIs used by client apps'))
        if self.DC:
            tiles.append(kpi(f'{self.DC["coveragePct"]}%', 'Deployment coverage', f'{self.DC["mapped"]} of {self.DC["prodTotal"]} prod apps in the graph'))
        if self.CF:
            tiles.append(kpi(e(self.CF['band']), 'Data confidence', f'{self.CF["orphanPct"]}% of APIs with no inbound calls'))
        rm = self.RM
        peer = (f'''<div class="card" style="margin-bottom:10px;padding:9px 14px">
    <h4 style="margin:0 0 4px">Peer-review metrics <span class="leg">the MuleSoft peer-review deck framing, for like-for-like comparison</span></h4>
    <div class="note" style="margin:0">API-led <b>{rm['apiLedPct']}%</b> ({rm['consumedApis']} of {rm['muleApps']} Mule apps have a consumer) · Reuse rate <b>{rm['reuseRate']}%</b> ({rm['reuseInstances']} of {rm['totalConsumers']} consumers are reuse) · Reusability <b>{rm['reusability']}%</b> ({rm['reusedApis']} of {rm['apis']} API-led APIs have 2+ consumers). These count only Experience, Process and System APIs, so they differ from the Reuse Analysis figures.</div>
  </div>''' if rm else '')
        sh = self.shared[:10]
        chart = (hbar_rows([(self.short(n['label']), n['in'], LAYER_COL.get(n['layer'], OTHER)) for n in sh],
                           max(n['in'] for n in sh), label_w=210) if sh else '<p class="note">No API is shared yet.</p>')
        return f'''
<section class="page">
  <div class="sec-head"><span class="sec-no">6 · MuleSoft Insights</span><h2>Observations and recommendations</h2></div>
  <div class="kpis" style="grid-template-columns:repeat({len(tiles)},1fr)">{''.join(tiles)}</div>
  {peer}
  <div class="cols2 top">
    <div class="card">
      <h4>Most-reused services</h4>{chart}
      <div class="note">Number of distinct components calling each API{f" (top {len(sh)} of {len(self.shared)})" if len(self.shared) > len(sh) else ""}.</div>
    </div>
    <div class="recs">{rec_html}{self.extra('insights')}</div>
  </div>
</section>'''

    def reuse(self):
        RP = self.RP
        if not RP:
            return ''
        r = RP['reuseRate']; bl = RP.get('byLayer') or {}
        layer_rows = [(k.capitalize(), round(bl[k]['reuseRate'] * 100, 1), LAYER_COL[k])
                      for k in ('experience', 'process', 'system', 'other') if k in bl]
        bg_rows = [(b['bg'], round(b['reuseRate'] * 100, 1),
                    GOOD if b['reuseRate'] >= .4 else FAIR if b['reuseRate'] >= .2 else POOR) for b in self.by_bg][:8]
        third = (f'<div class="card"><h4>Reuse rate by business group</h4>{hbar_rows(bg_rows, 100, width=300, label_w=150, unit="%")}</div>'
                 if len(bg_rows) >= 2 else '')
        bench = self.bench if self.bench is not None else .38
        bench_note = (f'Peer average from comparable {e(self.industry)} MuleSoft customers of a similar API estate size.'
                      if self.bench is not None and self.industry else
                      'Peer average from comparable MuleSoft customers.' if self.bench is not None else
                      'MuleSoft customer benchmark (no industry data available).')
        stage = self.maturity(r)
        nxt = {'Incubating': 'next stage: Developing at 20%', 'Developing': 'next stage: Industrialised at 40%',
               'Industrialised': 'next stage: Mature at 50%', 'Mature API-led': 'the highest stage (50%+)'}[stage]
        best = max(self.by_bg, key=lambda b: b['reuseRate']) if len(self.by_bg) >= 2 else None
        api_layers = [k for k in ('experience', 'process', 'system') if bl.get(k, {}).get('total', 0) >= 3]
        weak = min(api_layers, key=lambda k: bl[k]['reuseRate']) if api_layers else None
        if weak and bl[weak]['reuseRate'] < .5:
            inside = (f'{weak.capitalize()}-layer reuse is {bl[weak]["reuseRate"]:.0%}, the lowest of the three layers, '
                      f'and reusability is {RP["reusability"]:.1%}.')
        else:
            inside = (f'reuse is already above 50% in every API layer, so the focus is keeping it there as the estate '
                      f'grows. Reusability is {RP["reusability"]:.1%}.')
        opp = (self.N.get('reuse_opportunity')
               or (f'{e(best["bg"])} already reaches <b>{best["reuseRate"]:.1%}</b>. Bringing other groups onto the same shared '
                   f'APIs is the fastest route to the peer average.' if best and r < bench else
                   f'{e(self.name)} is above the peer average. The next gain is reuse inside the platform: {inside}' if r >= bench else
                   f'Lifting reuse from {r:.1%} toward the {bench:.1%} peer average means routing new builds through '
                   f'existing shared APIs.'))
        return f'''
<section class="page">
  <div class="sec-head"><span class="sec-no">7 · Reuse Analysis</span><h2>Production reuse</h2></div>
  <div class="kpis">
    {kpi(f'{r:.1%}', 'Reuse rate')}
    {kpi(f'{RP["reusability"]:.1%}', 'Reusability')}
    {kpi(f'{RP["reuseIndexApis"]:.2f}', 'Reuse index', 'consumers per active API')}
    {kpi(RP['consumers'], 'Total consumers', f'{RP["reuseInstances"]} reuse instances')}
    {kpi(RP['apisTotal'], 'APIs analysed')}
    {kpi(stage.replace(' API-led', ''), 'Maturity stage', nxt)}
  </div>
  <div class="card wide"><h4>{e(self.name)} against comparable customers</h4>{bench_bar(r, bench, self.name)}<div class="note">{bench_note}</div></div>
  <div class="{'cols3' if third else 'cols2'} top">
    <div class="card"><h4>How production APIs are consumed</h4>
      <div class="donut-row">{donut([(RP['consumedMore'], GOOD), (RP['consumedOnce'], FAIR_SOFT), (RP['consumedNone'], POOR_SOFT)], top=str(RP['apisTotal']), bot='APIs')}
      <div class="dleg"><div><i style="background:{GOOD}"></i><b>{RP['consumedMore']}</b> reused (2+ consumers)</div><div><i style="background:{FAIR_SOFT}"></i><b>{RP['consumedOnce']}</b> single consumer</div><div><i style="background:{POOR_SOFT}"></i><b>{RP['consumedNone']}</b> no consumers yet</div></div></div>
    </div>
    {third}
    <div class="card"><h4>Reuse rate by API layer</h4>{hbar_rows(layer_rows, 100, width=300, label_w=90, unit='%')}</div>
  </div>
  <div class="callout"><div class="callout-k">The opportunity</div><div>{opp}</div></div>
</section>'''

    def closing(self):
        recs = [(r.get('title', ''), r.get('body', '')) for r in self.N['recs']] if self.N.get('recs') else self.default_recs()
        steps = [('Clean up', recs[0][1] if recs else 'Retire unused applications.'),
                 ('Promote', 'Publish the shared APIs in Exchange as the standard building blocks.'),
                 ('Extend', 'Route new builds through existing shared APIs rather than point-to-point connections.'),
                 ('Measure', 'Re-run this analysis after the clean-up and track the reuse figures.')]
        step_html = ''.join(f'<div class="step"><span>0{i}</span><h4>{t}</h4><p>{b}</p></div>' for i, (t, b) in enumerate(steps, 1))
        conf = f' Data confidence for this export: <b>{e(self.CF["band"])}</b>.' if self.CF else ''
        return f'''
<section class="page closing">
  <div class="sec-head"><span class="sec-no">Next steps</span><h2>Turning the platform into reuse</h2></div>
  <div class="steps">{step_html}</div>
  <div class="method"><h4>About this report</h4>
    <p>Generated from the Anypoint Platform network-graph export of {e(self.extract)}, covering {len(self.RAW.get('orgs', []))} business {plural(len(self.RAW.get('orgs', [])), 'group')} and {len(self.RAW.get('envs', []))} environments. Integration flows and reuse come from the production dependency graph seen by Anypoint Visualizer; calls not seen by Visualizer are not included. <b>Reuse rate</b> = (consumers − APIs with consumers) ÷ consumers. <b>Reusability</b> = APIs with 2+ consumers ÷ APIs with consumers. <b>Reuse index</b> = consumers ÷ APIs with consumers. The peer average comes from MuleSoft's ANA industry benchmark data for comparable customers.{conf}</p>
  </div>
  <div class="end"><img class="logo" src="{self.logo}"><span>MuleSoft, a Salesforce company</span></div>
</section>'''

    def document(self):
        css = CSS_FILE.read_text('utf-8')
        for k, v in dict(BAND=BAND, INK=INK, LINE=LINE, MUTED=MUTED, NAVY=NAVY, ACCENT=ORD3, OKTX=ACCENT, RUN=RUN,
                         FOOTER=f'{self.name} · MuleSoft Integration Architecture Review').items():
            css = css.replace('$' + k, v)
        css += ('\n.t-val-inv { font-size: 9px; fill: #fff; font-weight: 700; font-family: inherit; }\n'
                '.bgc-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 9px; }\n'
                '.bgc { border: 1px solid ' + LINE + '; border-radius: 10px; padding: 9px 11px; }\n'
                '.bgc-h { display: flex; flex-direction: column; gap: 3px; font-size: 10.5pt; color: ' + NAVY + '; margin-bottom: 6px; }\n'
                '.pill-p, .pill-s { font-size: 7.5pt; font-weight: 700; padding: 1px 6px; border-radius: 8px; margin-right: 4px; }\n'
                '.pill-p { background: ' + NAVY + '; color: #fff; } .pill-s { background: ' + BAND + '; color: ' + MUTED + '; border: 1px solid ' + LINE + '; }\n'
                '.bgc-r { display: flex; justify-content: space-between; font-size: 8.6pt; margin: 3px 0; }\n'
                '.bgc-r span { color: ' + MUTED + '; } .bgc-r .mut { font-size: 8pt; }\n'
                '.bgc-bar { height: 7px; background: ' + BAND + '; border-radius: 4px; overflow: hidden; margin-bottom: 5px; }\n'
                '.bgc-bar i { display: block; height: 100%; background: ' + RUN + '; }\n'
                '.bgc-mix { display: flex; gap: 2px; height: 7px; border-radius: 4px; overflow: hidden; background: ' + BAND + '; }\n'
                '.bgc-mix i { display: block; height: 100%; }\n'
                '.compact .tile { font-size: 6.6pt; padding: 1px 5px; margin: 1px 2px 1px 0; }\n'
                '.compact .lane { margin-bottom: 4px; } .compact .lane-r { padding: 4px 6px; }\n'
                '.compact .badge { font-size: 6pt; } .compact .intro { margin-bottom: 6px; }\n'
                '.tile.more { border-left-color: transparent; color: ' + MUTED + '; font-style: italic; }\n')
        pages = [self.cover(), self.exec_summary(), self.overview(), self.business_groups(), self.api_led(),
                 self.flows(), self.inventory(), self.backends(), self.insights(), self.reuse(), self.closing()]
        body = ''.join(p for p in pages if p)
        return (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>{e(self.name)} - MuleSoft '
                f'Integration Architecture Review</title><style>{css}</style></head><body>{body}</body></html>')


def main():
    ap = argparse.ArgumentParser(description='Build the shareable PDF review for a customer export.')
    ap.add_argument('input', help='Anypoint network-graph export (.json)')
    ap.add_argument('-o', '--out-dir', help='output folder (default: alongside the input)')
    ap.add_argument('--customer', help='override the customer name')
    ap.add_argument('--notes', help='customer notes JSON (default: pdf_notes/<slug>.json next to the input, if present)')
    ap.add_argument('--browser', help='path to Chrome/Edge (default: auto-detect)')
    ap.add_argument('--keep-html', action='store_true', help='also keep the print HTML')
    ap.add_argument('--list-slots', action='store_true', help='list insight slot ids for notes files and exit')
    args = ap.parse_args()
    in_path = Path(args.input).expanduser().resolve()

    cmd = [sys.executable, str(BUILD_DATA), str(in_path)] + ([f'--customer={args.customer}'] if args.customer else [])
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                          env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    if proc.returncode != 0:
        sys.exit(f'build_data.py failed (exit {proc.returncode}) - no PDF written.')
    D = json.loads(proc.stdout.decode('utf-8'))
    RAW = json.loads(in_path.read_text('utf-8'))
    name = D['meta']['customer']
    slug = re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')
    notes_path = Path(args.notes) if args.notes else in_path.parent / 'pdf_notes' / f'{slug}.json'
    notes = {}
    if notes_path.exists():
        notes = json.loads(notes_path.read_text('utf-8'))
        log(f'  notes          : {notes_path.name}')
        ext = (D['meta'].get('extractOn') or '')[:10]
        if notes.get('asOf') and notes['asOf'][:10] != ext:
            log(f'  WARNING        : notes were written for the {notes["asOf"][:10]} extract but this export is '
                f'{ext}; review any hard-coded numbers in {notes_path.name}')
    tpl = TEMPLATE.read_text('utf-8')
    m = re.search(r'MULE_SVG = .<img src="(data:image/png;base64,[^"]+)"', tpl)
    logo = m.group(1) if m else ''

    rv = Review(D, RAW, notes, logo)
    doc = rv.document()
    if args.list_slots:
        print(f'Insight slots for {name} (use in pdf_notes/{slug}.json "insights"):')
        for k, t in rv.slots.items():
            print(f'  {k:22s} {re.sub("<[^>]+>", "", t)}')
        print('Extra-card pages: overview, business_groups, api_led, flows, inventory, backends, insights')
        print('Placeholders:', ', '.join('{' + k + '}' for k in rv.fields()))
        return

    out_dir = Path(args.out_dir).expanduser().resolve() if args.out_dir else in_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r'[^A-Za-z0-9._-]+', '_', name).strip('_.') or 'Customer'
    pdf_path = out_dir / f'{safe}_MuleSoft_Architecture_Review.pdf'
    browser = find_browser(args.browser)
    if not browser:
        sys.exit('No Chrome or Edge found to print the PDF. Install one, or pass --browser PATH.')
    with tempfile.TemporaryDirectory() as td:
        html_path = Path(td) / 'review.html'
        html_path.write_text(doc, encoding='utf-8', newline='\n')
        tmp_pdf = Path(td) / 'review.pdf'
        r = subprocess.run([browser, '--headless=new', '--disable-gpu', '--no-pdf-header-footer',
                            f'--user-data-dir={Path(td) / "profile"}', f'--print-to-pdf={tmp_pdf}',
                            html_path.as_uri()], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)
        if not tmp_pdf.exists() or tmp_pdf.stat().st_size < 1000:
            sys.exit(f'PDF printing failed (browser exit {r.returncode}).')
        try:
            shutil.copyfile(tmp_pdf, pdf_path)
        except PermissionError:
            sys.exit(f'Could not write {pdf_path} - is it open in a PDF viewer? Close it and re-run.')
        if args.keep_html:
            (out_dir / f'{safe}_MuleSoft_Architecture_Review.html').write_text(doc, encoding='utf-8', newline='\n')
    pages = len(re.findall(rb'/Type\s*/Page[^s]', pdf_path.read_bytes()))
    log(f'-- PDF WRITTEN: {pdf_path} ({pages} pages){" with notes" if notes else ""}')


if __name__ == '__main__':
    main()
