# Prompt: Generate a MuleSoft API-Led Architecture HTML Report from an Anypoint Network Graph JSON

## Objective

You are given a single JSON file exported from the Anypoint Platform network-graph API. Your task is to produce a **single self-contained HTML file** — no external dependencies, no CDN links, all CSS and JavaScript inline — that visualizes the customer's MuleSoft estate as a polished, interactive architecture report.

The report must use **MuleSoft API-Led Connectivity terminology** throughout (Experience / Process / System layers, Anypoint Platform, CloudHub 2.0, API Manager, Exchange, vCores, etc.) and keep the MuleSoft brand colors and logo. The customer name is derived from the JSON; everything else in the document must be generic enough to share with any audience.

---

## Input JSON Schema

The JSON file has the following top-level structure:

```json
{
  "masterOrg": {
    "masterOrgName": "Acme Corp",
    "extractOn": "15_07_2026_16_37_56"
  },
  "orgs": [
    { "orgName": "Acme IT" },
    { "orgName": "Acme Corp" }
  ],
  "envs": [
    { "envName": "Production", "envType": "production" },
    { "envName": "Test",       "envType": "sandbox" },
    { "envName": "Development","envType": "sandbox" }
  ],
  "apps": [
    {
      "appname": "exp-api-hris",
      "envtype": "production",
      "target": "CH2.0 - private-space",
      "minsize": 0.1,
      "status": "RUNNING"
    }
  ],
  "production": {
    "dependencies": { "nodes": [...], "edges": [...] },
    "clientgroup": [
      {
        "key": "<nodeId>",
        "value": [{ "name": "app-client-prod", "client_id": "..." }]
      }
    ],
    "policies": []
  },
  "sandbox": {
    "dependencies": { "nodes": [...], "edges": [...] },
    "clientgroup": [...],
    "policies": []
  }
}
```

### Node object fields (`production.dependencies.nodes`)

```json
{
  "id": "<uuid>",
  "type": "mule | http | other | sfdc | clientGroup",
  "label": "exp-api-hris",
  "systemLabel": "exp-api-hris",
  "appName": "exp-api-hris",
  "layer": { "label": "Experience | Process | System" },
  "tags": [{ "label": "HRIS" }],
  "deploymentTarget": "rtf | cloudhub2",
  "numberOfClientApplications": 3
}
```

