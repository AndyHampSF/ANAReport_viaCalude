#!/usr/bin/env python3
"""
build_data.py — mulesoft-estate-report skill, DATA object builder (v3.6.0)

Turns an Anypoint network-graph JSON export into the DATA object the template
injects. Written as a bundled script (not hand-authored per run) so the edge
remapping and backend consolidation are done ONCE, correctly, and every run is
reproducible.

Why this exists (v3.0.0, MAJOR):
  - Backend consolidation: raw FQDN endpoints -> business-friendly names
    (brand -> product -> domain-extraction). Internal Mule APIs are NEVER
    backends; their edges remap to the real Mule node.
  - Correct edge remapping: a single {node_id -> output_key} map covers every
    node. Earlier hand-written versions re-keyed backends but left edges
    pointing at the original UUID, silently dropping 100% of backend-based
    edges. That class of bug is now structurally impossible.
  - Reconciliation invariant: every raw edge is accounted for as kept /
    self-loop / duplicate-collapsed. The script FAILS LOUD if the arithmetic
    doesn't close, so flow counts can never be silently wrong again.
  - Flows KPI = count of consolidated, deduplicated edges (logical app->backend
    / app->app connections). A raw edge count is also reported for audit.

v3.2.0:
  - Peer benchmark: loads ANA Industry Data Matrix to derive a peer-set average
    reuse rate. OU categories resolved from data/customer_ou_map.json (substring
    match on masterOrgName). Peer set = same OU(s), APIs Total within 0.35–2.5×
    the customer's count, non-zero reuse data. Result emitted as
    reuseAnalysis.benchmarkAvg (null if matrix not found).

v3.3.0 (2026-10-05):
  - CH2/RTF internal hostnames: trailing 6-char suffix stripped before matching
    to Mule apps (app-name-97pqx7.internal-….cloudhub.io -> app-name).
  - '-pro-' recognised as the Process layer.
  - Backend overrides: Fibre Gateway, Salesforce Experience Cloud, Entra ID.
  - clientApps from production client groups only (export mixes in sandbox).
  - SCALING counted as running everywhere (RUNNING_STATES).
  - kpis.envs = distinct env names with apps (was distinct env types, max 2).
  - Input read as UTF-8 regardless of OS locale.

v3.4.0 (2026-10-05):
  - No third-party dependencies: the Industry Matrix .xlsx is read with the
    standard library (read_xlsx_sheet). Verified identical to the previous
    pandas implementation. Console messages are plain ASCII.

v3.4.1 (2026-10-28):
  - PRODUCT_MAP: 'arval.api.' -> 'Arval (BNP Paribas)'. .bnpparibas is a brand
    TLD, so domain extraction produced "Api API" / "Staging API" (JLR).

v3.5.0 (2026-10-29):
  - Benchmark ignores matrix rows whose OU, '# APIs Total' or reuse-rate cell
    is formatted strikethrough (the matrix owners strike out values that
    shouldn't be used). Detected from the .xlsx styles; stdlib only.
  - The source file, a content fingerprint and the struck-row count are printed.

v3.6.0 (2026-11-05): features adopted from a colleague's fork (v3.9.1), computed on our
  corrected layers and client data. All additive; existing DATA fields are unchanged:
  - businessGroups: per-business-group cards (apps, running, prod/sandbox, layer mix).
  - deploymentCoverage: production apps deployed vs present in the dependency graph
    ("isolated" apps). Inventory rows also gain `bg` and `isolated`.
  - adoption: share of the API-led catalogue consumed by client apps (+ Experience share).
  - confidence: High/Medium/Low data-quality band with reasons (orphan rate, export shape).
  - reuseMetrics: the MuleSoft peer-review three-metric framing (API-led %, reuse rate,
    reusability) for comparison with peer-review decks.
  - --customer=NAME overrides the customer / report name (default: masterOrgName).
  - Unidentified inbound traffic (http node, no host, clientId OTHER, outbound only;
    "External Traffic", TalkTalk's "Partner") is a consumer, not a backend.
  - Topology-only exports (no apps[]) now derive envRows, inventory and a single
    business group from the Mule node names (env token anywhere in the name), so the
    env chart and inventory aren't blank. Standard exports are unaffected.

Usage:
    python3 build_data.py <input.json> [--customer=NAME]

Prints a human-readable reconciliation report to stderr and the DATA object as
JSON to stdout. Normally invoked via build_report.py, which also injects DATA
into the HTML template.
"""
import json
import os
import re
import sys
from collections import Counter, defaultdict

# ─────────────────────────────────────────────────────────────────────────────
# Backend consolidation (4-tier). See BACKEND_CONSOLIDATION_STRATEGY.md.
# ─────────────────────────────────────────────────────────────────────────────

# Tier 1 — brand recognition (substring match on the raw label, lowercased).
BRAND_MAP = [
    # Specific overrides first — these would otherwise hit a generic keyword
    # below ('gateway') or extract a meaningless domain ('Site', 'Microsoft').
    ('fibregateway',    'Fibre Gateway'),
    ('my.site.com',     'Salesforce Experience Cloud'),
    ('login.microsoft', 'Microsoft Entra ID'),
    ('salesforce',   'Salesforce'),
    ('force.com',    'Salesforce'),
    ('okta',         'Okta'),
    ('dynamodb',     'AWS DynamoDB'),
    ('s3.amazon',    'AWS S3'),
    ('amazonaws',    'AWS'),
    ('azurewebsites','Azure'),
    ('azure-storage','Azure Blob Storage'),
    ('azure',        'Azure'),
    ('blob.core',    'Azure Blob Storage'),
    ('outlook',      'Outlook 365'),
    ('sharepoint',   'SharePoint'),
    ('sftp',         'SFTP'),
    ('peoplesoft',   'PeopleSoft (WSC)'),
    ('wsc',          'PeopleSoft (WSC)'),
    ('crypto',       'Crypto Service'),
    ('bedrock',      'AWS Bedrock'),
    ('oanda',        'Oanda FX'),
    ('gateway',      'API Gateway'),
]

# Tier 2 — known business products / partners (substring match, first match wins).
# The first few are targeted overrides for endpoints whose bare domain extraction
# reads as cryptic ("Microsoftonline API", "Paybyphoneapis API"). Keep this list
# small and specific — add an entry only when the extracted name is genuinely wrong,
# not merely unfamiliar.
PRODUCT_MAP = [
    ('microsoftonline', 'Microsoft Entra ID'),
    ('paybyphone',      'PayByPhone'),
    ('vertexcloud',     'Vertex (Tax)'),
    # .bnpparibas is a brand TLD, so domain extraction yields "Api"/"Staging".
    # Match 'arval.api.' exactly: JLR's own *-finance-arval-* Mule hostnames
    # and api-ce.bnpparibas-pf.com (a different service) must not match.
    ('arval.api.',      'Arval (BNP Paribas)'),
    ('corpayone',    'Corpay One'),
    ('corpay-one',   'Corpay One'),
    ('corpay',       'Corpay'),
    ('iconnectdata', 'iConnectData'),
    ('hotelbeds',    'HotelbedS API'),
    ('hotelbed',     'HotelbedS API'),
    ('cambridge',    'Cambridgelink'),
    ('transafe',     'Transafe'),
    ('tokenguard',   'Tokenguard'),
    ('derbysof',     'Derbysof'),
    ('cfnnet',       'CFN Network'),
    ('fleetcor',     'FleetCor API'),
]

