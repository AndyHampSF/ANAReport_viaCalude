# ANA Report — MuleSoft Estate Architecture Report Generator

Turns a MuleSoft **Anypoint network-graph JSON export** (the ANA export) into a single,
self-contained, interactive **HTML architecture report** for a customer. It covers
API-led layers, integration flows, backends, app inventory, and production reuse
metrics benchmarked against industry peers.

This is a rebuild of an older semi-manual, spreadsheet-based ANA process. The reuse
metrics are designed to match that process (see [Validation history](#validation-history)).

> **Customer data is not in this repo.** Exports and generated reports are kept on the
> owner's machine only (see `.gitignore`). The repo holds the code, the HTML template
> and the ANA Industry Data Matrix used for benchmarking. The repo must stay **private**
> because the matrix contains peer customer data.

---

## Repository layout

```
.
├── README.md                         ← this file
├── .gitignore                        ← keeps customer data out
├── .gitattributes                    ← LF line endings on every OS (identical checkouts)
├── tools/
│   └── regression_check.py           ← snapshot/compare outputs across all local exports
└── mulesoft-estate-report/           ← the Claude Code skill (self-contained)
    ├── SKILL.md                      ← skill definition: the run procedure Claude follows
    ├── mulesoft_arch_template.html   ← report template (all CSS/JS inline); DATA is injected
    ├── prompt_mulesoft_architecture_html.md  ← reference: input format, DATA contract, metrics, tabs
    ├── scripts/
    │   ├── build_report.py           ← ENTRY POINT: export JSON → finished HTML (one command)
    │   └── build_data.py             ← export JSON → DATA object (the real logic lives here)
    └── data/
        ├── ANA Industry Data Matrix - Golden Template.xlsx  ← peer benchmark source
        └── customer_ou_map.json      ← customer name → industry (OU) for benchmarking
```

Not in the repo, but present locally in the working folder
(`C:\Users\ahampshire\claude-projects\ANA_Reports\`):

| Local file(s) | What it is |
|---|---|
| `*-network_graphs-*.json`, `TalkTalk.json` | Customer ANA exports (inputs) |
| `{Customer}_Mule_Architecture.html` | Generated reports (outputs) |
| `jlr_data.json`, `sgn_data.json`, `informa_data.json` | Old intermediate DATA files from earlier runs |
| `_regress/` | Before/after regression snapshots and backups (see [Regression check](#regression-check-run-after-any-script-change)) |
| `mulesoft-estate-report.zip` | Stale packaged copy of the skill from Aug 2026, which predates the fixes below |

---

## Quick start

### Prerequisites

**Python 3.8 or newer. Nothing else.** There are no packages to install. The Industry
Matrix spreadsheet is read with Python's standard library. It works the same on Windows,
macOS and Linux.

The Python command differs by machine: `python3` (macOS/Linux, and often Windows), `python`
(Windows), or `py -3` (Windows launcher). Use whichever prints a 3.x version. When Claude
runs the skill, it works this out itself.

### Generate a report (one command)

```bash
python3 mulesoft-estate-report/scripts/build_report.py "<export>.json"
```

This writes `{masterOrgName}_Mule_Architecture.html` next to the input. Characters that
aren't safe in filenames become `_`. Options:
- `-o <folder>` writes the report elsewhere.
- `--keep-data` also saves the DATA JSON.
- `--open` opens the report in your browser.
- `--check` validates the export without building anything.

It prints the following to stderr:
- an **input check**: the export's structure, an empty `apps[]`, a customer missing from the
  OU map, a missing matrix
- the **edge reconciliation**: `accounted for` must equal `raw edges`. If any edge is lost,
  the script exits with `RECONCILIATION FAILED` and writes nothing.
- the **benchmark** line
- a **summary** of the key numbers and any warnings

Exit codes: 0 ok, 1 build failed, 2 invalid input. Open the HTML by double-clicking it.
It has no external dependencies.

`build_report.py` runs `build_data.py` and injects its output into the template. You can
run `build_data.py <export.json> > data.json` on its own to inspect the DATA object.

**Gotchas:**
- The input is always the full `*-network_graphs-*.json` export, **not** the smaller
  `*_data.json` files (those are old script outputs).
- Quote paths: export filenames usually contain spaces.
- If the benchmark line says `using all industries`, add the customer to
  `customer_ou_map.json`.

### Using it as a Claude Code skill (optional)

Copy the whole `mulesoft-estate-report/` folder, **including `data/`**, to
`~/.claude/skills/mulesoft-estate-report/`. Then asking Claude to "generate the MuleSoft
report from <file>" triggers it. `SKILL.md` holds the procedure Claude follows: validate,
run `build_report.py`, review, report. It is **not** currently installed as a skill; runs
have been done from this folder.

**Cross-platform verification (2026-10-05):** the same four exports were run on Windows 11
(Python 3.14) and on Ubuntu 22.04 under WSL (Python 3.10, no extra packages). Each run used a
fresh git clone. Both produced byte-identical HTML. macOS uses the same code paths as Linux
(POSIX, `python3`); it wasn't tested directly.

---

## The report

There are seven tabs: Overview · API-Led Architecture · Integration Flows · Application Inventory ·
Backend Systems · MuleSoft Insights · Reuse Analysis. The template also has a Business Groups
section in Overview, but it stays hidden because the script doesn't produce that data yet (see
open items). For a per-tab breakdown of the content and the DATA fields each tab uses, see
`mulesoft-estate-report/prompt_mulesoft_architecture_html.md` §5.

### Input export format

Top-level keys: `masterOrg`, `orgs`, `envs`, `apps`, `sandbox`, `production`.
`production` / `sandbox` each contain `dependencies.nodes`, `dependencies.edges`,
`clientgroup`, `policies`.

- `apps[]`: the deployment inventory (`appname, envid, envtype, status, target, minsize, replica, orgid, region…`). Drives the Overview KPIs, env chart and inventory.
- `nodes[]`: types `mule`, `http`, `other`, `db`, `sfdc`, `clientGroup`.
- `edges[]`: `sourceId → targetId`.

### What `build_data.py` does

1. **Classifies Mule apps into API-led layers** from the node's `layer` field, else from the
   name (`layer_of_name`): `-eapi`/`exp-` → Experience; `-papi`/`prc-`/`-pro-` → Process;
   `-sapi`/`sys-` → System; anything else → "Other".
2. **Merges all `clientGroup` nodes** into one "N Client Apps" consumer node.
3. **Consolidates backends** (`http`/`other`/`db`/`sfdc` nodes) into business-friendly names,
   using a 4-tier match: brand (`BRAND_MAP`) → product/partner (`PRODUCT_MAP`) → domain
   extraction (`api.foo.co.uk` → "Foo API") → titleised label.
4. **Remaps internal Mule calls.** An `http` node whose hostname is actually a deployed Mule
   app (including CloudHub 2/RTF hostnames with a 6-char suffix, such as
   `app-name-97pqx7.internal-….cloudhub.io`) is pointed at that app, not counted as a backend.
5. **Remaps and deduplicates edges, then reconciles them.** It requires
   `raw = kept + duplicates + self-loops + unresolved` and aborts otherwise. `flows` = kept.
6. **Computes reuse metrics** for production and sandbox, and per business group.
7. **Calculates the peer benchmark** from the Industry Matrix. Peers come from the customer's
   OU (looked up in `customer_ou_map.json`) and have 0.35–2.5× the customer's API count. If
   there are fewer than 5 such peers, it broadens to the whole OU, then to all rows.

### Reuse metric definitions (match the old spreadsheet process)

For production Mule APIs, *consumers* = incoming edges, with each `clientGroup` expanded by
its `numberOfClientApplications`.

| Metric | Formula |
|---|---|
| APIs with consumers | consumedMore + consumedOnce |
| **Reuse rate** | (consumers − APIs with consumers) ÷ consumers |
| **Reuse index** | consumers ÷ APIs with consumers |
| **Reusability** | consumedMore ÷ APIs with consumers |

---

## Known export quirks (all handled unless noted)

| Quirk | Where seen | Handling |
|---|---|---|
| `production.clientgroup` mixes **sandbox** entries (top-level `{key,value}` dicts) with the **production** ones (nested in a list) | All exports | Script flattens the list and keeps only entries keyed by a production `clientGroup` node id |
| The named client-app list is **capped at 50 per API**, but the node's `numberOfClientApplications` is the true count | TalkTalk (3 APIs: 80/77/58) | Reuse uses the node count. The Client Apps name list is therefore incomplete for those APIs |
| **`apps[]` empty** (Runtime Fabric deployment; nodes carry `deploymentTarget: rtf`) | TalkTalk | Not fixed. The script falls back to "every Mule node = 1 running app, 1 env", so the env chart and inventory are empty. Ask for a re-export with deployment data |
| Internal CH2/RTF hostnames carry a `-xxxxxx` suffix | TalkTalk, JLR, Informa | Suffix stripped before matching to Mule apps (fix 2026-10-05) |
| `SCALING` status | JLR, Informa | Counted as running everywhere (`RUNNING_STATES`) |
| Apps in **deleted environments** (e.g. JLR env `737a11c2`) aren't in the export | JLR | Not fixable from the export. Another tool shows them as "INVALID" |
| Some business groups have **two environments with the same name** (e.g. two "Dev" in Korea/MENA) | JLR | When comparing app lists, key apps on `envId`, not env name. The report's env chart groups by **name**, so same-named envs share one row (JLR: 36 env IDs with apps → 18 rows) |
| Same app name deployed twice in one env (shared-space stopped + private-space running) | JLR (7 cases) | Kept as two inventory rows; it's real duplication in the estate |

---

## Change log

### 2026-10-05 (latest): v3.4.0, platform independence

The goal: the skill behaves identically on Windows, macOS and Linux, and the person running
it doesn't need to know which platform they're on.

1. **No third-party packages.** pandas/openpyxl were replaced by a standard-library .xlsx
   reader (`read_xlsx_sheet`). Before this change, Ubuntu (no pandas, no pip) silently
   produced a report without the benchmark. Verified identical to pandas: the same 291 peer
   rows in the same order, and 0 differences across 37,037 benchmark cases. Averages are summed
   in numpy's pairwise order, because a plain sum gave 182 cases that rounded the last digit
   differently on .xxxx5 boundaries.
2. **Byte-identical output on every OS.** Files are read and written as UTF-8 with LF line
   endings (Windows previously wrote CRLF). `.gitattributes` forces LF checkouts regardless of
   `core.autocrlf`.
3. **Validation built into `build_report.py`.** Use `--check` to validate only. Exit codes:
   0/1/2. This replaces the ad-hoc shell snippets SKILL.md used to need.
4. **`--open`** opens the report in the default browser on any OS. Output filenames are
   sanitised to characters valid on every OS. Console messages are plain ASCII (Windows
   showed literal `─` escape codes or garbled characters before).
5. **SKILL.md:** Claude finds a working Python itself (`python3` → `python` → `py -3`) and
   never asks the user about their OS.
6. **`tools/regression_check.py`** replaces the bash-only regression loop.

No report content changed. All four customers' DATA is identical to v3.3.0.

### 2026-10-05 (later): v3.3.0, docs and one-command runner

Prompted by a check of whether an extracted copy of the skill behaves the same as the runs done here.

1. **New `scripts/build_report.py`** runs export → finished HTML in one command. Previously,
   SKILL.md told Claude to inject DATA by hand, i.e. to re-type 100–350 KB of HTML, which
   risked a truncated or altered file. Output is byte-identical to the previous method.
2. **`SKILL.md` rewritten.** Additions: prerequisites (pandas/openpyxl), the `data/` folder and
   benchmark, onboarding a customer to `customer_ou_map.json`, input validation, Windows notes,
   and a complete sharing list (the old list left out `data/`, which silently dropped the
   benchmark). Removed: the broken step numbering and a dead link to a file on the original
   author's machine.
3. **`prompt_mulesoft_architecture_html.md` rewritten** from the original "hand-build the HTML"
   brief into an accurate reference covering the input format, transformation rules, DATA
   contract, metric definitions and the 7 tabs.
4. **"Active environments" KPI** now counts distinct env names with apps. It used to count
   env *types*, so the maximum was 2. JLR 2→18, SGN 2→3, Informa 2→6, TalkTalk unchanged (1).
5. **Exports are now read as UTF-8** regardless of the Windows locale. No effect on current
   exports, which are all ASCII.
6. **Template comment updated** to say DATA is injected by `build_report.py`. Comment only,
   no rendering change.

### 2026-10-05: script v3.2.0 + fixes (TalkTalk onboarding and validation)

All changes were checked against all four exports. Only the intended numbers moved.

1. **CH2/RTF hostname suffix stripped** when matching internal calls to Mule apps. This removed a
   fake "Cloudhub API" backend. Effect: TalkTalk 22 calls remapped; JLR backends 20→19 and flows
   71→64; Informa flows 388→384.
2. **`-pro-` recognised as the Process layer** (TalkTalk naming: `pro-whs-pro-…`). No effect on
   other customers.
3. **Backend name overrides** added at the top of `BRAND_MAP`: `fibregateway` → Fibre Gateway,
   `my.site.com` → Salesforce Experience Cloud, `login.microsoft` → Microsoft Entra ID.
4. **`customer_ou_map.json`**: added `talktalk` → "Technology, Media, Telecomm".
5. **Client Apps list now uses production client groups only.** Previously it showed sandbox
   client names.
6. **`SCALING` counted as running in the headline KPI** too, so it now matches the env chart.
   JLR running 139→140; Informa 399→401.

---

## Validation history

### TalkTalk vs the old spreadsheet process

| Metric | Old process | This script |
|---|---|---|
| Reusability | 51.28% | 51.28% |
| Reuse rate | 89.32% | 90.93% |
| Reuse index | 9.36 | 11.03 |

Both use the same 39 APIs with consumers. The difference is total consumers: 365 vs 430.
The old process counted the **named client-app list, which is capped at 50 per API**. The
script uses `numberOfClientApplications` (80, 77 and 58 on three APIs), which accounts for
the missing 65. The script's figure is believed correct. To confirm, check the contract count
in API Manager for `pro-whs-exp-partners-security-api-v1`. If it shows 80, the script is right.

### JLR app list vs the "JLR Admin Data" platform report (5 Oct 2026)

The comparison source was `C:\Users\ahampshire\claude-projects\JLR Admin Data\JLR-Mulesoft-Platform-Report.html`,
which embeds `const DATA = {...}` with an `apps[]` list. It compared well: 205 apps (Aug export) − 21 gone + 6 new = 190.

- 177 apps matched on name + envId. 100% agreement on business group and platform, and 169/170 on status.
- The 21 apps only in the export were all not running in August: 14 undeployed CH1 apps, 5 stopped
  copies in duplicate-named Korea/MENA envs, and 2 other stopped apps.
- The 6 apps only in the admin report: 3 new Japan CH2 deployments (CH1→CH2 migration), and 3 apps in
  deleted env `737a11c2` (`jrl-goldstar`, `jlr-eu-eapi-commerce-cloud`, `jlr-eu-eapi-smart`).

---

## Customers processed (as of 2026-10-05)

| Customer | Export file (local) | Extracted | Notes |
|---|---|---|---|
| Jaguar Land Rover | `JLR Global 360-network_graphs-17_08_2026_06_49_41.json` | 17 Aug 2026 | 205 apps / 140 running, 18 envs, 64 flows |
| SGN | `SGN-network_graphs-20_04_2026_11_21_22.json` | 20 Apr 2026 | 149 apps, 3 envs, 94 flows |
| Informa | `Global Support-network_graphs-30_06_2026_10_35_02.json` | 30 Jun 2026 | 618 apps / 401 running, 6 envs, 384 flows |
| TalkTalk | `TalkTalk.json` | 21 Sep 2026 | RTF, no `apps[]`; 47 prod Mule apps, 111 flows; business group "Wholesale" |

---

## Onboarding a new customer: checklist

1. **Validate the export:** `python3 mulesoft-estate-report/scripts/build_report.py "<export>.json" --check`.
   This checks the structure, edges pointing at missing nodes, an empty `apps[]`, and whether
   the customer is in the OU map and the matrix is present.
2. **Do a baseline run** (without `--check`) and inspect:
   - the "unclassified" count: apps the layer rules didn't classify, which may mean a new
     naming convention
   - the backend list: generic or wrong names, or a big "Cloudhub API" backend, which means
     internal calls aren't being remapped
   - the benchmark line
3. **Add the customer to `customer_ou_map.json`** (substring match on `masterOrgName`), or the
   benchmark falls back to all industries.
4. If you change the script, **run the regression check** below before regenerating anything.

## Regression check (run after any script change)

```bash
python3 tools/regression_check.py snapshot before     # before the change
# ... make the change ...
python3 tools/regression_check.py snapshot after
python3 tools/regression_check.py compare before after
```

It runs `build_data.py` on every customer export in the repo root, found automatically,
and reports for each customer either `identical` or exactly which DATA keys and KPIs
changed. Snapshots go to `_regress/<label>/`, which git ignores because it holds customer
data. On a fresh clone there's no baseline, so take one *before* changing anything.

---

## Open items / ideas

- **TalkTalk inventory gap.** Request a re-export that includes `apps[]`. Alternatively, rebuild
  per-environment app counts from the graph nodes' `environmentId` (47 prod + 204 sandbox
  Mule nodes across DEV/SIT/UAT/STG/PVE). Status still wouldn't be available.
- **TalkTalk reuse rate (90.9%)** is driven by large client groups (46–80 apps on single APIs).
  Sense-check it before presenting.
- **TalkTalk:** `pro-whs-sys-som2-appointing-api-v1` is called in production but isn't deployed
  there. It still shows as a "Cloudhub API" backend, and it's a talking point for the customer.
- **JLR clean-up talking points:** 7 duplicate app deployments, and 3 orphaned apps in a deleted environment.
- **Business Groups section is hidden.** The template's Overview can show per-business-group
  cards (apps, running, prod/sandbox, layer mix), but only if `DATA.businessGroups` exists, and
  `build_data.py` doesn't produce it yet. The data is available (`apps[].orgid` → `orgs[]`).
  Adding it would make a new section appear in every multi-BG report.
- **Fixed recommendation text** on the Insights tab, e.g. "All apps are at 0.1 vCore
  replicas" and "HRIS sync", isn't derived from data. Sense-check it before presenting.
- **Unclassified ("other") Mule apps** are drawn in the Backend column of the Integration Flows
  graph. That's template behaviour.
- **Sandbox reuse** is computed (`reuseAnalysis.sandbox`) but not shown anywhere in the report.
- The original strategy doc `BACKEND_CONSOLIDATION_STRATEGY.md` (on the original skill author's
  machine) isn't in this repo. `prompt_mulesoft_architecture_html.md` §3.3 now documents the rules.
- Optional: install the skill to `~/.claude/skills/` so it's triggerable by name.

---

## Notes for Claude (continuing this project)

- **Platform:** never assume an OS or ask the user about it. Find Python as SKILL.md describes,
  keep the scripts standard-library only (no pip dependencies), and read/write files as
  UTF-8 with LF line endings.
- **Generate reports only with `scripts/build_report.py`.** Never hand-write the DATA
  transformation or the HTML, and don't edit the template's design. `SKILL.md` is the run
  procedure; `prompt_mulesoft_architecture_html.md` is the reference for the input format,
  DATA contract and metrics. Keep both in step with the code whenever the script or
  template changes.
- **Before changing `build_data.py`:** explain the problem and the proposed fix to the user and
  get agreement. Then snapshot, change, and run `tools/regression_check.py` across *all* local exports,
  and report exactly which numbers moved for which customer. Fixes for one customer have
  changed others before (e.g. the hostname-suffix fix changed JLR and Informa).
- **After a script change**, ask before regenerating other customers' reports. Back up the
  existing HTML to `_regress/old_html/` first.
- **Validate new exports** with the onboarding checklist before generating, and surface anomalies.
- **Never commit customer data** (exports, reports, `_regress/`). `.gitignore` handles this, so
  don't override it. The Industry Matrix is committed deliberately, and the repo must stay private.
- When comparing app lists with other sources, key on `(appName, envId)`, not env name.
- User preferences: collaborative (check before non-trivial or irreversible actions), concise
  but explain *why*, intermediate experience level, newish to Claude Code.
- Remote: `https://github.com/AndyHampSF/ANAReport_viaCalude` (private), branch `main`.