- **`type=mule`** — a deployed Mule application. If it has `layer`, classify it into Experience/Process/System. If no `layer`, treat as "other" (utility apps like email alerts, connection tests).
- **`type=http`** — either another Mule app referenced by its internal CloudHub 2.0 hostname (pattern: `<appname>-<hash>.<private-space>.<region>.cloudhub.io`) or a true external HTTP endpoint / backend system. Strip the hostname suffix to recover the clean app name. If after stripping it matches a known Mule app label, skip this node (it's a duplicate). Otherwise, classify as a backend.
- **`type=other`** — a non-HTTP backend (file shares, encryption services, SFTP servers, SharePoint, ERP SOAP, AI inference, etc.).
- **`type=sfdc`** — a Salesforce org endpoint; treat as a CRM backend.
- **`type=clientGroup`** — an API Manager consumer group. Use `numberOfClientApplications` to build the "Client Apps" consumer node; cross-reference with `production.clientgroup` to get actual client app names.

### Edge object fields

```json
{ "id": "<uuid>", "sourceId": "<nodeId>", "targetId": "<nodeId>", "valid": true }
```

Edges reference nodes by `id`. Build a lookup `{ id → node }` to resolve them.

---

## Data Processing Steps

### Step 1 — Parse identity

```
customer   = masterOrg.masterOrgName
extractDate = masterOrg.extractOn  (reformat: "15_07_2026_16_37_56" → "15 Jul 2026, 16:37 UTC")
orgs        = orgs[].orgName  (deduplicate)
```

### Step 2 — Classify production nodes

Build an id→node map. For each node:

1. **`type=mule`** with `layer`:
   - `layer.label = "Experience"` → push to `layers.experience`
   - `layer.label = "Process"` → push to `layers.process`
   - `layer.label = "System"` → push to `layers.system`
   - Extract `tags[0].label` as the business domain tag.
2. **`type=mule`** with no `layer` → push to `layers.other` (still part of inventory/graph).
3. **`type=http`** whose label matches `*.cloudhub.io` → strip to app name → if matches a known mule node, skip (duplicate); else treat as external backend.
4. **`type=http`** with a plain hostname or URL → backend.
5. **`type=other`** → backend.
6. **`type=sfdc`** → backend (CRM).
7. **`type=clientGroup`** → consumer. If `numberOfClientApplications > 1`, label = "Client Apps"; else "Client App".

### Step 3 — Resolve edges

For each edge where `valid=true`:
- Resolve `sourceId` and `targetId` to node labels.
- Discard edges where either end is a duplicate `http` node (internal CH2 hostnames that map to known mule apps).
- Store as `{ source: label, target: label }`.

### Step 4 — Compute in/out degrees

For every node, count how many edges arrive (`in`) and depart (`out`). These drive the reuse badge on API tiles and the reuse ranking in the Insights tab.

### Step 5 — Build inventory

From `apps[]`:
- Match each app to its environment using `envtype` and the `envs` array.
- Infer the API-Led layer from the app name:
  - ends with `-eapi` or name contains `exp-` → `experience`
  - ends with `-papi` or name contains `prc-` → `process`
  - ends with `-sapi` or name contains `sys-` → `system`
  - otherwise → `other`
- Keep: `name`, `env`, `envtype`, `layer`, `status`, `target`, `vcores` (= `minsize`).

### Step 6 — Build client app list

Flatten `production.clientgroup[].value[].name` → deduplicated list of registered OAuth client application names.

### Step 7 — Compute KPIs

```
totalApps   = apps.length
running     = apps where status = "RUNNING"
stopped     = totalApps - running
prod        = apps where envtype = "production"
sandbox     = apps where envtype = "sandbox"
envs        = distinct envNames in inventory
uniqueApis  = layers.experience + layers.process + layers.system (lengths)
backends    = distinct backend nodes
flows       = edges.length (production graph)
expCount    = layers.experience.length
procCount   = layers.process.length
sysCount    = layers.system.length
```

### Step 8 — Backend icon mapping

Use the node label/systemLabel to assign a display icon key:

| Pattern | Icon key |
|---|---|
| `*.okta.com` or `okta` in label | `okta` |
| `salesforce` / type=sfdc | `salesforce` |
| `sharepoint` | `sharepoint` |
| `azure` / `Azure-storage` | `azure` |
| `outlook` / `Outlook365` | `outlook` |
| `sftp` / `SFTP Server` | `sftp` |
| `smb` / `File Server` | `smb` |
| `crypto` / `Crypto` | `crypto` |
| `Wsc` / `peoplesoft` | `peoplesoft` |
| `anypoint.mulesoft.com` | `mulesoft` |
| `Ms-inference` / `ai` | `ai` |
| `oanda` / `exchange-rates` | `oanda` |
| `gateway` | `gateway` |
| `timesheetportal` | `timesheet` |
| External Traffic / web | `web` |
| Client App(s) | `client` |
| fallback | `service` |

---

## Visual Design

**CRITICAL: Copy the stylesheet below EXACTLY into the `<style>` block. Do not rename classes, do not add new variables, do not change any value.**

```css
:root{
  --navy:#052D60; --teal:#0BA49B; --indigo:#5E66F9;
  --band:#EFF8FF; --text:#464D55; --title:#052D60;
  --badge-bg:#F1F1F1; --badge-text:#002196; --mule:#00A0DF;
  --line:#D8E3F0; --ink:#1B2733; --muted:#7B8794;
  --card:#FFFFFF; --bg:#F4F7FB;
  --exp:var(--navy); --proc:var(--teal); --sys:var(--indigo);
  --shadow:0 6px 18px rgba(5,45,96,.10),0 1px 3px rgba(5,45,96,.08);
  --shadow-sm:0 2px 6px rgba(5,45,96,.10);
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{
  font-family:"Salesforce Sans","Helvetica Neue",Arial,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  color:var(--text); background:var(--bg); -webkit-font-smoothing:antialiased; line-height:1.45;
}
a{color:var(--badge-text);text-decoration:none}

/* ── Header ─────────────────────────────────────────── */
header{
  background:linear-gradient(120deg,#052D60 0%,#0A3E7E 55%,#0BA49B 160%);
  color:#fff; padding:26px 40px 0; position:relative; overflow:hidden;
}
header::after{content:"";position:absolute;right:-80px;top:-60px;width:340px;height:340px;
  background:radial-gradient(circle,rgba(94,102,249,.35),transparent 70%);pointer-events:none}
.h-top{display:flex;align-items:flex-start;justify-content:space-between;gap:24px;position:relative;z-index:1}
.h-brand{display:flex;align-items:center;gap:14px}
.h-logo{width:46px;height:46px;border-radius:12px;background:#fff;display:flex;align-items:center;justify-content:center;
  box-shadow:0 4px 14px rgba(0,160,223,.45);flex:0 0 auto;padding:6px}
.h-logo img{width:100%;height:100%;object-fit:contain;display:block}
h1{font-size:22px;margin:0;font-weight:700;letter-spacing:.2px}
.h-sub{font-size:13px;opacity:.85;margin-top:2px;font-weight:400}
.h-meta{text-align:right;font-size:12px;opacity:.82;line-height:1.7}
.h-meta b{color:#fff;font-weight:600}
.pill{display:inline-block;background:rgba(255,255,255,.16);border:1px solid rgba(255,255,255,.25);
  padding:2px 10px;border-radius:999px;font-size:11px;font-weight:600;margin-left:6px}

/* ── Tabs ───────────────────────────────────────────── */
nav.tabs{display:flex;gap:2px;margin-top:22px;position:relative;z-index:1;flex-wrap:wrap}
nav.tabs button{
  background:transparent;border:0;color:rgba(255,255,255,.72);font:inherit;font-size:13.5px;font-weight:600;
  padding:12px 18px;cursor:pointer;border-radius:10px 10px 0 0;display:flex;align-items:center;gap:8px;transition:.15s;
}
nav.tabs button .tico{width:16px;height:16px;opacity:.8}
nav.tabs button:hover{color:#fff;background:rgba(255,255,255,.08)}
nav.tabs button.active{background:var(--bg);color:var(--title)}
nav.tabs button.active .tico{opacity:1}

/* ── Layout ─────────────────────────────────────────── */
main{padding:28px 40px 60px;max-width:1400px;margin:0 auto}
.panel{display:none;animation:fade .25s ease}
.panel.active{display:block}
@keyframes fade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
h2.sec{font-size:17px;color:var(--title);margin:0 0 4px;font-weight:700}
.sec-desc{font-size:13px;color:var(--muted);margin:0 0 18px;max-width:820px}
.block{margin-bottom:34px}

/* ── KPI cards ──────────────────────────────────────── */
.kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin-bottom:26px}
.kpi{background:var(--card);border-radius:14px;padding:16px 18px;box-shadow:var(--shadow);position:relative;overflow:hidden}
.kpi .num{font-size:30px;font-weight:800;color:var(--title);line-height:1}
.kpi .lbl{font-size:12px;color:var(--muted);margin-top:6px;font-weight:600;letter-spacing:.2px}
.kpi .ic{position:absolute;right:12px;top:12px;width:22px;height:22px;opacity:.28}
.kpi .num small{font-size:15px;font-weight:700;color:var(--muted)}

.cols{display:grid;grid-template-columns:1.3fr 1fr;gap:24px}
@media(max-width:900px){.cols{grid-template-columns:1fr}}
.card{background:var(--card);border-radius:14px;box-shadow:var(--shadow);padding:20px 22px}
.card h3{margin:0 0 14px;font-size:14px;color:var(--title);font-weight:700;display:flex;align-items:center;gap:8px}
.card h3 svg{width:17px;height:17px}

/* env bars */
.envbar{margin-bottom:14px}
.envbar .top{display:flex;justify-content:space-between;font-size:12.5px;margin-bottom:5px}
.envbar .top .nm{font-weight:600;color:var(--ink)}
.envbar .top .nm .tag{font-size:10px;font-weight:700;padding:1px 7px;border-radius:6px;margin-left:7px;text-transform:uppercase;letter-spacing:.4px}
.tag.prod{background:#E7F6EF;color:#0B7A4B}
.tag.sandbox{background:#EEF0FF;color:#4A52D6}
.envbar .top .ct{color:var(--muted);font-weight:600}
.track{height:10px;border-radius:6px;background:#EDF1F6;overflow:hidden;display:flex}
.track .run{background:linear-gradient(90deg,#0BA49B,#12C2B6)}
.track .stop{background:#E6A23C}
.legend{display:flex;gap:16px;font-size:11.5px;color:var(--muted);margin-top:10px}
.legend span{display:flex;align-items:center;gap:6px}
.dot{width:9px;height:9px;border-radius:3px;display:inline-block}

/* domain chips */
.chips{display:flex;flex-wrap:wrap;gap:9px}
.chip{background:var(--band);border:1px solid var(--line);border-radius:9px;padding:8px 12px;font-size:12.5px;color:var(--ink);
  display:flex;align-items:center;gap:8px;font-weight:600}
.chip b{color:var(--indigo);font-weight:800}
.lgroup{display:flex;flex-wrap:wrap;gap:8px}
.lchip{font-size:12px;padding:5px 11px;border-radius:8px;color:#fff;font-weight:700}

/* ── Architecture swimlanes ─────────────────────────── */
.arch{background:var(--card);border-radius:16px;box-shadow:var(--shadow);padding:22px 24px 26px}
.tier-row{display:flex;justify-content:center;gap:22px;flex-wrap:wrap;margin:6px 0 14px}
.node-ico{display:flex;flex-direction:column;align-items:center;gap:6px;width:104px}
.node-ico .disc{width:52px;height:52px;border-radius:14px;background:#fff;box-shadow:var(--shadow-sm);
  display:flex;align-items:center;justify-content:center;border:1px solid var(--line)}
.node-ico .disc svg{width:30px;height:30px}
.node-ico .disc img{width:32px;height:32px;object-fit:contain}
.node-ico .cap{font-size:11px;text-align:center;color:var(--ink);font-weight:600;line-height:1.25}
.conn{height:16px;position:relative}
.conn::before{content:"";position:absolute;left:50%;top:0;bottom:0;width:2px;background:var(--line);transform:translateX(-50%)}

.lane{display:flex;align-items:stretch;gap:0;margin-bottom:10px;border-radius:14px;overflow:hidden;box-shadow:var(--shadow-sm)}
.lane .side{flex:0 0 116px;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:13px;
  text-align:center;padding:10px;line-height:1.25}
.lane .side small{display:block;font-size:10.5px;font-weight:600;opacity:.85;margin-top:3px}
.lane.experience .side{background:var(--exp)}
.lane.process .side{background:var(--proc)}
.lane.system .side{background:var(--sys)}
.lane .band{flex:1;background:var(--band);padding:14px;display:grid;
  grid-template-columns:repeat(auto-fill,minmax(224px,1fr));gap:10px;align-content:start;align-items:stretch}
.api{background:#fff;border-radius:9px;box-shadow:var(--shadow-sm);padding:9px 12px 9px 9px;display:flex;align-items:center;gap:9px;
  min-width:0;cursor:default;transition:.14s;border:1px solid transparent;position:relative}
.api:hover{transform:translateY(-2px);box-shadow:0 8px 20px rgba(5,45,96,.16);border-color:var(--line)}
.api .mi{width:30px;height:30px;flex:0 0 auto;display:flex;align-items:center;justify-content:center}
.api .mi img{width:28px;height:28px;object-fit:contain;display:block}
.api .txt{min-width:0;display:flex;flex-direction:column;justify-content:center}
.api .nm{font-size:11.5px;font-weight:600;color:var(--ink);line-height:1.22;word-break:break-word}
.api .badge{position:absolute;top:-7px;right:-7px;min-width:19px;height:19px;padding:0 5px;border-radius:10px;background:var(--navy);
  color:#fff;font-size:10.5px;font-weight:800;display:flex;align-items:center;justify-content:center;box-shadow:var(--shadow-sm)}
.api .dtag{font-size:9px;color:#fff;background:var(--teal);padding:1px 6px;border-radius:5px;font-weight:700;margin-top:3px;display:inline-block}
.archnote{font-size:11.5px;color:var(--muted);margin-top:12px;display:flex;gap:20px;flex-wrap:wrap}
.archnote span{display:flex;align-items:center;gap:7px}

/* ── Flows graph (SVG) ──────────────────────────────── */
.graph-wrap{background:var(--card);border-radius:16px;box-shadow:var(--shadow);padding:18px 10px 10px;overflow:hidden}
.graph-controls{display:flex;gap:16px;align-items:center;flex-wrap:wrap;padding:0 14px 12px;font-size:12px;color:var(--muted)}
.graph-controls .col-key{display:flex;gap:14px;flex-wrap:wrap}
.graph-controls .col-key span{display:flex;align-items:center;gap:6px;font-weight:600}
#flowsvg{width:100%;height:auto;display:block}
#flowsvg text{font-family:inherit}
.gnode rect,.gnode circle{transition:.15s}
.gnode .glabel{font-size:10.5px;fill:var(--ink);font-weight:600;pointer-events:none}
.gedge{fill:none;stroke:#C4D2E4;stroke-width:1.3;transition:.15s;opacity:.55}
svg.dim .gedge{opacity:.06}
svg.dim .gnode{opacity:.18}
svg.dim .gnode.hl{opacity:1}
svg.dim .gedge.hl{opacity:.95;stroke-width:2.4}
.gnode{cursor:pointer;opacity:1;transition:.15s}
.gnode .gcard{fill:#fff;stroke:var(--line);stroke-width:1}
.flowtip{position:fixed;pointer-events:none;background:var(--navy);color:#fff;padding:8px 11px;border-radius:8px;
  font-size:11.5px;box-shadow:0 6px 20px rgba(0,0,0,.3);opacity:0;transition:.1s;z-index:99;max-width:240px;line-height:1.4}
.flowtip b{color:#7FE9DF}

/* ── Inventory table ────────────────────────────────── */
.toolbar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:14px}
.toolbar input[type=search]{flex:1;min-width:200px;padding:9px 13px;border:1px solid var(--line);border-radius:9px;font:inherit;font-size:13px;background:#fff}
.toolbar select{padding:9px 11px;border:1px solid var(--line);border-radius:9px;font:inherit;font-size:13px;background:#fff;color:var(--ink)}
.toolbar .count{font-size:12px;color:var(--muted);font-weight:600;margin-left:auto}
.tbl-wrap{background:var(--card);border-radius:14px;box-shadow:var(--shadow);overflow:hidden}
table{width:100%;border-collapse:collapse;font-size:12.5px}
thead th{background:#F0F5FB;color:var(--title);text-align:left;padding:11px 14px;font-weight:700;font-size:11.5px;
  text-transform:uppercase;letter-spacing:.4px;cursor:pointer;user-select:none;white-space:nowrap;border-bottom:1px solid var(--line)}
thead th:hover{background:#E7F0FA}
tbody td{padding:9px 14px;border-bottom:1px solid #EEF2F7;color:var(--ink)}
tbody tr:hover{background:#F7FAFE}
.lpill{font-size:10px;font-weight:800;padding:2px 8px;border-radius:6px;text-transform:uppercase;letter-spacing:.3px;color:#fff}
.lpill.experience{background:var(--exp)} .lpill.process{background:var(--proc)}
.lpill.system{background:var(--sys)} .lpill.other{background:#9AA5B1}
.st{display:inline-flex;align-items:center;gap:6px;font-weight:600}
.st .dot{width:8px;height:8px;border-radius:50%}
.st.RUNNING .dot{background:#12B886} .st.RUNNING{color:#0B7A4B}
.st.NOT_RUNNING .dot{background:#E6A23C} .st.NOT_RUNNING{color:#B9770E}
.etag{font-size:10px;font-weight:700;padding:1px 7px;border-radius:6px}

/* ── Backend cards ──────────────────────────────────── */
.sys-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(215px,1fr));gap:14px}
.sys{background:var(--card);border-radius:13px;box-shadow:var(--shadow);padding:15px 16px;display:flex;gap:13px;align-items:flex-start}
.sys .ic{width:44px;height:44px;border-radius:11px;background:var(--band);display:flex;align-items:center;justify-content:center;flex:0 0 auto;border:1px solid var(--line)}
.sys .ic svg{width:26px;height:26px}
.sys .ic img{width:28px;height:28px;object-fit:contain}
.sys .nm{font-size:13.5px;font-weight:700;color:var(--title);line-height:1.2}
.sys .cat{font-size:11px;color:var(--muted);margin-top:2px;font-weight:600}
.sys .conns{font-size:11px;color:var(--indigo);margin-top:7px;font-weight:700}

/* ── Insights ───────────────────────────────────────── */
.insight-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;margin-bottom:26px}
.ins{background:var(--card);border-radius:14px;box-shadow:var(--shadow);padding:20px}
.ins h3{margin:0 0 6px;font-size:14px;color:var(--title);font-weight:700;display:flex;gap:9px;align-items:center}
.ins h3 .ib{width:30px;height:30px;border-radius:8px;display:flex;align-items:center;justify-content:center;flex:0 0 auto}
.ins h3 .ib svg{width:18px;height:18px}
.ins p{font-size:12.5px;color:var(--text);margin:8px 0 0}
.ins .big{font-size:26px;font-weight:800;color:var(--title)}
.reuse-row{display:flex;align-items:center;gap:10px;margin:9px 0;font-size:12.5px}
.reuse-row .rn{flex:1;font-weight:600;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.reuse-row .rbar{height:8px;border-radius:5px;background:#EDF1F6;flex:0 0 130px;overflow:hidden}
.reuse-row .rbar i{display:block;height:100%;background:linear-gradient(90deg,var(--indigo),#8A90FF)}
.reuse-row .rv{font-weight:800;color:var(--indigo);width:26px;text-align:right}
.rec{display:flex;gap:12px;padding:13px 0;border-bottom:1px solid #EEF2F7}
.rec:last-child{border-bottom:0}
.rec .rk{width:26px;height:26px;border-radius:7px;background:var(--band);flex:0 0 auto;display:flex;align-items:center;justify-content:center;color:var(--indigo);font-weight:800;font-size:13px}
.rec .rt{font-size:12.5px} .rec .rt b{color:var(--title)}
footer{text-align:center;font-size:11px;color:var(--muted);padding:24px;border-top:1px solid var(--line);margin-top:20px}
.clientlist{display:flex;flex-direction:column;gap:8px}
.clientlist .ca{display:flex;align-items:center;gap:9px;font-size:12.5px;font-weight:600;color:var(--ink);background:var(--band);padding:8px 12px;border-radius:8px}
.clientlist .ca svg{width:15px;height:15px;color:var(--indigo);flex:0 0 auto}
```

---

## Canonical HTML Skeleton

**CRITICAL: Use this exact `<body>` structure. Do not rename IDs, do not add wrapper divs.**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{customerName} — MuleSoft Architecture</title>
<style>
  /* === PASTE THE FULL STYLESHEET FROM THE "Visual Design" SECTION ABOVE === */
</style>
</head>
<body>
<header>
  <div class="h-top">
    <div class="h-brand">
      <div class="h-logo"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40"><rect width="40" height="40" rx="8" fill="#00A0DF"/><path d="M8,11 L13,11 L20,22 L27,11 L32,11 L32,30 L27,30 L27,19 L21,28 L19,28 L13,19 L13,30 L8,30 Z" fill="#fff"/></svg></div>
      <div>
        <h1>{customerName} — MuleSoft Estate</h1>
        <div class="h-sub">API-Led Integration Architecture · Anypoint Platform network-graph analysis</div>
      </div>
    </div>
    <div class="h-meta">
      <div>Master org <b>{masterOrg}</b></div>
      <div>Business groups: <b>{orgs joined by ", "}</b></div>
      <div>Platform extract <b>{extractOn}</b> <span class="pill">CH 2.0</span></div>
    </div>
  </div>
  <nav class="tabs" id="tabs"></nav>
</header>
<main id="main"></main>
<div class="flowtip" id="flowtip"></div>
<footer>
  Generated from Anypoint Platform network-graph export · {customerName} ·
  Visual language per MuleSoft API-Led architecture template. Topology reflects the <b>Production</b> business group dependency graph; inventory spans all environments.
</footer>
<script>
  /* DATA + icon library + renderer functions go here */
</script>
</body>
</html>
```

---

## Tab Content Specifications

### Tab 1 — Overview

**Purpose:** Executive summary of the MuleSoft estate at a glance.

**KPI grid** (6 cards, `auto-fill minmax(150px)`):
- Total deployed applications
- Running apps (e.g. "119 / 142")
- Unique API projects
- Integration flows (production)
- Backend systems connected
- Active environments

**API-Led layer distribution card:**
- Three colored chips: `Experience · N`, `Process · N`, `System · N`
- 1–2 sentence narrative: describe the 3-layer split, note which tier is widest and what that implies about reuse investment.

**Environment inventory card** (bar chart):
- One row per environment; bar width proportional to app count.
- Each bar split into "running" (teal) and "stopped" (amber) segments.
- Legend below.

**Business domains card:**
- Chips for each tag derived from `tags[].label` with a count badge.
- Caption: "N business domains tagged across the API catalog."

**OAuth client governance card:**
- List of registered client app names from `clientgroup`.
- Caption: "Registered client applications consuming Experience APIs via client-ID enforcement."

---

### Tab 2 — API-Led Architecture

**Purpose:** The canonical 3-layer swimlane view of the production topology.

**Layout (top to bottom):**
1. Consumer nodes row (Client Apps, External Traffic icons)
2. Connector line
3. Experience lane (navy sidebar label)
4. Process lane (teal sidebar label)
5. System lane (indigo sidebar label)
6. Connector line
7. Backend systems row (icons)

Each lane has:
- A colored left sidebar: layer name + `"channel APIs · N"` / `"orchestration · N"` / `"systems of record · N"`
- A grid of API tiles (minmax 224px). Each tile shows:
  - MuleSoft logo icon (left)
  - API name (right, bold)
  - Optional domain tag chip (teal pill, from `tags[0].label`)
  - Optional reuse badge (navy circle, top-right corner) when `in > 1`

**Section description text:**
> "The canonical three-layer view of the production estate. Client applications and external traffic enter through Experience APIs, orchestrate through reusable Process APIs, and reach systems of record through System APIs. Badges show how many downstream calls each API receives (reuse in-degree)."

---

### Tab 3 — Integration Flows

**Purpose:** Interactive SVG dependency graph — the same view as Anypoint Visualizer, reconstructed from the export.

**Graph layout:**
- 5 columns left-to-right: Consumers | Experience | Process | System | Backends
- Nodes rendered as rounded rectangles (196px wide, 18px tall) with a 4px colored left bar.
- Edges as cubic bezier curves between right edge of source and left edge of target.
- Column headers in bold uppercase.

**Interactions:**
- On hover, `dim` the whole graph (reduce opacity of all elements).
- Highlight the hovered node and all its direct neighbors at full opacity.
- Highlight all edges connected to the hovered node in a brighter stroke.
- Show a floating tooltip: API name, role (Experience/Process/System/Backend), connection count, in/out degree, and domain tag if present.

**Section description text:**
> "Every production dependency, laid out left-to-right by architectural role. Hover any node to isolate its upstream and downstream connections. This is the same graph Anypoint renders in Visualizer — reconstructed here from the export."

**Color key legend:** Consumer (navy), Experience, Process, System, Backend (grey).

---

### Tab 4 — Application Inventory

**Purpose:** Sortable, filterable table of all deployed Mule applications across all environments.

**Toolbar:**
- Search input (filter by app name, live)
- Environment dropdown (All / Production / Test / Development / …)
- Layer dropdown (All / Experience / Process / System / Other)
- Status dropdown (Any / Running / Stopped)
- Live count badge: "N of M shown"

**Table columns:** Application | Layer | Environment | Status | Target | vCores

- Layer: colored pill (navy/teal/indigo/grey).
- Environment: name + sandbox/production pill.
- Status: colored dot — green "Running" / amber "Stopped".
- Sortable by clicking any column header.

**Section description text:**
> "Every one of the {totalApps} deployed Mule applications across {N} active environments. Search by name, filter by environment / layer / status, and click any column to sort."

---

### Tab 5 — Backend Systems

**Purpose:** Cards for all external systems and endpoints the System APIs connect to.

**Grid:** `auto-fill minmax(215px)` cards. Each card:
- Icon (left, 44px rounded square)
- Name (bold)
- Category label (muted, e.g. "Core HR / ERP", "Identity / SSO", "Cloud storage")
- Connection count: "N System-API connection(s)"

**Section description text:**
> "The {N} systems of record and external services that the System APIs connect to. Connection count shows how many Mule flows terminate at each system — the reuse fan-in delivered by the System layer."

---

### Tab 6 — MuleSoft Insights

**Purpose:** Data-driven observations and actionable recommendations for an SE or architect conversation.

**Top insight cards (3-column grid):**

1. **API reuse maturity** — compute `edges.length / muleNodes.length`, display as `X.X×`. Narrative: explain that a wide System tier with high reuse ratio demonstrates mature API-led investment.
2. **Operational health** — `running / totalApps` as a percentage. Narrative: note that production is near-fully healthy; stopped apps concentrate in lower environments.
3. **Consumption governance** — count of registered OAuth client apps. Narrative: client-ID enforcement is in place on Experience APIs; recommend extending with SLA tiers and rate limits in API Manager.

**Most-reused APIs (fan-in bar chart):**
- List the top 6–8 mule nodes sorted by `in` descending.
- Horizontal bar proportional to in-degree, indigo gradient fill.
- Caption: "In-degree = number of distinct upstream APIs / consumers calling this asset. High values are your crown-jewel reusable services."

**Recommendations card (numbered list):**
Generate 4 contextual recommendations derived from the data:
1. **Consolidate stopped apps** — reference the count of NOT_RUNNING apps, particularly in Development; suggest reclaiming vCores.
2. **Promote System-API reuse** — name the top 2–3 highest-reuse System APIs; recommend cataloging them in Exchange as canonical connectivity assets.
3. **Right-size vCore allocation** — note that all apps are at 0.1 vCore replicas; recommend validating this covers peak throughput for data-heavy flows (file transfers, HRIS sync).
4. **Formalize the Experience proxy pattern** — identify any `*-proxy` Experience APIs; recommend standardizing the fronting pattern with API Manager policies for consistent security and throttling.

---

## MuleSoft Logo

Use the following inline SVG as the canonical MuleSoft logo mark — a white geometric M on the MuleSoft blue (#00A0DF) rounded-square background. Copy it **verbatim**; do not substitute a text element or any other shape.

```
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40"><rect width="40" height="40" rx="8" fill="#00A0DF"/><path d="M8,11 L13,11 L20,22 L27,11 L32,11 L32,30 L27,30 L27,19 L21,28 L19,28 L13,19 L13,30 L8,30 Z" fill="#fff"/></svg>
```

Use it:
- In the header white rounded-square badge (paste directly inside `.h-logo`)
- As the icon on every API tile in the Architecture tab (via `IC.mule`)
- As the icon for Anypoint / MuleSoft backend system cards (via `IC.mulesoft`)
- In the Insights tab reuse-maturity card
- In the Architecture tab legend

---

## JavaScript Architecture

**CRITICAL: Copy the DATA schema shape, icon library, tab definitions, and router pattern below EXACTLY. Only the values inside `DATA` change per customer — all keys, class names, and function signatures are fixed.**

### DATA schema (all fields required)

```js
const DATA = {
  meta: { customer, masterOrg, extractOn, orgs, generated },
  kpis: { totalApps, running, stopped, prod, sandbox, envs, uniqueApis, backends, expCount, procCount, sysCount, flows },
  envRows: [ { name, type, total, running, stopped } ],  // type = "production" | "sandbox"
  targets: [],
  layers: { experience: [], process: [], system: [] },
  nodes: [],      // all graph nodes — shape below
  edges: [ { source, target } ],
  backends: [],
  consumers: [],
  reuse: [],      // mule nodes sorted by .in descending
  tagDist: [ [name, count] ],   // array of 2-tuples
  clientApps: [],
  inventory: []
};
// Node item shape (used in nodes[], layers.*, backends[], consumers[], reuse[]):
// { key, label, kind, layer, tag, category, icon, in, out }
// kind = "mule" | "backend" | "consumer"
```

### Icon library — copy verbatim

```js
const MULE_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40"><rect width="40" height="40" rx="8" fill="#00A0DF"/><path d="M8,11 L13,11 L20,22 L27,11 L32,11 L32,30 L27,30 L27,19 L21,28 L19,28 L13,19 L13,30 L8,30 Z" fill="#fff"/></svg>`;
const IC = {
  mule: MULE_SVG,
  salesforce: `<svg viewBox="0 0 24 24"><path d="M14.3 6.2a3.5 3.5 0 016.1 1.9 3.1 3.1 0 01-.9 6.1 2.9 2.9 0 01-3.6 1.4 3.4 3.4 0 01-6 .3 3.9 3.9 0 01-5.2-1.8A3.5 3.5 0 015.4 8a3.6 3.6 0 016.2-2 3.5 3.5 0 012.7.2z" fill="#00A1E0"/></svg>`,
  okta: `<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5" fill="none" stroke="#007DC1" stroke-width="3.2"/></svg>`,
  peoplesoft: `<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" fill="none" stroke="#C74634" stroke-width="3.4"/></svg>`,
  oracle: `<svg viewBox="0 0 24 24"><rect x="3" y="7.5" width="18" height="9" rx="4.5" fill="none" stroke="#C74634" stroke-width="3"/></svg>`,
  sharepoint: `<svg viewBox="0 0 24 24"><circle cx="9.5" cy="8.5" r="5" fill="#036C70"/><circle cx="15.5" cy="14" r="4.3" fill="#1A9BA1"/><circle cx="11" cy="18" r="3.2" fill="#37C6D0"/></svg>`,
  azure: `<svg viewBox="0 0 24 24"><path d="M9 4l-6 15h4l1.5-4 3.5 3 2-2L9 4z" fill="#0078D4"/><path d="M11 4l4 15h6L11 4z" fill="#5EA0EF"/></svg>`,
  outlook: `<svg viewBox="0 0 24 24"><rect x="3" y="6" width="18" height="12" rx="2" fill="#0078D4"/><path d="M4 7l8 5 8-5" stroke="#fff" stroke-width="1.6" fill="none"/></svg>`,
  sftp: `<svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="6" rx="1.6" fill="#5E6B7B"/><rect x="3" y="13" width="18" height="6" rx="1.6" fill="#8895A7"/><circle cx="7" cy="7" r="1.2" fill="#fff"/><circle cx="7" cy="16" r="1.2" fill="#fff"/></svg>`,
  smb: `<svg viewBox="0 0 24 24"><path d="M4 7a2 2 0 012-2h4l2 2h6a2 2 0 012 2v7a2 2 0 01-2 2H6a2 2 0 01-2-2V7z" fill="#F0A93B"/></svg>`,
  crypto: `<svg viewBox="0 0 24 24"><rect x="5" y="10" width="14" height="10" rx="2" fill="#3B4A5A"/><path d="M8 10V8a4 4 0 018 0v2" stroke="#3B4A5A" stroke-width="2" fill="none"/><circle cx="12" cy="15" r="1.6" fill="#fff"/></svg>`,
  ai: `<svg viewBox="0 0 24 24"><rect x="5" y="7" width="14" height="11" rx="3" fill="#5E66F9"/><circle cx="9.5" cy="12.5" r="1.4" fill="#fff"/><circle cx="14.5" cy="12.5" r="1.4" fill="#fff"/><path d="M12 4v3M8 18v2M16 18v2" stroke="#5E66F9" stroke-width="2" stroke-linecap="round"/></svg>`,
  oanda: `<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" fill="none" stroke="#1F9E5A" stroke-width="2"/><path d="M12 7v10M9.5 9.2a2.5 2.5 0 015 .3c0 3-5 1.5-5 4.5a2.5 2.5 0 005 .3" stroke="#1F9E5A" stroke-width="1.7" fill="none"/></svg>`,
  gateway: `<svg viewBox="0 0 24 24"><path d="M12 3l7 3v5c0 4.4-3 7.6-7 9-4-1.4-7-4.6-7-9V6l7-3z" fill="#0A3E7E"/><path d="M9 12l2 2 4-4" stroke="#fff" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  mulesoft: MULE_SVG,
  timesheet: `<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5" fill="none" stroke="#6B4FBB" stroke-width="2"/><path d="M12 8v4.3l3 1.8" stroke="#6B4FBB" stroke-width="2" stroke-linecap="round" fill="none"/></svg>`,
  web: `<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" fill="none" stroke="#0A3E7E" stroke-width="1.8"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18" stroke="#0A3E7E" stroke-width="1.5" fill="none"/></svg>`,
  client: `<svg viewBox="0 0 24 24"><rect x="4" y="4" width="7" height="7" rx="1.6" fill="#5E66F9"/><rect x="13" y="4" width="7" height="7" rx="1.6" fill="#8A90FF"/><rect x="4" y="13" width="7" height="7" rx="1.6" fill="#8A90FF"/><rect x="13" y="13" width="7" height="7" rx="1.6" fill="#5E66F9"/></svg>`,
  service: `<svg viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="6" rx="1.6" fill="#7B8794"/><rect x="4" y="14" width="16" height="6" rx="1.6" fill="#9AA5B1"/><circle cx="8" cy="7" r="1.1" fill="#fff"/><circle cx="8" cy="17" r="1.1" fill="#fff"/></svg>`,
};
const icon = k => IC[k] || IC.service;
```

### Nav-tab icons and tab list — copy verbatim

```js
const TICO = {
  overview: `<svg class="tico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>`,
  arch: `<svg class="tico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="4" rx="1"/><rect x="3" y="10" width="18" height="4" rx="1"/><rect x="3" y="16" width="18" height="4" rx="1"/></svg>`,
  flows: `<svg class="tico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="5" cy="12" r="2.5"/><circle cx="19" cy="6" r="2.5"/><circle cx="19" cy="18" r="2.5"/><path d="M7 11l10-4M7 13l10 4"/></svg>`,
  inv: `<svg class="tico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M8 4v16"/></svg>`,
  sys: `<svg class="tico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="5" rx="1.5"/><rect x="3" y="13" width="18" height="5" rx="1.5"/></svg>`,
  ins: `<svg class="tico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 18h6M10 21h4M12 3a6 6 0 00-4 10.5c.7.7 1 1.2 1 2.5h6c0-1.3.3-1.8 1-2.5A6 6 0 0012 3z"/></svg>`,
};

const K = DATA.kpis;
const esc = s => String(s).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

const TABS = [
  {id:'overview', label:'Overview',             ico:TICO.overview},
  {id:'arch',     label:'API-Led Architecture', ico:TICO.arch},
  {id:'flows',    label:'Integration Flows',    ico:TICO.flows},
  {id:'inv',      label:'Application Inventory',ico:TICO.inv},
  {id:'sys',      label:'Backend Systems',      ico:TICO.sys},
  {id:'ins',      label:'MuleSoft Insights',    ico:TICO.ins},
];
```

### Router / boot pattern — copy verbatim

```js
const dico = svg => `<div class="ic">${svg.replace('class="tico" ','')}</div>`;

const R = {overview:renderOverview, arch:renderArch, flows:renderFlows, inv:renderInv, sys:renderSys, ins:renderIns};

function show(id){
  document.querySelectorAll('nav.tabs button').forEach(b => b.classList.toggle('active', b.dataset.id===id));
  hideTip();
  const main = document.getElementById('main');
  main.innerHTML = `<div class="panel active" id="p-${id}">${R[id]()}</div>`;
  if(id==='flows') requestAnimationFrame(buildGraph);
  if(id==='inv') wireInv();
  location.hash = id;
}

document.getElementById('tabs').innerHTML = TABS.map(t =>
  `<button data-id="${t.id}">${t.ico}${t.label}</button>`).join('');
document.querySelectorAll('nav.tabs button').forEach(b => b.addEventListener('click', () => show(b.dataset.id)));
const _initial = (location.hash||'').slice(1);
show(_initial in R ? _initial : 'overview');
```

### Renderer function signatures (implement content per Tab Content Specifications)

```js
function renderOverview() { /* returns HTML string */ }
function renderArch()     { /* returns HTML string */ }
function renderFlows()    { /* returns HTML string containing <svg id="flowsvg"></svg> */ }
function renderInv()      { /* returns HTML string containing toolbar + tbl-wrap */ }
function renderSys()      { /* returns HTML string */ }
function renderIns()      { /* returns HTML string */ }
function buildGraph()     { /* called via requestAnimationFrame after renderFlows(); uses DOM SVG API */ }
function wireInv()        { /* attaches input/change listeners for #invSearch, #invEnv, #invLayer, #invStatus and th[data-c] sort */ }
```

---

## Footer

```
Generated from Anypoint Platform network-graph export · {customerName} ·
Visual language per MuleSoft API-Led architecture template.
Topology reflects the Production business group dependency graph; inventory spans all environments.
```

---

## Constraints

- **Zero external dependencies** — no CDN, no `<link>` tags, no `<script src>`. Everything is inline.
- **Offline-ready** — the file must render correctly with no internet access.
- **Single file** — HTML + CSS + JS + all assets (logo, icons) in one `.html` file.
- **No framework** — vanilla JS only. No React, Vue, D3, Chart.js, etc.
- **MuleSoft branding preserved** — keep the MuleSoft logo, color palette, and API-Led terminology regardless of customer name.
- **Customer-agnostic text** — all narrative descriptions should be generic enough to apply to any industry vertical. Do not hard-code vendor product names (Workday, PeopleSoft, Okta, Salesforce, etc.) into the descriptive text; use the API-Led layer terms instead.
- **Responsive** — the layout should work on 1280px+ screens. The two-column `cols` grid collapses to single column below 900px.