# Simple 'other'/'db' node labels that are already clean brand words.
SIMPLE_LABEL_MAP = {
    'dynamodb':      'AWS DynamoDB',
    's3':            'AWS S3',
    'sqs':           'AWS SQS',
    'amqp':          'AMQP (Message Queue)',
    'email':         'Email / SMTP',
    'crypto':        'Crypto Service',
    'wsc':           'PeopleSoft (WSC)',
    'sftp':          'SFTP',
    'azure-storage': 'Azure Blob Storage',
    'ms-bedrock':    'AWS Bedrock',
    'database':      'Database',
    'external traffic': 'External Traffic',
    'other':         'External Service',
}

# App statuses counted as running — shared by the KPI and the env chart so the
# two always agree. SCALING = mid-scale but serving traffic.
RUNNING_STATES = ('RUNNING', 'STARTED', 'SCALING')

# Multi-part TLDs so domain extraction picks the org label, not the TLD chunk.
MULTI_TLDS = {'co.uk', 'com.au', 'co.nz', 'co.za', 'com.br', 'co.in', 'com.mx'}


def _icon_for(raw_lower):
    """Icon key from the RAW (pre-consolidation) label."""
    table = [
        ('okta', 'okta'), ('salesforce', 'salesforce'), ('force.com', 'salesforce'),
        ('sharepoint', 'sharepoint'), ('azure', 'azure'), ('outlook', 'outlook'),
        ('sftp', 'sftp'), ('smb', 'smb'), ('file server', 'smb'),
        ('crypto', 'crypto'), ('wsc', 'peoplesoft'), ('peoplesoft', 'peoplesoft'),
        ('dynamodb', 'service'), ('bedrock', 'ai'), ('ms-inference', 'ai'),
        ('oanda', 'oanda'), ('gateway', 'gateway'), ('anypoint', 'mulesoft'),
        ('mulesoft', 'mulesoft'), ('timesheet', 'timesheet'),
        ('external traffic', 'web'), ('client', 'client'),
    ]
    for kw, ic in table:
        if kw in raw_lower:
            return ic
    return 'service'


def _extract_domain(raw):
    """Tier 3 — pull the organisation label out of an FQDN/URL.

    apiprd.allstaronline.co.uk -> 'Allstaronline'
    drive-api.plugsurfing.com  -> 'Plugsurfing'
    api.iconnectdata.com       -> 'Iconnectdata'
    """
    host = raw.lower().split('/')[0].split(':')[0].strip()
    parts = host.split('.')
    if len(parts) < 2:
        return raw.split('.')[0].replace('-', ' ').replace('_', ' ').title()
    last2 = '.'.join(parts[-2:])
    if last2 in MULTI_TLDS and len(parts) >= 3:
        org = parts[-3]
    else:
        org = parts[-2]
    return org.replace('-', ' ').replace('_', ' ').title()


def consolidate_backend(raw_label):
    """Map a raw backend endpoint to a business-friendly name (4-tier)."""
    low = raw_label.lower().strip()

    if low in SIMPLE_LABEL_MAP:
        return SIMPLE_LABEL_MAP[low]
    for kw, name in BRAND_MAP:
        if kw in low:
            return name
    for kw, name in PRODUCT_MAP:
        if kw in low:
            return name
    if '.' in low or '/' in low:
        return _extract_domain(raw_label) + ' API'
    return raw_label.replace('-', ' ').replace('_', ' ').title()


def backend_category(friendly):
    f = friendly.lower()
    if any(k in f for k in ('aws', 'azure', 's3', 'dynamodb', 'blob')):
        return 'Cloud Service'
    if 'salesforce' in f:
        return 'CRM / SaaS'
    if 'okta' in f:
        return 'Identity / SSO'
    if any(k in f for k in ('sftp', 'smb', 'file')):
        return 'File Transfer'
    if any(k in f for k in ('email', 'smtp', 'amqp', 'sqs', 'queue')):
        return 'Messaging / Email'
    if 'peoplesoft' in f:
        return 'ERP / HR'
    if 'gateway' in f:
        return 'Infrastructure'
    if 'database' in f:
        return 'Database'
    return 'External System / Partner'


# ─────────────────────────────────────────────────────────────────────────────
# Schema normalisation — handle both the standard export and nodes/edges-only.
# ─────────────────────────────────────────────────────────────────────────────

def normalise(raw):
    """Return (nodes, edges, apps, envs, clientgroup, master, orgs, sandbox_dep)."""
    if 'production' in raw and isinstance(raw['production'], dict):
        dep = raw['production'].get('dependencies', {})
        nodes = dep.get('nodes', [])
        edges = dep.get('edges', [])
        clientgroup = raw['production'].get('clientgroup', [])
    else:
        nodes = raw.get('nodes', [])
        edges = raw.get('edges', [])
        clientgroup = raw.get('clientgroup', [])

    sandbox_dep = None
    if 'sandbox' in raw and isinstance(raw['sandbox'], dict):
        sandbox_dep = raw['sandbox'].get('dependencies', {})

    apps = raw.get('apps', [])
    envs = raw.get('envs', [])
    master = raw.get('masterOrg', {}) or {}
    orgs = [o.get('orgName') for o in raw.get('orgs', []) if o.get('orgName')]
    return nodes, edges, apps, envs, clientgroup, master, orgs, sandbox_dep


