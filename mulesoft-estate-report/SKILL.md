---
name: mulesoft-estate-report
description: >
  Generate a polished, single-file interactive HTML architecture report from a MuleSoft
  Anypoint Platform network-graph JSON export (the "ANA" export). Use this skill whenever
  the user wants to produce, regenerate, or update the MuleSoft architecture HTML document —
  including when they mention an Anypoint export, a network-graph JSON, an ANA report, an
  architecture report, API reuse metrics, or say something like "generate the MuleSoft
  report", "create the architecture HTML", "run the mule prompt", or "build the architecture
  doc from the JSON". Also trigger when the user pastes or references a path to a JSON file
  that looks like an Anypoint network-graph export. The output is always a single
  self-contained .html file — no external dependencies, all CSS/JS/SVGs inline.
user-invocable: true
---

# mulesoft-estate-report — MuleSoft Architecture HTML Report Generator

## How this skill works

Everything is deterministic and bundled. **Your job is to validate the input, run one
script, and report the results — never to hand-write the data transformation or the HTML.**

```
<BASE_DIR>/
├── SKILL.md                          ← this file
├── mulesoft_arch_template.html       ← report template; DATA is injected into it
├── prompt_mulesoft_architecture_html.md  ← reference: DATA contract, metric definitions, tabs
├── scripts/
│   ├── build_report.py               ← ENTRY POINT: export JSON → finished HTML
│   └── build_data.py                 ← export JSON → DATA object (called by build_report.py)
└── data/
    ├── ANA Industry Data Matrix - Golden Template.xlsx  ← peer benchmark source
    └── customer_ou_map.json          ← customer name → industry (OU) for the benchmark
```

`<BASE_DIR>` is the "Base directory for this skill" path shown above this section in your
context. All scripts locate the template and `data/` relative to themselves, so the skill
works from any folder.

> **Why scripts, not hand-authoring:** the transformation (clientGroup merge, backend
> consolidation, internal-API remapping, edge reconciliation, reuse metrics) is subtle, and
> hand-written versions have silently dropped edges before. `build_data.py` enforces an
> edge reconciliation invariant and aborts if any edge is lost. `build_report.py` does the
> template injection so the 100–350 KB HTML is never re-typed. Same input → byte-identical
> output.

---

## Prerequisites

- **Python 3.** On Windows use `python` (`python3` may be a Microsoft Store stub). On
  macOS/Linux use `python3`. Wherever this file says `python`, use whichever works.
- **pandas + openpyxl.** These are needed for the peer benchmark only. Check with
  `python -c "import pandas, openpyxl"`. If either is missing, tell the user and offer
  `python -m pip install pandas openpyxl`. Without them the report still builds, but
  `benchmarkAvg` is null and the Reuse tab falls back to a generic 38% "MuleSoft
  customer benchmark". **This produces a different report**, so don't let it happen silently.

---

## Execution steps

### 1. Get the input

The user provides a path to an Anypoint network-graph export, usually named
`<Org>-network_graphs-<dd_mm_yyyy_hh_mm_ss>.json`. If none is given, ask: "Which Anypoint
network-graph JSON file should I use?" Use the full export, **not** a `*_data.json` file;
those are previous outputs of this skill.

### 2. Validate the export (always, and especially for a new customer)

Quick checks, run with a short Python snippet. Don't print the whole file.

- Top-level keys are `masterOrg, orgs, envs, apps, sandbox, production`.
- `production.dependencies.nodes` / `.edges` are non-empty, and every edge's
  `sourceId`/`targetId` exists in `nodes`.
- `apps[]` is populated. If it's **empty** (seen with Runtime Fabric estates whose nodes have
  `deploymentTarget: "rtf"`), warn the user: the Overview will show every production Mule
  node as one running app in one environment, and the env chart and inventory will be empty.
- `masterOrg.masterOrgName` matches a key in `data/customer_ou_map.json`
  (case-insensitive substring). If not, see step 4.

### 3. Run the report builder

```bash
python "<BASE_DIR>/scripts/build_report.py" "<input.json>"
```

- Output: `{masterOrgName}_Mule_Architecture.html` (spaces → underscores), written **next to
  the input JSON**. Use `-o <folder>` to write elsewhere, and `--keep-data` to also save the
  DATA JSON for audit.
- Use real paths for input and output. Don't route files through `/tmp`; on Windows, Git
  Bash's `/tmp` and Python's `/tmp` are different folders.
- If it exits non-zero (`RECONCILIATION FAILED` or a build_data error), **stop and report**.
  Never ship a report with silently-lost edges.

