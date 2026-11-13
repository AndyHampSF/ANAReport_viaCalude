#!/usr/bin/env python3
"""
make_example_export.py - build a synthetic, non-identifying Anypoint network-graph export
for demonstrating the mulesoft-estate-report skill.

Nothing in the output comes from a real customer. Sizes and proportions are set to the
median of the real exports processed so far (about 260 deployments, 6 environments,
~50 production Mule apps, ~120 flows, ~20 backends, ~50% reuse, ~40% single-replica,
~12% stopped). Names are generic business functions, backends are mainstream SaaS
products, hosts use the reserved example.com / example.net domains, and every ID is a
deterministic fake UUID. The organisation is "Example Co" and is deliberately not in
customer_ou_map.json, so the peer benchmark compares against all industries.

Usage:  python3 tools/make_example_export.py [-o OUTPUT.json] [--seed N]
"""
import argparse
import json
import random
import uuid
from pathlib import Path

NS = uuid.UUID('6f1c2a4e-0000-4000-8000-000000000000')


def uid(*parts):
    return str(uuid.uuid5(NS, '/'.join(str(p) for p in parts)))


MASTER = 'Example Co'
EXTRACT = '13_11_2026_09_00_00'
BGS = ['Example Co', 'Digital Channels', 'Core Platform', 'Shared Services']

ENVS = [('Production', 'production'), ('Development', 'sandbox'), ('Test', 'sandbox'),
        ('UAT', 'sandbox'), ('Pre-Production', 'sandbox'), ('Sandbox', 'sandbox')]

# ── production Mule apps: (name, business group) ───────────────────────────────
EXP = [('exp-customer-portal-v1', 'Digital Channels'), ('exp-mobile-app-v1', 'Digital Channels'),
       ('exp-partner-gateway-v1', 'Digital Channels'), ('exp-partner-gateway-v2', 'Digital Channels'),
       ('exp-employee-portal-v1', 'Shared Services'), ('exp-public-website-v1', 'Digital Channels'),
       ('exp-self-service-v1', 'Digital Channels'), ('exp-reporting-v1', 'Shared Services')]
PROC = [('prc-customer-management-v1', 'Core Platform'), ('prc-order-orchestration-v1', 'Core Platform'),
        ('prc-case-management-v1', 'Core Platform'), ('prc-account-services-v1', 'Core Platform'),
        ('prc-document-services-v1', 'Shared Services'), ('prc-invoice-processing-v1', 'Core Platform'),
        ('prc-identity-verification-v1', 'Shared Services'), ('prc-notification-routing-v1', 'Shared Services'),
        ('prc-employee-onboarding-v1', 'Shared Services'), ('prc-search-aggregation-v1', 'Digital Channels'),
        ('prc-supplier-management-v1', 'Core Platform'), ('prc-payment-processing-v1', 'Core Platform')]
SYS = [('sys-crm-v1', 'Core Platform'), ('sys-erp-v1', 'Core Platform'), ('sys-hr-v1', 'Shared Services'),
       ('sys-itsm-v1', 'Shared Services'), ('sys-identity-v1', 'Shared Services'),
       ('sys-documents-v1', 'Shared Services'), ('sys-file-storage-v1', 'Shared Services'),
       ('sys-core-database-v1', 'Core Platform'), ('sys-messaging-v1', 'Core Platform'),
       ('sys-email-v1', 'Shared Services'), ('sys-payments-v1', 'Core Platform'),
       ('sys-code-lists-v1', 'Core Platform'), ('sys-address-lookup-v1', 'Digital Channels'),
       ('sys-file-transfer-v1', 'Core Platform'), ('sys-search-index-v1', 'Digital Channels'),
       ('sys-finance-ledger-v1', 'Core Platform'), ('sys-customer-master-v1', 'Core Platform'),
       ('sys-audit-logging-v1', 'Shared Services')]
OTHER = [('batch-invoice-export', 'Core Platform'), ('batch-data-warehouse-sync', 'Shared Services'),
         ('sched-reference-data-refresh', 'Core Platform'), ('listener-order-events', 'Core Platform'),
         ('batch-supplier-feed', 'Core Platform'), ('sync-employee-directory', 'Shared Services')]