def compute_reuse_stats_by_org(dep_nodes, dep_edges, master_org_name, org_map):
    """Compute per-BG reuse stats from production graph nodes/edges.

    Each node carries organizationId; org_map maps orgId -> orgName.
    Returns a list of per-BG dicts sorted by APIs descending, excluding BGs
    with zero APIs. Title format: '<master> → <bg>' for hierarchy clarity.
    """
    if not dep_nodes:
        return []

    node_by_id = {n['id']: n for n in dep_nodes}
    mule_nodes = [n for n in dep_nodes if n.get('type') == 'mule']
    if not mule_nodes:
        return []

    mule_ids = {n['id'] for n in mule_nodes}

    # Expand clientGroup consumers
    incoming = defaultdict(int)
    for e in dep_edges:
        s = e.get('sourceId') or e.get('source')
        t = e.get('targetId') or e.get('target')
        if t in mule_ids:
            src = node_by_id.get(s, {})
            n_clients = (src.get('numberOfClientApplications') or 1) if src.get('type') == 'clientGroup' else 1
            incoming[t] += n_clients

    # Group mule nodes by org
    by_org = defaultdict(list)
    for n in mule_nodes:
        org_name = org_map.get(n.get('organizationId', ''), '')
        by_org[org_name].append(n)

    results = []
    for org_name, org_nodes in by_org.items():
        ids = {n['id'] for n in org_nodes}
        apis_total = len(ids)
        consumed_more = sum(1 for i in ids if incoming[i] > 1)
        consumed_once = sum(1 for i in ids if incoming[i] == 1)
        consumed_none = sum(1 for i in ids if incoming[i] == 0)
        total_consumers = sum(incoming[i] for i in ids)
        apis_with = consumed_more + consumed_once
        reuse_instances = total_consumers - apis_with
        reuse_rate = round(reuse_instances / total_consumers, 4) if total_consumers else 0

        per_app = sorted(
            [{'name': n['label'], 'consumers': incoming[n['id']],
              'layer': layer_of_node(n)}
             for n in org_nodes if incoming[n['id']] > 0],
            key=lambda x: -x['consumers']
        )

        title = f'{master_org_name} → {org_name}' if master_org_name and org_name and org_name != master_org_name else (org_name or master_org_name or 'Unknown')

        results.append({
            'bg': org_name,
            'title': title,
            'apisTotal': apis_total,
            'consumedMore': consumed_more,
            'consumedOnce': consumed_once,
            'consumedNone': consumed_none,
            'consumers': total_consumers,
            'reuseInstances': reuse_instances,
            'reuseRate': reuse_rate,
            'reusability': round(consumed_more / (apis_total - consumed_none), 4) if (apis_total - consumed_none) > 0 else 0,
            'perApp': per_app,
        })

    return sorted([r for r in results if r['apisTotal'] > 0], key=lambda x: -x['apisTotal'])


def compute_reuse_stats(dep_nodes, dep_edges, apps, envtype_filter=None, org_map=None):
    """Compute reuse analysis for a dependency graph section.

    Expands clientGroup nodes by numberOfClientApplications so each client
    application counts as an individual consumer (matching ANA tool behaviour).
    envtype_filter: if given ('production'|'sandbox'), used to count total
    deployed apps for the accuracy percentage.
    """
    if not dep_nodes:
        return None

    node_by_id = {n['id']: n for n in dep_nodes}
    mule_nodes = [n for n in dep_nodes if n.get('type') == 'mule']
    if not mule_nodes:
        return None
    mule_ids = {n['id'] for n in mule_nodes}

    # Count incoming consumers per mule node, expanding clientGroup
    incoming = defaultdict(int)
    outgoing = defaultdict(set)
    for e in dep_edges:
        s = e.get('sourceId') or e.get('source')
        t = e.get('targetId') or e.get('target')
        if s in mule_ids and t != s:
            outgoing[s].add(t)
        if t in mule_ids:
            src = node_by_id.get(s, {})
            n_clients = (src.get('numberOfClientApplications') or 1) if src.get('type') == 'clientGroup' else 1
            incoming[t] += n_clients

    consumed_more = sum(1 for n in mule_nodes if incoming[n['id']] > 1)
    consumed_once = sum(1 for n in mule_nodes if incoming[n['id']] == 1)
    consumed_none = sum(1 for n in mule_nodes if incoming[n['id']] == 0)
    total_consumers = sum(incoming[n['id']] for n in mule_nodes)
    apis_with_consumers = consumed_more + consumed_once
    reuse_instances = total_consumers - apis_with_consumers

    apis_total = len(mule_nodes)

    # Layer × consumer-status breakdown
    layer_stats = {}
    for lyr in ('experience', 'process', 'system', 'other'):
        ids_in_layer = [n['id'] for n in mule_nodes if layer_of_node(n) == lyr]
        if not ids_in_layer:
            continue
        lmore = sum(1 for i in ids_in_layer if incoming[i] > 1)
        lonce = sum(1 for i in ids_in_layer if incoming[i] == 1)
        lnone = sum(1 for i in ids_in_layer if incoming[i] == 0)
        lactive = lmore + lonce
        layer_stats[lyr] = {
            'total': len(ids_in_layer),
            'more': lmore, 'once': lonce, 'none': lnone,
            'reuseRate': round(lmore / lactive, 4) if lactive else 0,
        }

    # Per-app consumer detail for the ranked list
    per_app = sorted(
        [{'name': n['label'], 'consumers': incoming[n['id']],
          'layer': layer_of_node(n)}
         for n in mule_nodes if incoming[n['id']] > 0],
        key=lambda x: -x['consumers']
    )

    # APIs with no consumers: what (if anything) each one calls, to tell batch /
    # scheduled / event-driven apps (call out, nothing calls in) from apps with no
    # observed dependencies at all (idle, new, or not seen by Visualizer).
    status_by_app = {}
    for a in apps or []:
        if a.get('envtype') == 'production' and a.get('appname'):
            st = a.get('status') or ''
            if st in RUNNING_STATES or a['appname'] not in status_by_app:
                status_by_app[a['appname']] = st
    no_consumers = []
    for n in mule_nodes:
        if incoming[n['id']]:
            continue
        tgts = [node_by_id.get(t, {}) for t in outgoing[n['id']]]
        lbl = n.get('label') or ''
        no_consumers.append({
            'name': lbl,
            'layer': layer_of_node(n),
            'bg': (org_map or {}).get(n.get('organizationId'), ''),
            'calls': len(tgts),
            'callsMule': sum(1 for t in tgts if t.get('type') == 'mule'),
            'status': status_by_app.get(lbl) or status_by_app.get(n.get('appName') or '', ''),
        })
    no_consumers.sort(key=lambda x: (x['calls'] == 0, x['layer'], x['name']))

    reuse_rate = round(reuse_instances / total_consumers, 4) if total_consumers else 0
    reuse_index_apis = round(total_consumers / apis_with_consumers, 4) if apis_with_consumers else 0
    reuse_index_all  = round(total_consumers / apis_total, 4) if apis_total else 0
    reusability      = round(consumed_more / (apis_total - consumed_none), 4) if (apis_total - consumed_none) > 0 else 0

    return {
        'apisTotal':       apis_total,
        'consumedMore':    consumed_more,
        'consumedOnce':    consumed_once,
        'consumedNone':    consumed_none,
        'consumers':       total_consumers,
        'reuseInstances':  reuse_instances,
        'reuseRate':       reuse_rate,
        'reuseIndexApis':  reuse_index_apis,
        'reuseIndexAll':   reuse_index_all,
        'reusability':     reusability,
        'perApp':          per_app,
        'noConsumers':     no_consumers,
        'byLayer':         layer_stats,
    }


# Environment tokens found in Mule app names (used only when apps[] is absent).
ENV_NAME = {
    'prod': 'Production', 'prd': 'Production', 'production': 'Production',
    'sit': 'SIT', 'qa': 'QA', 'dev': 'Development', 'uat': 'UAT', 'test': 'Test',
    'sandbox': 'Sandbox', 'nonprod': 'Non-Prod', 'stage': 'Staging', 'staging': 'Staging',
    'stg': 'Staging', 'perf': 'Performance', 'pve': 'PVE', 'hotfix': 'Hotfix',
}
PROD_TOKENS = {'prod', 'prd', 'production'}