### 4. Review the output and tell the user

`build_report.py` prints to stderr: the edge reconciliation, the benchmark line, and a
summary (apps, APIs by layer, unclassified count, backends, flows, reuse metrics). Check:

- **Reconciliation:** `accounted for` must equal `raw edges`.
- **Benchmark:** the line should read `N peers (OU+API band)`. If it says
  `OU set too small … using all industries`, or `NOT AVAILABLE`, the customer is missing from
  `customer_ou_map.json` or pandas is missing. Fix it and re-run. To add a customer, add
  `"<lowercase name fragment>": ["<OU category>"]` using an OU value that exists in the
  matrix's `OU` column, e.g. `"Technology, Media, Telecomm"`, `"Manufacturing, Auto, Energy"`
  or `"Consumer and Business Services"`. Confirm the category with the user.
- **Unclassified APIs:** a high count means the customer uses a naming convention the layer
  rules don't recognise (see `layer_of_name` in `build_data.py`). Raise it with the user;
  don't silently change the script.
- **Backends:** a large generic backend such as "Cloudhub API" usually means internal Mule
  calls aren't being remapped. Wrong or cryptic names can be fixed in `BRAND_MAP` /
  `PRODUCT_MAP`.

Then tell the user:
- the output file path, and that they can open it by double-clicking (Windows `start "" "<file>"`,
  macOS `open "<file>"`)
- the customer name and key KPIs: total/running apps, environments, APIs by layer,
  backends, flows, and production reuse rate vs the benchmark
- any warnings from step 2 or step 4

### Changing the script

If a fix to `build_data.py` is needed, explain the problem and the proposed change and get
the user's agreement first. After the change, re-run **every** export you have and diff the
DATA output against the previous run. Report exactly which numbers moved for which customer,
because fixes for one customer have changed others before.

---

## What the pipeline does (for explaining numbers)

Full definitions are in `prompt_mulesoft_architecture_html.md`. In brief:

- **Layers.** A Mule node's `layer.label` is used if present. Otherwise the layer comes from
  the name: `-eapi`/`exp-` → Experience; `-papi`/`prc-`/`-pro-` → Process; `-sapi`/`sys-` →
  System; anything else goes to `layerOther`.
- **Consumers.** All `clientGroup` nodes are merged into one "N Client Apps" node.
  `clientApps` lists only the **production** client-group names. The export mixes sandbox
  entries into `production.clientgroup`, and the production ones are in a nested list.
- **Backends.** `http`/`other`/`db`/`sfdc` nodes are consolidated to business-friendly names
  (brand → product → domain extraction → titleised label).
- **Internal Mule calls.** An `http` node whose hostname is a deployed Mule app (including
  CH2/RTF names with a `-xxxxxx` suffix) is remapped to that app and is never counted as a
  backend.
- **Flows.** Unique consolidated edges. `flowsRaw` is the raw edge count.
- **Running.** Statuses `RUNNING`, `STARTED` and `SCALING`. **Environments** = distinct env
  names that have apps deployed.
- **Reuse metrics** (production graph). Consumers are incoming edges per Mule API, with
  client groups expanded by `numberOfClientApplications`. Reuse rate =
  (consumers − APIs with consumers) ÷ consumers. Reuse index = consumers ÷ APIs with
  consumers. Reusability = APIs with 2+ consumers ÷ APIs with consumers.
- **Benchmark.** The mean of `% Reuse rate (over all APIs)` across peers in the matrix's
  `Data Tab`. Peers share the customer's OU(s) and have 0.35–2.5× its API count. With fewer
  than 5 peers it broadens to the whole OU, then to all rows.

---

## Critical constraints

- **Don't edit the template's design** (layout, CSS, branding, logo). Only DATA changes per customer.
- **Zero external dependencies.** The output must be a single offline-ready HTML file.
- **Don't hand-assemble the HTML or DATA.** Always use `build_report.py`.
- **Customer data is confidential.** Don't paste export contents or client IDs into
  external services.

---

## Sharing this skill

Copy the **entire** `mulesoft-estate-report/` folder, including `scripts/` (both files) and
`data/` (the matrix and the OU map), to `~/.claude/skills/mulesoft-estate-report/` on the
recipient's machine. Without `data/`, the benchmark silently falls back to the generic 38%.
No path editing is needed. The recipient also needs Python 3 with pandas and openpyxl.

The ANA Industry Data Matrix contains peer customer data, so only share it internally.
