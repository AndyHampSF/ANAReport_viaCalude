# Reference: MuleSoft Estate Report — Input, DATA Contract, Metrics and Tabs

> **Status:** this is the current reference for skill v3.3.0 (build_data.py v3.3.0, updated
> 2026-10-05). It replaces the original "build the HTML by hand" brief.
>
> **Sources of truth:** `scripts/build_data.py` (the transformation) and
> `mulesoft_arch_template.html` (rendering and design). This document describes them. If it
> ever disagrees with the code, the code wins, so update this file.
>
> **To produce a report**, follow `SKILL.md`: run `scripts/build_report.py <export.json>`.
> Nothing in this document needs to be done by hand.

---

## 1. Pipeline overview

```
Anypoint network-graph export (.json)
        │
        ▼
scripts/build_data.py ──► DATA object (JSON on stdout; reconciliation + benchmark on stderr)
        │      ▲
        │      └── data/ANA Industry Data Matrix - Golden Template.xlsx  (peer benchmark)
        │          data/customer_ou_map.json                             (customer → OU)
        ▼
scripts/build_report.py ──► replaces `const DATA = /* DATA_PLACEHOLDER */ null;`
        │                   in mulesoft_arch_template.html
        ▼
{masterOrgName}_Mule_Architecture.html   (single self-contained file, all JS/CSS inline)
```

The template's rendering code is static. Only the DATA object differs between customers.

---

## 2. Input: the Anypoint network-graph export

### 2.1 Top level

```json
{
  "masterOrg": { "masterOrgId": "<uuid>", "masterOrgName": "Acme Corp", "extractOn": "15_07_2026_16_37_56" },
  "orgs":  [ { "orgId": "<uuid>", "orgName": "Acme Corp" }, { "orgId": "<uuid>", "orgName": "Acme IT" } ],
  "envs":  [ { "envId": "<uuid>", "envName": "Production", "envType": "production" } ],
  "apps":  [ { "appid": "...", "appname": "acme-exp-orders-api", "envid": "<uuid>", "envtype": "production",
               "orgid": "<uuid>", "status": "RUNNING", "target": "CH2.0 - private-space",
               "minsize": 0.1, "maxsize": 0.1, "memory": "...", "replica": 1, "region": "cloudhub-eu-west-2" } ],
  "production": { "dependencies": { "nodes": [...], "edges": [...] }, "clientgroup": [...], "policies": [] },
  "sandbox":    { "dependencies": { "nodes": [...], "edges": [...] }, "clientgroup": [...], "policies": [] }
}
```

- `apps[]` is the deployment inventory across all environments. It drives the Overview KPIs,
  the env chart and the inventory.
  - `status` values seen: `RUNNING`, `STARTED`, `SCALING`, `NOT_RUNNING`, `UNDEPLOYED`,
    `UNRECOVERABLE_RUNTIME_ERROR`.
  - `target` values seen: `CH1.0`, `CH2.0 - shared-space`, `CH2.0 - private-space`.
- `production` / `sandbox` hold the Anypoint Visualizer dependency graphs. The topology,
  backends and reuse metrics use **production**. Sandbox reuse is computed but not displayed.
- A nodes/edges-only export (no `production` wrapper) is also accepted.

### 2.2 Nodes (`*.dependencies.nodes[]`)

| `type` | Meaning | Key fields |
|---|---|---|
| `mule` | Deployed Mule app | `id, label, layer?{label}, tags?[{label}]`. CloudHub exports also have `host`. RTF exports also have `appName, environmentId, organizationId, deploymentTarget:"rtf", serverId, clusterId` |
| `http` | An HTTP endpoint. It's **either** an internal call to another Mule app via its hostname (e.g. `app-name-97pqx7.internal-dxakq7.gbr-e1.cloudhub.io`) **or** a real external system | `id, label, host` |
| `other` / `db` / `sfdc` | Non-HTTP backend (SFTP, Azure storage, database, Salesforce…) | `id, label` |
| `clientGroup` | API Manager consumer group for one API | `id, label, numberOfClientApplications` |

`organizationId` (used for the per-business-group reuse breakdown) is only present on some
exports. Without it, every Mule node falls into one unnamed group.