def env_of_name(label):
    """(env name, envtype) from a Mule app name, for topology-only exports.

    Scans every hyphen token, so env-first (prod-us-acme-payments-sapi) and
    org-first (mm-crm-salesforce-exp-prd-v1) names both resolve. When several
    tokens match (a domain word like 'dev'), prefer the one just before a
    trailing version segment, then a production token, otherwise the first.
    Default: Production.
    """
    toks = (label or '').lower().split('-')
    hits = [(i, t) for i, t in enumerate(toks) if t in ENV_NAME]
    if not hits:
        return 'Production', 'production'
    if len(hits) > 1:
        ver = [(i, t) for i, t in hits
               if i + 1 < len(toks) and toks[i + 1][:1] == 'v' and toks[i + 1][1:].isdigit()]
        # an explicit production token wins over a domain word like 'test'
        # (network-test-pxc-prod is a production app)
        prod_hits = [(i, t) for i, t in hits if t in PROD_TOKENS]
        _, tok = (ver or prod_hits or hits)[0]
    else:
        _, tok = hits[0]
    return ENV_NAME[tok], ('production' if tok in PROD_TOKENS else 'sandbox')


def layer_of_node(n):
    """Layer for a graph node: Visualizer's layer label when it names an API-led layer,
    otherwise the name rules. Used everywhere a node's layer is shown or counted, so the
    API-Led and Reuse tabs always agree."""
    lab = ((n.get('layer') or {}).get('label') or '').lower()
    if lab in ('experience', 'process', 'system'):
        return lab
    return layer_of_name(n.get('label') or '')


def layer_of_name(name):
    """Infer API-led layer from app name conventions."""
    n = (name or '').lower()
    if n.endswith('-eapi') or '-eapi-' in n or 'exp-' in n or n.startswith('sgn-e'):
        return 'experience'
    if n.endswith('-papi') or '-papi-' in n or 'prc-' in n or '-pro-' in n or n.startswith('sgn-p'):
        return 'process'
    if n.endswith('-sapi') or '-sapi-' in n or 'sys-' in n or n.startswith('sgn-s'):
        return 'system'
    return 'other'


# ─────────────────────────────────────────────────────────────────────────────
# Peer benchmark — ANA Industry Data Matrix
# ─────────────────────────────────────────────────────────────────────────────

# Paths relative to this script's directory
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR    = os.path.join(_SCRIPT_DIR, '..', 'data')
_MATRIX_PATH = os.path.join(_DATA_DIR, 'ANA Industry Data Matrix - Golden Template.xlsx')
_OU_MAP_PATH = os.path.join(_DATA_DIR, 'customer_ou_map.json')

# API count band: peer must have between PEER_LOW and PEER_HIGH times the
# customer's API count to be included. Wider = more peers, less precise.
_PEER_RATIO_LOW  = 0.35
_PEER_RATIO_HIGH = 2.50
# Minimum peers needed to trust the average; fall back to full-OU average if below.
_MIN_PEERS = 5


def _resolve_ous(customer_name):
    """Return list of OU category strings for this customer.

    Looks up customer_ou_map.json via case-insensitive substring match on the
    customer name. Falls back to None (use all rows) if no mapping found.
    """
    try:
        with open(_OU_MAP_PATH, encoding='utf-8') as f:
            ou_map = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None

    name_lower = (customer_name or '').lower()
    for key, ous in ou_map.items():
        if key.startswith('_'):
            continue
        if key.lower() in name_lower or name_lower in key.lower():
            return ous if isinstance(ous, list) else [ous]
    return None


_XLSX_NS = {
    'm': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'rel': 'http://schemas.openxmlformats.org/package/2006/relationships',
}


def _col_index(cell_ref):
    """'AB12' -> 27 (0-based column index)."""
    idx = 0
    for ch in cell_ref:
        if not ch.isalpha():
            break
        idx = idx * 26 + (ord(ch.upper()) - 64)
    return idx - 1


def _struck_styles(z, ns, ET):
    """Indexes of cell styles (cellXfs) whose font is struck through."""
    if 'xl/styles.xml' not in z.namelist():
        return set()
    st = ET.fromstring(z.read('xl/styles.xml'))
    struck_fonts = set()
    for i, f in enumerate(st.iterfind('m:fonts/m:font', ns)):
        s = f.find('m:strike', ns)
        if s is not None and s.get('val', '1') not in ('0', 'false'):
            struck_fonts.add(i)
    return {i for i, xf in enumerate(st.iterfind('m:cellXfs/m:xf', ns))
            if int(xf.get('fontId', 0)) in struck_fonts}


def read_xlsx_sheet(path, sheet_name, with_strike=False):
    """Read one worksheet of an .xlsx into a list of rows (lists of cell values).

    Standard library only (zipfile + ElementTree), so the skill needs no
    third-party packages on any OS. Values: float for numeric cells, str for
    text/error cells, None for empty. Formula cells yield their cached value
    (as Excel last saved it), matching pandas/openpyxl data_only behaviour.

    with_strike=True also returns, per row, the set of column indexes whose
    cell is formatted strikethrough (whole-cell font, or any struck rich-text
    run): returns (rows, struck_rows).
    """
    import zipfile
    import xml.etree.ElementTree as ET
    ns = _XLSX_NS
    with zipfile.ZipFile(path) as z:
        struck_xf = _struck_styles(z, ns, ET)
        wb = ET.fromstring(z.read('xl/workbook.xml'))
        rid = None
        for s in wb.iterfind('m:sheets/m:sheet', ns):
            if s.get('name') == sheet_name:
                rid = s.get(f'{{{ns["r"]}}}id')
        if rid is None:
            raise KeyError(f"worksheet '{sheet_name}' not found")
        rels = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
        target = next(r.get('Target') for r in rels.iterfind('rel:Relationship', ns)
                      if r.get('Id') == rid)
        sheet_path = target.lstrip('/') if target.startswith('/') else 'xl/' + target

        shared, shared_struck = [], set()
        if 'xl/sharedStrings.xml' in z.namelist():
            for k, si in enumerate(ET.fromstring(z.read('xl/sharedStrings.xml')).iterfind('m:si', ns)):
                # Plain <t>, or rich-text runs <r><t>; phonetic <rPh> runs are ignored.
                parts = [t.text or '' for t in si.findall('m:t', ns)]
                parts += [t.text or '' for t in si.findall('m:r/m:t', ns)]
                shared.append(''.join(parts))
                if any(s.get('val', '1') not in ('0', 'false')
                       for s in si.findall('m:r/m:rPr/m:strike', ns)):
                    shared_struck.add(k)

        rows, struck_rows = [], []
        for row in ET.fromstring(z.read(sheet_path)).iterfind('m:sheetData/m:row', ns):
            vals, struck = {}, set()
            for c in row.iterfind('m:c', ns):
                t = c.get('t', 'n')
                v = c.find('m:v', ns)
                if int(c.get('s', 0)) in struck_xf or (
                        t == 's' and v is not None and v.text and int(v.text) in shared_struck):
                    struck.add(_col_index(c.get('r')))
                if t == 'inlineStr':
                    val = ''.join(x.text or '' for x in c.iter(f'{{{ns["m"]}}}t'))
                elif v is None or v.text is None:
                    val = None
                elif t == 's':
                    val = shared[int(v.text)]
                elif t in ('str', 'e'):
                    val = v.text
                elif t == 'b':
                    val = v.text == '1'
                else:
                    val = float(v.text)
                if val is not None and val != '':
                    vals[_col_index(c.get('r'))] = val
            if vals:
                width = max(vals) + 1
                rows.append([vals.get(i) for i in range(width)])
                struck_rows.append(struck)
    return (rows, struck_rows) if with_strike else rows