# production deployments with no dependencies mapped (isolated) - one is a test app
ISOLATED = [('test-connectivity-check-prod', 'Example Co'), ('legacy-report-scheduler', 'Shared Services'),
            ('exp-campaign-microsite-v1', 'Digital Channels')]

# ── backend systems: key -> (node type, label, host) ───────────────────────────
BACKENDS = {
    'crm':      ('http', 'example.my.salesforce.com', 'example.my.salesforce.com'),
    'erp':      ('http', 'erp.corecloud.example', 'erp.corecloud.example'),
    'hr':       ('http', 'wd5-services.myworkday.com', 'wd5-services.myworkday.com'),
    'itsm':     ('http', 'example.service-now.com', 'example.service-now.com'),
    'entra':    ('http', 'login.microsoftonline.com', 'login.microsoftonline.com'),
    'sharepoint': ('other', 'Sharepoint', 'Sharepoint'),
    'blob':     ('http', 'examplestore.blob.core.windows.net', 'examplestore.blob.core.windows.net'),
    'db':       ('db', 'Core Database', 'Database'),
    'mq':       ('other', 'amqp', 'amqp'),
    'smtp':     ('other', 'email', 'email'),
    'payments': ('http', 'api.paystream.example', 'api.paystream.example'),
    'refdata':  ('db', 'Reference Data Store', 'Database'),
    'address':  ('http', 'api.addressfinder.example', 'api.addressfinder.example'),
    'sftp':     ('other', 'sftp', 'sftp'),
    'search':   ('http', 'eu.searchly.example', 'eu.searchly.example'),
    'ledger':   ('http', 'api.ledgerpro.example', 'api.ledgerpro.example'),
    's3':       ('other', 's3', 's3'),
    'sqs':      ('other', 'sqs', 'sqs'),
    'dw':       ('http', 'acct.datawarehouse.example', 'acct.datawarehouse.example'),
    'docsign':  ('http', 'api.signflow.example', 'api.signflow.example'),
    'partner':  ('http', 'api.tradingpartner.example', 'api.tradingpartner.example'),
}