### 2.3 Edges

`{ "id", "sourceId", "targetId", "valid" }`. `sourceId` calls `targetId`.

### 2.4 Client groups: known export quirk

`production.clientgroup` is a list that **mixes two things**:

- top-level `{key, value}` dicts, whose keys are **sandbox** clientGroup node ids
- one nested **list** of `{key, value}` dicts, whose keys are the **production** clientGroup
  node ids

Each `value` is `[{name, client_id}]`. `build_data.py` flattens the list and keeps only
entries whose `key` is a clientGroup node in the production graph.

The named list is **capped at 50 entries per API**; `numberOfClientApplications` on the node
is the true count. Reuse metrics use the node count. The `clientApps` name list may be
incomplete for APIs with more than 50 consumers.

### 2.5 Other known quirks

- **Empty `apps[]`** (seen with Runtime Fabric). The script treats every production Mule node
  as one running app in one environment. The env chart and inventory are empty.
- **Apps in deleted environments** aren't in the export at all.
- **Duplicate environment names** within one org (e.g. two "Dev" in one business group).
  `envRows` groups by **name**, so same-named environments merge into one row.
- **Duplicate deployments** (same app name in one env, e.g. a shared-space copy and a
  private-space copy) appear as separate inventory rows.

---

## 3. Transformation rules (`build_data.py`)

### 3.1 Layer classification

1. If the Mule node has `layer.label` ∈ {Experience, Process, System}, use it.
2. Otherwise use `layer_of_name(label)`, case-insensitive, first match wins:
   - **experience**: ends `-eapi`, contains `-eapi-` or `exp-`, or starts `sgn-e`
   - **process**: ends `-papi`, contains `-papi-`, `prc-` or `-pro-`, or starts `sgn-p`
   - **system**: ends `-sapi`, contains `-sapi-` or `sys-`, or starts `sgn-s`
   - else **other** → `layerOther`. These apps are not in `layers`, not in `uniqueApis`, and
     are drawn in the Backend column of the flows graph.

The inventory and reuse `perApp` lists always use the name rules, because `apps[]` has no
layer field.

### 3.2 Consumers

All `clientGroup` nodes merge into one node, `key: "consumer-merged"`, labelled
`"<Σ numberOfClientApplications> Client Apps"`. All their edges are remapped to it.

### 3.3 Backends (`http`, `other`, `db`, `sfdc` nodes)

**First, check for internal Mule calls.** Take the hostname stem (the text before the first
`.`). If the stem, the raw label, or the stem with a trailing `-[a-z0-9]{6}` removed equals a
Mule app label, the node is remapped to that app and is **not** a backend.

**Otherwise, consolidate to a friendly name** (`consolidate_backend`), first match wins:

1. `SIMPLE_LABEL_MAP`: exact simple labels (`dynamodb`, `sftp`, `email`, `other`, `database`, …)
2. `BRAND_MAP`: substring match. Specific overrides come first (`fibregateway`, `my.site.com`,
   `login.microsoft`), then brands (Salesforce, Okta, AWS, Azure, SharePoint, SFTP, …,
   `gateway`).
3. `PRODUCT_MAP`: known products/partners (Entra ID, PayByPhone, Vertex, Corpay, FleetCor…)
4. Domain extraction: `api.foo.co.uk` → "Foo API" (handles multi-part TLDs)
5. Fallback: the label, titleised

Each backend gets a key `backend-<friendly-name>`, a `category` (`backend_category`) and an
`icon` (`_icon_for`, from the raw label). Several endpoints can consolidate into one backend.

### 3.4 Edges and reconciliation

Every node id maps to an output key, and every raw edge is classified as one of:

- **kept**: a unique (source, target) pair
- **duplicate**: collapsed, because consolidation merged its endpoints
- **self-loop**: both ends map to the same key
- **unresolved**: an endpoint id isn't in the node list

The script aborts unless `kept + duplicates + self-loops + unresolved = raw`. `kpis.flows`
is the kept count and `kpis.flowsRaw` is the raw count. Output edges reference node
**labels**: `{source: label, target: label}`.