def _to_number(v):
    """Numeric value or None — mirrors pandas.to_numeric(errors='coerce')."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, float):
        return v
    try:
        return float(str(v).strip())
    except ValueError:
        return None


def _pairwise_sum(a, lo=0, n=None):
    """Float sum in numpy's pairwise order, so means are bit-identical to the
    pandas implementation this replaced (a naive or exact sum can round a
    4-dp benchmark differently when the mean sits on a .xxxx5 boundary)."""
    if n is None:
        n = len(a)
    if n < 8:
        res = 0.0
        for i in range(lo, lo + n):
            res += a[i]
        return res
    if n <= 128:
        r = a[lo:lo + 8]
        i = 8
        while i < n - (n % 8):
            for j in range(8):
                r[j] += a[lo + i + j]
            i += 8
        res = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]))
        while i < n:
            res += a[lo + i]
            i += 1
        return res
    n2 = n // 2
    n2 -= n2 % 8
    return _pairwise_sum(a, lo, n2) + _pairwise_sum(a, lo + n2, n - n2)


def load_matrix_peers(report=None):
    """Return [(ou, apis_total, reuse_rate)] from the matrix's 'Data Tab'.

    Rows with 0 / missing APIs or a non-numeric reuse rate are dropped, and so
    are rows where the OU, API count or reuse rate cell is formatted
    strikethrough - the matrix owners strike out values that shouldn't be
    used. If `report` is a dict, it receives {'struck': n} (rows that would
    otherwise have been used). Raises on a missing file or unexpected layout.
    """
    rows, struck_rows = read_xlsx_sheet(_MATRIX_PATH, 'Data Tab', with_strike=True)
    header = [str(h) if h is not None else '' for h in rows[0]]
    want = {'OU': None, '# APIs Total': None, '% Reuse rate (over all APIs)': None}
    for i, h in enumerate(header):
        if h in want and want[h] is None:     # first occurrence, as pandas does
            want[h] = i
    missing = [k for k, v in want.items() if v is None]
    if missing:
        raise KeyError(f'matrix columns not found: {missing}')
    i_ou, i_api, i_rate = want['OU'], want['# APIs Total'], want['% Reuse rate (over all APIs)']

    peers, struck_count = [], 0
    for r, struck in zip(rows[1:], struck_rows[1:]):
        cell = lambda i: r[i] if i < len(r) else None
        apis = _to_number(cell(i_api)) or 0.0
        rate = _to_number(cell(i_rate))
        if apis > 0 and rate is not None:
            if struck & {i_ou, i_api, i_rate}:
                struck_count += 1
                continue
            peers.append((cell(i_ou), apis, rate))
    if report is not None:
        report['struck'] = struck_count
    return peers


def compute_benchmark(customer_name, customer_api_count):
    """Return peer-set average reuse rate (0-1) or None if unavailable.

    Column used: '% Reuse rate (over all APIs)' (column M in the matrix).
    Peer selection:
      1. Filter to matching OU categories (from customer_ou_map.json).
      2. Filter to rows where APIs Total is within PEER_RATIO band.
      3. Exclude zero-data rows and non-numeric reuse rate values.
      4. If fewer than MIN_PEERS remain, broaden to full OU set (no API count filter).
    """
    if not os.path.exists(_MATRIX_PATH):
        print(f'  benchmark: matrix not found at {_MATRIX_PATH} - skipping', file=sys.stderr)
        return None
    try:
        info = {}
        df = load_matrix_peers(info)
    except Exception as e:
        print(f'  benchmark: could not read matrix ({e}) - skipping', file=sys.stderr)
        return None
    # Content fingerprint, not file date: a git checkout resets file dates and
    # the downloaded .xlsx carries no saved-date metadata.
    import hashlib
    with open(_MATRIX_PATH, 'rb') as f:
        fingerprint = hashlib.sha256(f.read()).hexdigest()[:8]
    print(f'  benchmark source: data/{os.path.basename(_MATRIX_PATH)} [id {fingerprint}]; '
          f'{len(df)} usable peer rows, {info.get("struck", 0)} struck-through rows ignored',
          file=sys.stderr)

    ous = _resolve_ous(customer_name)

    def _avg(subset):
        if not subset:
            return None
        return round(_pairwise_sum([p[2] for p in subset]) / len(subset), 4)

    ou_df = [p for p in df if p[0] in ous] if ous else df

    lo = customer_api_count * _PEER_RATIO_LOW
    hi = customer_api_count * _PEER_RATIO_HIGH
    peer_df = [p for p in ou_df if lo <= p[1] <= hi]

    if len(peer_df) >= _MIN_PEERS:
        avg = _avg(peer_df)
        print(f'  benchmark: {len(peer_df)} peers (OU+API band) -> avg reuse rate {avg:.1%}', file=sys.stderr)
        return avg

    if len(ou_df) >= _MIN_PEERS:
        avg = _avg(ou_df)
        print(f'  benchmark: API band too narrow ({len(peer_df)} peers); broadened to full OU ({len(ou_df)} peers) -> avg {avg:.1%}', file=sys.stderr)
        return avg

    avg = _avg(df)
    if avg is None:
        print('  benchmark: matrix has no usable rows - skipping', file=sys.stderr)
        return None
    print(f'  benchmark: OU set too small ({len(ou_df)} peers); using all industries ({len(df)} rows) -> avg {avg:.1%}', file=sys.stderr)
    return avg


def strip_host(label):
    """Recover an app stem from an internal hostname."""
    if not label:
        return label
    # first dns label, minus any trailing -<hash> only when it looks like a hash
    stem = label.split('.')[0]
    return stem


def main():
    # --customer=NAME overrides the report/customer name (default: masterOrgName)
    customer_override, positional = None, []
    for a in sys.argv[1:]:
        if a.startswith('--customer='):
            customer_override = a.split('=', 1)[1].strip() or None
        elif not a.startswith('--'):
            positional.append(a)
    if not positional:
        sys.exit('usage: build_data.py <input.json> [--customer=NAME]')
    path = positional[0]
    with open(path, encoding='utf-8') as f:
        raw = json.load(f)

    nodes, edges, apps, envs, clientgroup, master, orgs, sandbox_dep = normalise(raw)

    # Build org lookup from raw export (needed for per-BG breakdown)
    raw_orgs = raw.get('orgs', [])
    org_id_to_name = {o['orgId']: o.get('orgName', '') for o in raw_orgs if 'orgId' in o}
    master_org_name = customer_override or master.get('masterOrgName', '')

    by_id = {n['id']: n for n in nodes}
    mule_labels = {n.get('label', '') for n in nodes if n.get('type') == 'mule'}

    # ── Classify nodes; build node_id -> output_key map ────────────────────
    LAYER = {'experience': [], 'process': [], 'system': []}
    layer_other = []
    out_nodes = {}          # output_key -> node dict
    id_to_key = {}          # raw node id -> output_key
    backend_members = defaultdict(list)   # friendly -> [raw labels]

    layer_of = layer_of_node

    # First pass: mule nodes (own an output key = their id)
    for n in nodes:
        if n.get('type') != 'mule':
            continue
        lab = n.get('label', n['id'])
        lyr = layer_of(n)
        tag = ''
        tags = n.get('tags') or []
        if tags and isinstance(tags[0], dict):
            tag = tags[0].get('label', '')
        node = {'key': n['id'], 'label': lab, 'kind': 'mule', 'layer': lyr,
                'tag': tag, 'category': '', 'icon': 'mule', 'in': 0, 'out': 0}
        out_nodes[n['id']] = node
        id_to_key[n['id']] = n['id']
        if lyr in LAYER:
            LAYER[lyr].append(node)
        else:
            layer_other.append(node)

    # clientGroup -> single merged consumer
    cg_ids = [n['id'] for n in nodes if n.get('type') == 'clientGroup']
    total_clients = sum(n.get('numberOfClientApplications', 1)
                        for n in nodes if n.get('type') == 'clientGroup')
    consumers = []
    if cg_ids:
        ckey = 'consumer-merged'
        lbl = f'{total_clients} Client App{"s" if total_clients != 1 else ""}'
        merged = {'key': ckey, 'label': lbl, 'kind': 'consumer', 'layer': 'consumer',
                  'tag': '', 'category': '', 'icon': 'client', 'in': 0, 'out': 0}
        consumers = [merged]
        out_nodes[ckey] = merged
        for cid in cg_ids:
            id_to_key[cid] = ckey

    # Unidentified inbound traffic: Visualizer's catch-all node for callers with no
    # recognised client ID ("External Traffic", sometimes renamed, e.g. TalkTalk's
    # "Partner"). Signature: http node, no host, clientId OTHER, no inbound edges.
    # It's a consumer, not a backend.
    _has_in = {e.get('targetId') or e.get('target') for e in edges}
    def _is_external_traffic(n):
        return (n.get('type') == 'http' and not n.get('host')
                and str(n.get('clientId', '')).upper() == 'OTHER'
                and n['id'] not in _has_in)
    for n in nodes:
        if _is_external_traffic(n):
            ekey = 'consumer-ext-' + n['id']
            lbl = n.get('label') or 'External Traffic'
            out_nodes[ekey] = {'key': ekey, 'label': lbl, 'kind': 'consumer', 'layer': 'consumer',
                               'tag': '', 'category': 'Unidentified inbound traffic',
                               'icon': 'web', 'in': 0, 'out': 0}
            consumers.append(out_nodes[ekey])
            id_to_key[n['id']] = ekey

    # backend candidates: http / other / db / sfdc
    internal_remapped = 0
    for n in nodes:
        t = n.get('type')
        if t not in ('http', 'other', 'db', 'sfdc'):
            continue
        if n['id'] in id_to_key:          # already classified (e.g. external traffic)
            continue
        raw_label = n.get('label', '') or ''
        stem = strip_host(raw_label)
        # CloudHub 2 / RTF internal hostnames append a 6-char suffix:
        # pro-whs-sys-dise-api-v1-97pqx7.internal-….cloudhub.io
        stem_nohash = re.sub(r'-[a-z0-9]{6}$', '', stem)
        # Internal Mule API reached via a hostname? -> remap to the real app.
        target = next((c for c in (stem, raw_label, stem_nohash) if c in mule_labels), None)
        if target:
            match = next((m for m in nodes
                          if m.get('type') == 'mule' and m.get('label') == target), None)
            if match:
                id_to_key[n['id']] = match['id']
                internal_remapped += 1
                continue
        # True external backend -> consolidate
        friendly = consolidate_backend(raw_label)
        bkey = 'backend-' + friendly.lower().replace(' ', '-')
        if bkey not in out_nodes:
            out_nodes[bkey] = {'key': bkey, 'label': friendly, 'kind': 'backend',
                               'layer': 'backend', 'tag': '',
                               'category': backend_category(friendly),
                               'icon': _icon_for(raw_label.lower()),
                               'in': 0, 'out': 0}
        id_to_key[n['id']] = bkey
        backend_members[friendly].append(raw_label)

    # ── Edge remap + reconciliation ────────────────────────────────────────
    raw_edge_count = len(edges)
    seen = set()
    out_edges = []
    dropped_unresolved = 0
    dropped_selfloop = 0
    collapsed_duplicate = 0

    for e in edges:
        s = e.get('sourceId') or e.get('source')
        t = e.get('targetId') or e.get('target')
        sk = id_to_key.get(s)
        tk = id_to_key.get(t)
        if sk is None or tk is None:
            dropped_unresolved += 1
            continue
        if sk == tk:
            dropped_selfloop += 1
            continue
        pair = (sk, tk)
        if pair in seen:
            collapsed_duplicate += 1
            continue
        seen.add(pair)
        out_nodes[sk]['out'] += 1
        out_nodes[tk]['in'] += 1
        out_edges.append({'source': out_nodes[sk]['label'],
                          'target': out_nodes[tk]['label']})

    kept = len(out_edges)
    accounted = kept + dropped_unresolved + dropped_selfloop + collapsed_duplicate

    report = [
        '-- EDGE RECONCILIATION ------------------------------',
        f'  raw edges                : {raw_edge_count}',
        f'  kept (unique flows)      : {kept}',
        f'  collapsed duplicates     : {collapsed_duplicate}  (consolidation merged endpoints)',
        f'  self-loops dropped       : {dropped_selfloop}',
        f'  unresolved endpoints     : {dropped_unresolved}',
        f'  -------------------------------------',
        f'  accounted for            : {accounted} / {raw_edge_count}',
        f'  internal http remapped   : {internal_remapped} (leaked-backend noise removed)',
        f'  backends (consolidated)  : {sum(1 for v in out_nodes.values() if v["kind"]=="backend")}',
    ]
    print('\n'.join(report), file=sys.stderr)

    # INVARIANT: every raw edge must be accounted for. Fail loud otherwise.
    if accounted != raw_edge_count:
        sys.exit(f'RECONCILIATION FAILED: {accounted} != {raw_edge_count}. '
                 'Edges were silently lost - aborting.')

    # ── Assemble DATA ──────────────────────────────────────────────────────
    all_node_list = list(out_nodes.values())
    backends = sorted([v for v in all_node_list if v['kind'] == 'backend'],
                      key=lambda x: -x['in'])
    mule_nodes = [v for v in all_node_list if v['kind'] == 'mule']
    reuse = sorted(mule_nodes, key=lambda x: -x['in'])[:8]

    tag_counter = Counter(n['tag'] for n in mule_nodes if n['tag'])

    # KPI fallbacks for nodes/edges-only exports (no apps[] status data).
    # Treat every discovered Mule node as a deployed, running app so the
    # Overview and the "0 stopped apps" governance message stay coherent.
    # Build env lookup: envId -> envName
    env_lookup = {e['envId']: e.get('envName', e.get('envType', '')) for e in envs}

    graph_labels = {v['label'] for v in mule_nodes}

    if apps:
        total_apps = len(apps)
        running = sum(1 for a in apps if a.get('status') in RUNNING_STATES)
        stopped = total_apps - running
        prod = sum(1 for a in apps if a.get('envtype') == 'production')
        sandbox = sum(1 for a in apps if a.get('envtype') == 'sandbox')
        # Build envRows for the overview bar chart
        env_row_map = {}
        for a in apps:
            ename = env_lookup.get(a.get('envid', ''), a.get('envtype', '').title())
            etype = a.get('envtype', '')
            if ename not in env_row_map:
                env_row_map[ename] = {'name': ename, 'type': etype, 'total': 0, 'running': 0, 'stopped': 0, 'runningVcores': 0}
            env_row_map[ename]['total'] += 1
            vcores = a.get('minsize', 0.1) or 0.1
            replica = a.get('replica', 1) or 1
            if a.get('status') in RUNNING_STATES:
                env_row_map[ename]['running'] += 1
                env_row_map[ename]['runningVcores'] = round(env_row_map[ename]['runningVcores'] + vcores * replica, 2)
            else:
                env_row_map[ename]['stopped'] += 1
        env_rows = sorted(env_row_map.values(), key=lambda x: -x['total'])
        # Active environments = distinct env names with apps deployed — the same
        # rows as the env chart and the inventory's environment filter.
        env_count = len(env_rows)

        # Build inventory list. Layer: Visualizer's label for the same app in either
        # graph (production or sandbox) when it has one, else the name rules.
        graph_layer = {}
        for sec in ('production', 'sandbox'):
            for gn in (raw.get(sec) or {}).get('dependencies', {}).get('nodes', []) or []:
                if gn.get('type') != 'mule':
                    continue
                lyr = layer_of_node(gn)
                if lyr != 'other':
                    for nm in (gn.get('appName'), gn.get('label')):
                        if nm:
                            graph_layer.setdefault(nm, lyr)
        inventory = []
        for a in apps:
            ename = env_lookup.get(a.get('envid', ''), a.get('envtype', '').title())
            vcores = a.get('minsize', 0.1) or 0.1
            replica = a.get('replica', 1) or 1
            inventory.append({
                'name': a.get('appname', ''),
                'env': ename,
                'envtype': a.get('envtype', ''),
                'layer': graph_layer.get(a.get('appname', '')) or layer_of_name(a.get('appname', '')),
                'status': a.get('status', ''),
                'target': a.get('target', ''),
                'vcores': vcores,
                'replica': replica,
                'totalVcores': round(vcores * replica, 2),
                'region': a.get('region', ''),
                'bg': org_id_to_name.get(a.get('orgid', ''), '') or 'Unknown',
                # production app with no node in the dependency graph
                'isolated': a.get('envtype') == 'production' and a.get('appname', '') not in graph_labels,
            })
    else:
        # Topology-only export (no apps[]): derive the env chart and inventory from the
        # Mule node names so those views aren't blank. Status isn't in the export, so
        # every app is shown as running (the data-confidence card flags this).
        total_apps = len(mule_nodes)
        running = total_apps
        stopped = 0
        inventory, env_row_map = [], {}
        for v in mule_nodes:
            ename, etype = env_of_name(v['label'])
            inventory.append({'name': v['label'], 'env': ename, 'envtype': etype,
                              'layer': v['layer'] if v['layer'] in ('experience', 'process', 'system') else 'other',
                              'status': 'RUNNING', 'target': '', 'vcores': '', 'replica': '',
                              'totalVcores': '', 'region': '',
                              'bg': master_org_name or 'Customer', 'isolated': False})
            r = env_row_map.setdefault(ename, {'name': ename, 'type': etype, 'total': 0,
                                                'running': 0, 'stopped': 0, 'runningVcores': 0})
            r['total'] += 1
            r['running'] += 1
        env_rows = sorted(env_row_map.values(), key=lambda x: -x['total'])
        prod = sum(1 for r in inventory if r['envtype'] == 'production')
        sandbox = sum(1 for r in inventory if r['envtype'] == 'sandbox')
        env_count = len(env_rows) or 1

    # ── Business groups (Overview cards) - per org, from apps[] ──────────────
    business_groups = []
    if apps:
        bg_agg = {}
        for r in inventory:
            b = bg_agg.setdefault(r['bg'], {'name': r['bg'], 'total': 0, 'running': 0, 'prod': 0,
                                            'sandbox': 0, 'experience': 0, 'process': 0,
                                            'system': 0, 'other': 0})
            b['total'] += 1
            b['running'] += r['status'] in RUNNING_STATES
            if r['envtype'] == 'production':
                b['prod'] += 1
            elif r['envtype'] == 'sandbox':
                b['sandbox'] += 1
            b[r['layer'] if r['layer'] in ('experience', 'process', 'system') else 'other'] += 1
        business_groups = sorted(bg_agg.values(), key=lambda x: -x['total'])
    elif inventory:
        business_groups = [{'name': master_org_name or 'Customer', 'total': total_apps,
                            'running': running, 'prod': prod, 'sandbox': sandbox,
                            'experience': len(LAYER['experience']), 'process': len(LAYER['process']),
                            'system': len(LAYER['system']), 'other': len(layer_other)}]

    # ── Deployment coverage - prod apps deployed vs present in the graph ─────
    deployment_coverage = None
    if apps:
        prod_layer = {}
        for r in inventory:
            if r['envtype'] == 'production':
                prod_layer.setdefault(r['name'], r['layer'])
        iso = sorted(set(prod_layer) - graph_labels, key=lambda n: (prod_layer[n], n))
        iso_by_layer = Counter(prod_layer[n] for n in iso)
        mapped = len(set(prod_layer) & graph_labels)
        deployment_coverage = {
            'prodTotal': len(prod_layer), 'mapped': mapped, 'isolated': len(iso),
            'coveragePct': round(mapped / len(prod_layer) * 100, 1) if prod_layer else 0,
            'byLayer': {k: iso_by_layer.get(k, 0) for k in ('experience', 'process', 'system', 'other')},
            'isolatedApps': [{'name': n, 'layer': prod_layer[n]} for n in iso],
        }

    # ── Platform adoption - share of the API-led catalogue clients consume ──
    API_LED = ('experience', 'process', 'system')
    cg_clients = {n['id']: (n.get('numberOfClientApplications') or 1)
                  for n in nodes if n.get('type') == 'clientGroup'}
    api_clients = defaultdict(int)
    for e in edges:
        s_ = e.get('sourceId') or e.get('source')
        t_ = e.get('targetId') or e.get('target')
        if s_ in cg_clients:
            tk = id_to_key.get(t_)
            if tk in out_nodes and out_nodes[tk]['kind'] == 'mule':
                api_clients[tk] += cg_clients[s_]
    api_led_nodes = [v for v in mule_nodes if v['layer'] in API_LED]
    adoption = None
    if cg_ids:
        consumed = [(k, c) for k, c in api_clients.items() if out_nodes[k]['layer'] in API_LED]
        by_layer = Counter(out_nodes[k]['layer'] for k, _ in consumed)
        exp_total = sum(1 for v in api_led_nodes if v['layer'] == 'experience')
        adoption = {
            'clientApps': total_clients,
            'consumedApis': len(consumed), 'totalApis': len(api_led_nodes),
            'coveragePct': round(len(consumed) / len(api_led_nodes) * 100) if api_led_nodes else 0,
            'expConsumed': by_layer.get('experience', 0), 'expTotal': exp_total,
            'expCoveragePct': round(by_layer.get('experience', 0) / exp_total * 100) if exp_total else 0,
            'byLayer': {k: by_layer.get(k, 0) for k in API_LED},
            'topConsumed': sorted(({'label': out_nodes[k]['label'], 'clients': c,
                                    'layer': out_nodes[k]['layer']} for k, c in consumed),
                                  key=lambda x: -x['clients'])[:8],
        }

    # ── Data confidence - how far to trust the data-driven metrics ──────────
    orphans = sum(1 for v in api_led_nodes if v['in'] == 0)
    orphan_rate = orphans / len(api_led_nodes) if api_led_nodes else 0.0
    conf_reasons = []
    if not apps:
        conf_reasons.append('Topology-only export: no app deployment data, so status and '
                            'environments come from the dependency graph, not measured values')
    if orphan_rate > 0.25:
        conf_reasons.append(f'{round(orphan_rate * 100)}% of APIs ({orphans}/{len(api_led_nodes)}) have no '
                            'inbound dependency in the graph, so the dependency map may be incomplete')
    if cg_ids:
        conf_reasons.append('Client applications are pre-aggregated by Anypoint; per-application '
                            'consumption is inferred from group counts')
    if orphan_rate > 0.40:
        band = 'Low'
    elif (not apps) or orphan_rate > 0.25:
        band = 'Medium'
    else:
        band = 'High'
    confidence = {'band': band, 'orphanPct': round(orphan_rate * 100), 'reasons': conf_reasons}

    # ── Peer-review metrics (MuleSoft peer-review deck framing) ──────────────
    # apiLedPct = APIs with >=1 consumer / all Mule apps; reuseRate = reuse instances /
    # consumers; reusability = APIs with >1 consumer / all API-led APIs (orphans included).
    # Consumers count each client app, not the merged "N Client Apps" node.
    def _consumers(v):
        c = api_clients.get(v['key'], 0)
        return v['in'] - (1 if c else 0) + c
    cons = {v['key']: _consumers(v) for v in api_led_nodes}
    ge1 = sum(1 for c in cons.values() if c >= 1)
    gt1 = sum(1 for c in cons.values() if c > 1)
    tot = sum(cons.values())
    inst = sum(max(c - 1, 0) for c in cons.values())
    reuse_metrics = {
        'muleApps': len(mule_nodes), 'apis': len(api_led_nodes), 'consumedApis': ge1,
        'reusedApis': gt1, 'totalConsumers': tot, 'reuseInstances': inst,
        'apiLedPct': round(ge1 / len(mule_nodes) * 100, 1) if mule_nodes else 0,
        'reuseRate': round(inst / tot * 100, 1) if tot else 0,
        'reusability': round(gt1 / len(api_led_nodes) * 100, 1) if api_led_nodes else 0,
    }

    # ── Reuse analysis (production graph + optional sandbox graph) ─────────────
    prod_dep_nodes = nodes   # already extracted from production section
    prod_dep_edges = edges
    reuse_prod = compute_reuse_stats(prod_dep_nodes, prod_dep_edges, apps, org_map=org_id_to_name)

    reuse_sandbox = None
    if sandbox_dep:
        sb_nodes = sandbox_dep.get('nodes', [])
        sb_edges = sandbox_dep.get('edges', [])
        reuse_sandbox = compute_reuse_stats(sb_nodes, sb_edges, apps)

    # ── Per-BG reuse breakdown ────────────────────────────────────────────────
    # Uses raw production nodes (before consolidation) which carry organizationId
    raw_prod_nodes = raw.get('production', {}).get('dependencies', {}).get('nodes', []) if 'production' in raw else nodes
    raw_prod_edges = raw.get('production', {}).get('dependencies', {}).get('edges', []) if 'production' in raw else edges
    reuse_by_bg = compute_reuse_stats_by_org(raw_prod_nodes, raw_prod_edges, master_org_name, org_id_to_name)

    # ── Peer benchmark ─────────────────────────────────────────────────────────
    customer_name = master_org_name
    customer_api_count = reuse_prod['apisTotal'] if reuse_prod else 0
    benchmark_avg = compute_benchmark(customer_name, customer_api_count)

    # Client app names. The export mixes sandbox entries ({key, value} dicts at
    # the top level) with the production ones (nested inside a list), so flatten
    # and keep only entries keyed by a clientGroup node in this graph.
    flat_groups = []
    for g in (clientgroup if isinstance(clientgroup, list) else []):
        flat_groups.extend(g if isinstance(g, list) else [g])
    prod_client_groups = [g for g in flat_groups
                          if isinstance(g, dict) and g.get('key') in cg_ids]

    data = {
        'meta': {
            'customer': master_org_name or 'Customer',
            'masterOrg': master_org_name,
            'extractOn': master.get('extractOn', ''),
            'orgs': orgs,
            'generated': '',
        },
        'kpis': {
            'totalApps': total_apps,
            'running': running,
            'stopped': stopped,
            'prod': prod,
            'sandbox': sandbox,
            'envs': env_count,
            'uniqueApis': len(LAYER['experience']) + len(LAYER['process']) + len(LAYER['system']),
            'backends': len(backends),
            'expCount': len(LAYER['experience']),
            'procCount': len(LAYER['process']),
            'sysCount': len(LAYER['system']),
            'flows': kept,          # consolidated, deduplicated
            'flowsRaw': raw_edge_count,
        },
        'envRows': env_rows,
        'targets': [],
        'layers': LAYER,
        'nodes': all_node_list,
        'edges': out_edges,
        'backends': backends,
        'consumers': consumers,
        'reuse': reuse,
        'tagDist': tag_counter.most_common(),
        'clientApps': sorted(set(
            v.get('name') for g in prod_client_groups
            for v in g.get('value', [])
            if isinstance(v, dict) and v.get('name')
        )),
        'inventory': inventory,
        'layerOther': layer_other,
        'businessGroups': business_groups,
        'deploymentCoverage': deployment_coverage,
        'adoption': adoption,
        'confidence': confidence,
        'reuseMetrics': reuse_metrics,
        'reuseAnalysis': {
            'production': reuse_prod,
            'sandbox': reuse_sandbox,
            'benchmarkAvg': benchmark_avg,
            'byBG': reuse_by_bg,
        },
    }
    print(json.dumps(data))


if __name__ == '__main__':
    main()