# System API -> backends it calls
SYS_TO_BE = {
    'sys-crm-v1': ['crm'], 'sys-erp-v1': ['erp'], 'sys-hr-v1': ['hr'], 'sys-itsm-v1': ['itsm'],
    'sys-identity-v1': ['entra'], 'sys-documents-v1': ['sharepoint', 'docsign'], 'sys-file-storage-v1': ['blob', 's3'],
    'sys-core-database-v1': ['db'], 'sys-messaging-v1': ['mq', 'sqs'], 'sys-email-v1': ['smtp'],
    'sys-payments-v1': ['payments'], 'sys-code-lists-v1': ['refdata'], 'sys-address-lookup-v1': ['address'],
    'sys-file-transfer-v1': ['sftp'], 'sys-search-index-v1': ['search'], 'sys-finance-ledger-v1': ['ledger', 'erp'],
    'sys-customer-master-v1': ['crm', 'db'], 'sys-audit-logging-v1': ['blob'],
}
# Process API -> System APIs it orchestrates (skewed towards a few shared services)
PROC_TO_SYS = {
    'prc-customer-management-v1': ['sys-customer-master-v1', 'sys-crm-v1', 'sys-address-lookup-v1', 'sys-audit-logging-v1'],
    'prc-order-orchestration-v1': ['sys-erp-v1', 'sys-payments-v1', 'sys-customer-master-v1', 'sys-messaging-v1'],
    'prc-case-management-v1': ['sys-itsm-v1', 'sys-crm-v1', 'sys-documents-v1'],
    'prc-account-services-v1': ['sys-customer-master-v1', 'sys-finance-ledger-v1', 'sys-identity-v1'],
    'prc-document-services-v1': ['sys-documents-v1'],
    'prc-invoice-processing-v1': ['sys-finance-ledger-v1', 'sys-erp-v1'],
    'prc-identity-verification-v1': ['sys-identity-v1', 'sys-customer-master-v1', 'sys-audit-logging-v1'],
    'prc-notification-routing-v1': ['sys-email-v1', 'sys-messaging-v1'],
    'prc-employee-onboarding-v1': ['sys-hr-v1', 'sys-identity-v1'],
    'prc-search-aggregation-v1': ['sys-search-index-v1'],
    'prc-supplier-management-v1': [],          # deployed, no dependencies observed
    'prc-payment-processing-v1': ['sys-payments-v1', 'sys-finance-ledger-v1', 'sys-audit-logging-v1'],
}
# Experience API -> Process / System APIs
EXP_TO = {
    'exp-customer-portal-v1': ['prc-customer-management-v1', 'prc-order-orchestration-v1', 'prc-case-management-v1',
                               'prc-notification-routing-v1'],
    'exp-mobile-app-v1': ['prc-customer-management-v1', 'prc-account-services-v1', 'prc-notification-routing-v1',
                          'prc-identity-verification-v1'],
    'exp-partner-gateway-v1': ['prc-order-orchestration-v1', 'prc-invoice-processing-v1'],
    'exp-partner-gateway-v2': ['prc-order-orchestration-v1', 'prc-document-services-v1'],
    'exp-employee-portal-v1': ['prc-employee-onboarding-v1'],
    'exp-public-website-v1': ['prc-search-aggregation-v1', 'sys-address-lookup-v1'],
    'exp-self-service-v1': ['prc-account-services-v1', 'prc-payment-processing-v1'],
    'exp-reporting-v1': ['sys-core-database-v1'],
}
# integration / batch apps -> systems (nothing calls them)
OTHER_TO = {
    'batch-invoice-export': ['sys-finance-ledger-v1', 'sftp'],
    'batch-data-warehouse-sync': ['sys-core-database-v1', 'sys-customer-master-v1', 'dw'],
    'sched-reference-data-refresh': ['partner', 'refdata'],
    'listener-order-events': ['sqs', 'sys-erp-v1', 'sys-email-v1'],
    'batch-supplier-feed': ['sftp', 'sys-erp-v1'],
    'sync-employee-directory': ['hr', 'entra'],
}
# client app groups -> Experience APIs they consume: (group label suffix, n clients, [apis], [names])
CLIENTS = [
    (1, ['exp-customer-portal-v1'], ['web-portal-client']),
    (1, ['exp-mobile-app-v1'], ['mobile-ios-client']),
    (1, ['exp-mobile-app-v1'], ['mobile-android-client']),
    (5, ['exp-partner-gateway-v2'], ['partner-a-client', 'partner-b-client', 'partner-c-client',
                                     'partner-d-client', 'partner-e-client']),
    (2, ['exp-partner-gateway-v1'], ['partner-f-client', 'partner-g-client']),
    (1, ['exp-employee-portal-v1'], ['intranet-client']),
    (1, ['exp-public-website-v1'], ['website-cms-client']),
    (1, ['exp-self-service-v1'], ['self-service-web-client']),
    (3, ['exp-self-service-v1', 'exp-customer-portal-v1'], ['chatbot-client', 'contact-centre-client', 'kiosk-client']),
    (1, ['sys-code-lists-v1'], ['analytics-client']),
    (1, ['exp-reporting-v1'], ['bi-dashboard-client']),
    (1, ['sys-address-lookup-v1'], ['data-quality-client']),
    (2, ['prc-search-aggregation-v1'], ['search-widget-client', 'internal-search-client']),
]
EXTERNAL_TRAFFIC_TO = ['exp-public-website-v1', 'exp-partner-gateway-v1', 'exp-self-service-v1']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('-o', '--output', default='Example Co-network_graphs-13_11_2026_09_00_00.json')
    ap.add_argument('--seed', type=int, default=7)
    a = ap.parse_args()
    rnd = random.Random(a.seed)

    master_id = uid('org', MASTER)
    org_id = {bg: (master_id if bg == MASTER else uid('org', bg)) for bg in BGS}
    env_id = {name: uid('env', name) for name, _ in ENVS}
    prod_env = env_id['Production']

    all_prod = EXP + PROC + SYS + OTHER
    bg_of = dict(all_prod + ISOLATED)

    # ── apps inventory ──
    apps = []

    def app(name, env, etype, bg, status, target, size, replica, java8=False):
        apps.append({'appname': name, 'appid': name, 'orgid': org_id[bg], 'envid': env_id[env], 'envtype': etype,
                     'target': target, 'minsize': size, 'maxsize': size,
                     'memory': {0.1: '500 MB memory', 0.2: '1 GB memory', 0.5: '2 GB memory', 1: '4 GB memory'}[size],
                     'replica': replica, 'region': 'EU (Ireland)', 'status': status})

    busy_single = {'sys-customer-master-v1', 'sys-identity-v1'}   # shared APIs on one replica
    java8 = set()
    for name, bg in all_prod:
        lay = name.split('-')[0]
        size = 0.5 if name in ('prc-order-orchestration-v1', 'batch-data-warehouse-sync') else (0.2 if lay in ('exp', 'prc') else 0.1)
        if name in busy_single:
            rep = 1
        elif lay in ('exp', 'prc'):
            rep = 2
        else:
            rep = 1 if rnd.random() < 0.55 else 2
        target = 'CH2.0 - private-space' if lay in ('exp', 'prc', 'sys') else 'CH1.0'
        app(name, 'Production', 'production', bg, 'RUNNING', target, size, rep)
        if name in ('prc-case-management-v1', 'sys-itsm-v1', 'sys-file-transfer-v1', 'batch-invoice-export',
                    'batch-supplier-feed'):
            java8.add(name)
    for name, bg in ISOLATED:
        st = 'UNDEPLOYED' if name.startswith('exp-campaign') else 'RUNNING'
        app(name, 'Production', 'production', bg, st, 'CH1.0', 0.1, 1)

    sandbox_envs = [('Development', 'dev', 0.22), ('Test', 'test', 0.08), ('UAT', 'uat', 0.04),
                    ('Pre-Production', 'preprod', 0.03)]
    for env, suf, p_stop in sandbox_envs:
        for name, bg in all_prod:
            if env == 'Pre-Production' and rnd.random() < 0.15:
                continue
            base = name.rsplit('-v', 1)[0] if name.endswith(('-v1', '-v2')) else name
            ver = name[len(base):]
            st = 'STOPPED' if rnd.random() < p_stop else 'RUNNING'
            tgt = 'CH2.0 - shared-space' if rnd.random() < 0.55 else 'CH1.0'
            app(f'{base}-{suf}{ver}', env, 'sandbox', bg, st, tgt, 0.1, 1)
    for i, poc in enumerate(['poc-event-streaming', 'poc-graphql-gateway', 'poc-ai-summariser', 'demo-hello-world',
                             'poc-async-api', 'spike-cache-layer', 'poc-file-scanner', 'test-oauth-flow',
                             'spike-throttling', 'demo-dataweave-playground', 'poc-event-relay', 'spike-retry-patterns']):
        app(poc, 'Sandbox', 'sandbox', 'Example Co', 'STOPPED' if i % 2 else 'RUNNING', 'CH2.0 - shared-space', 0.1, 1)

    # ── production dependency graph ──
    nodes, edges = [], []
    nid = {}

    def mule(name):
        lay = {'exp': 'Experience', 'prc': 'Process', 'sys': 'System'}.get(name.split('-')[0])
        n = {'id': uid('node', name), 'organizationId': org_id[bg_of[name]], 'environmentId': prod_env,
             'type': 'mule', 'deploymentTarget': 'cloudhub', 'label': name, 'systemLabel': name, 'appName': name,
             'serverId': 'worker-0', 'clusterId': uid('cluster', name)[:24].replace('-', ''),
             'host': f'{name}.eu1.cloudhub.io',
             'muleVersion': '4.6-java8' if name in java8 else '4.9-java17'}
        if lay:
            n['layer'] = {'id': uid('layer', lay), 'label': lay, 'order': {'Experience': 1, 'Process': 2, 'System': 3}[lay],
                          'source': 'muleRuntime'}
        nodes.append(n)
        nid[name] = n['id']

    for name, _ in all_prod:
        mule(name)
    for key, (typ, label, host) in BACKENDS.items():
        n = {'id': uid('be', key), 'type': typ, 'label': label, 'systemLabel': label, 'host': host}
        nodes.append(n)
        nid[key] = n['id']

    def edge(src, dst):
        edges.append({'id': uid('edge', src, dst, len(edges)), 'sourceId': nid[src], 'targetId': nid[dst], 'valid': True})

    for s_, bes in SYS_TO_BE.items():
        for b in bes:
            edge(s_, b)
    for p_, ss in PROC_TO_SYS.items():
        for x in ss:
            edge(p_, x)
    for e_, ts in EXP_TO.items():
        for x in ts:
            edge(e_, x)
    for o_, ts in OTHER_TO.items():
        for x in ts:
            edge(o_, x)

    clientgroup_prod = []
    for i, (n_clients, targets, names) in enumerate(CLIENTS):
        cid = uid('cg', i)
        nodes.append({'id': cid, 'type': 'clientGroup', 'label': f'{n_clients} Client App{"s" if n_clients > 1 else ""}',
                      'systemLabel': f'{n_clients} Client App{"s" if n_clients > 1 else ""}',
                      'numberOfClientApplications': n_clients})
        nid[f'cg{i}'] = cid
        for t in targets:
            edge(f'cg{i}', t)
        clientgroup_prod.append({'key': cid, 'value': [{'name': f'{nm}-{{prod}}', 'client_id': uid('client', nm)}
                                                        for nm in names]})
    ext = {'id': uid('node', 'external-traffic'), 'type': 'http', 'label': 'External Traffic',
           'systemLabel': 'External Traffic', 'clientId': 'OTHER'}
    nodes.append(ext)
    nid['ext'] = ext['id']
    for t in EXTERNAL_TRAFFIC_TO:
        edge('ext', t)
    # a few duplicate observations of the same call (Visualizer records per worker)
    for src, dst in [('prc-order-orchestration-v1', 'sys-erp-v1'), ('exp-mobile-app-v1', 'prc-customer-management-v1'),
                     ('sys-crm-v1', 'crm')]:
        edge(src, dst)

    # ── sandbox graph: the UAT copy of the same topology, smaller ──
    sb_nodes, sb_edges = [], []
    uat_id = env_id['UAT']
    for n in nodes:
        if n['type'] != 'mule':
            continue
        m = dict(n)
        m['id'] = uid('sbnode', n['label'])
        base = n['label'].rsplit('-v', 1)[0] if n['label'].endswith(('-v1', '-v2')) else n['label']
        m['label'] = m['systemLabel'] = m['appName'] = f'{base}-uat{n["label"][len(base):]}'
        m['environmentId'] = uat_id
        m['host'] = f'{m["label"]}.eu1.cloudhub.io'
        sb_nodes.append(m)
    sb_map = {uid('node', n['label']): uid('sbnode', n['label']) for n in nodes if n['type'] == 'mule'}
    for e in edges:
        if e['sourceId'] in sb_map and e['targetId'] in sb_map and rnd.random() < 0.8:
            sb_edges.append({'id': uid('sbedge', e['id']), 'sourceId': sb_map[e['sourceId']],
                             'targetId': sb_map[e['targetId']], 'valid': True})

    export = {
        'masterOrg': {'masterOrgId': master_id, 'masterOrgName': MASTER, 'extractOn': EXTRACT},
        'orgs': [{'orgId': org_id[bg], 'orgName': bg} for bg in BGS],
        'envs': [{'envId': env_id[n], 'envName': n, 'envType': t} for n, t in ENVS],
        'apps': apps,
        'sandbox': {'dependencies': {'nodes': sb_nodes, 'edges': sb_edges}, 'clientgroup': [], 'policies': []},
        'production': {'dependencies': {'nodes': nodes, 'edges': edges},
                       'clientgroup': [clientgroup_prod], 'policies': []},
    }
    out = Path(a.output)
    out.write_text(json.dumps(export, indent=1), encoding='utf-8', newline='\n')
    print(f'wrote {out}  ({len(apps)} apps, {len(nodes)} prod nodes, {len(edges)} prod edges, '
          f'{len(java8)} java8 apps)')


if __name__ == '__main__':
    main()