### 3.5 Apps / inventory (from `apps[]`)

- The environment name comes from `envs[]` by `envid`.
- **Running** = status in `RUNNING_STATES` = `RUNNING`, `STARTED`, `SCALING`. Everything
  else counts as stopped.
- `vcores` = `minsize` (default 0.1). `totalVcores` = `vcores × replica`. Each `envRows`
  entry also sums `runningVcores`.

### 3.6 Reuse metrics (`compute_reuse_stats`, production graph)

For each production Mule API, *consumers* = incoming edges, with an edge from a clientGroup
counting as that group's `numberOfClientApplications`.

| Field | Definition |
|---|---|
| `apisTotal` | Production Mule nodes |
| `consumedMore` / `consumedOnce` / `consumedNone` | APIs with >1 / exactly 1 / 0 consumers |
| `consumers` | Σ consumers |
| `reuseInstances` | consumers − APIs with consumers |
| **`reuseRate`** | reuseInstances ÷ consumers |
| **`reuseIndexApis`** | consumers ÷ APIs with consumers |
| `reuseIndexAll` | consumers ÷ apisTotal |
| **`reusability`** | consumedMore ÷ APIs with consumers |
| `byLayer[layer]` | `{total, more, once, none, reuseRate}` where this `reuseRate` = more ÷ (more + once) |
| `perApp` | `[{name, consumers, layer}]` for APIs with ≥1 consumer, sorted descending |

`byBG` repeats the headline metrics per business group (`organizationId` → `orgs[]`
name), with `title` = `"<master> → <bg>"`. Groups with no APIs are excluded.

These definitions match the old spreadsheet-based ANA process. One difference: the old
process counted the named client list, which is capped at 50, so it under-counts consumers
for APIs with more than 50 client apps.

### 3.7 Peer benchmark (`compute_benchmark`)

- **Source:** `data/ANA Industry Data Matrix - Golden Template.xlsx`, sheet `Data Tab`. It
  uses the columns `OU`, `# APIs Total` and `% Reuse rate (over all APIs)`. Rows with 0 APIs
  or a non-numeric rate are dropped.
- **OU lookup:** `data/customer_ou_map.json` maps a lowercase name fragment to a list of OU
  values. It matches as a substring of `masterOrgName`, in either direction. Keys starting
  with `_` are ignored.
- **Peer set:**
  1. Same OU and an API count of 0.35–2.5× the customer's production API count.
  2. If that gives fewer than 5 peers, the whole OU.
  3. If still fewer than 5, all rows.
- **Result:** the mean reuse rate, emitted as `reuseAnalysis.benchmarkAvg`. It's `null` if
  pandas or openpyxl is missing or the matrix can't be read. In that case the template falls
  back to 0.38.

---

## 4. DATA contract (what `build_report.py` injects)

```js
const DATA = {
  meta: { customer, masterOrg, extractOn, orgs: [orgName], generated: "" },
  kpis: {
    totalApps, running, stopped,      // from apps[]; running = RUNNING|STARTED|SCALING
    prod, sandbox,                    // apps by envtype
    envs,                             // distinct env names with apps (= envRows.length)
    uniqueApis,                       // expCount + procCount + sysCount (excludes layerOther)
    backends, expCount, procCount, sysCount,
    flows, flowsRaw                   // unique consolidated edges / raw edge count
  },
  envRows:   [ { name, type /*production|sandbox*/, total, running, stopped, runningVcores } ],  // sorted by total desc
  targets:   [],                                      // reserved, always empty
  layers:    { experience: [Node], process: [Node], system: [Node] },
  layerOther: [Node],                                 // Mule apps the layer rules didn't classify
  nodes:     [Node],                                  // every output node (mule + consumer + backend)
  edges:     [ { source: label, target: label } ],
  backends:  [Node],                                  // sorted by in desc
  consumers: [Node],                                  // 0 or 1 merged client node
  reuse:     [Node],                                  // top 8 Mule nodes by in-degree
  tagDist:   [ [tagLabel, count] ],                   // from tags[0].label; often empty
  clientApps:[ name ],                                // production client-app names, sorted, deduped
  inventory: [ { name, env, envtype, layer, status, target, vcores, replica, totalVcores, region } ],
  reuseAnalysis: {
    production: ReuseStats | null,
    sandbox:    ReuseStats | null,                    // computed, not rendered
    benchmarkAvg: number | null,                      // 0–1
    byBG: [ { bg, title, apisTotal, consumedMore, consumedOnce, consumedNone,
              consumers, reuseInstances, reuseRate, reusability, perApp } ]
  }
};
// Node: { key, label, kind: "mule"|"consumer"|"backend",
//         layer: "experience"|"process"|"system"|"other"|"consumer"|"backend",
//         tag, category, icon, in, out }
// ReuseStats: see §3.6
```

**The template also reads `DATA.businessGroups`**, an optional list of
`[{name, total, running, prod, sandbox, experience, process, system, other}]` that drives
the Overview's "Business Groups" cards. `build_data.py` **does not currently emit it**, so
that section is hidden. It's a known gap; see the README's open items.

---

## 5. Report tabs (as rendered by the template)

The header shows the customer, master org, business groups (`meta.orgs`) and extract date.
The footer is generic.

| # | Tab | Content | DATA used |
|---|---|---|---|
| 1 | **Overview** | 6 KPI tiles: total apps, running/total, unique APIs, flows (prod), backends, active environments. Also: layer distribution chips and narrative, environment bars (running/stopped and running vCores), business-domain tag chips, the OAuth client list, and Business Groups cards (only if `businessGroups` is present) | `kpis`, `envRows`, `tagDist`, `clientApps`, `businessGroups` |
| 2 | **API-Led Architecture** | Consumer row → Experience / Process / System swimlanes of API tiles. A tile shows a reuse badge when `in > 1`. The backend row is underneath | `consumers`, `layers`, `backends` |
| 3 | **Integration Flows** | Interactive SVG in 5 columns (Consumer · Experience · Process · System · Backend), with hover highlight, a layer filter and name search. Nodes with layer `other` are drawn in the Backend column | `nodes`, `edges` |
| 4 | **Application Inventory** | Searchable/sortable table filterable by env, layer and status (Running = RUNNING/STARTED/SCALING, Stopped = NOT_RUNNING, Undeployed) | `inventory`, `kpis` |
| 5 | **Backend Systems** | Cards with icon, name, category (by icon) and in-degree "System-API connections" | `backends` |
| 6 | **MuleSoft Insights** | Three cards: % of APIs with in-degree >1 (Mature ≥40%, Developing ≥20%), operational health (running ÷ total) and the client-app count. Also the top 8 most-shared APIs, and 4 recommendations | `layers`, `kpis`, `reuse`, `clientApps` |
| 7 | **Reuse Analysis** | Production reuse KPIs (rate, reusability, index, consumers, APIs, maturity stage); a consumer-distribution donut and by-layer bars; a metric breakdown table; a benchmark bar; a per-BG drill-down (only shown if `byBG` has 2+ groups); and a ranked list of the most consumed APIs | `reuseAnalysis` |

**Maturity stage** (from the production reuse rate): Mature API-Led ≥ 50% · Industrialised ≥
40% · Developing ≥ 20% · Incubating < 20%. The benchmark bar shows the customer's rate against
`benchmarkAvg`. The "low 10% / high 70%" figures are fixed values in the template.

**Static text to be aware of:** some recommendation text on the Insights tab is fixed in the
template and isn't derived from data. For example, it says "All apps are at 0.1 vCore
replicas" and refers to "HRIS sync". Sense-check it before presenting to a customer.

---

## 6. Design rules

- One self-contained HTML file. No CDN, `<link>` or `<script src>`, and no framework (vanilla JS).
- Keep the MuleSoft branding (logo, palette: navy `#052D60`, teal `#0BA49B`, indigo `#5E66F9`,
  MuleSoft blue `#00A0DF`) and API-led terminology.
- Narrative text should stay customer-agnostic. The customer name comes only from `meta`.
- The CSS, icons and renderers in `mulesoft_arch_template.html` are the design reference. Don't
  restyle per customer. Template changes affect every customer's report, so agree them with
  the user and regenerate all reports afterwards.
