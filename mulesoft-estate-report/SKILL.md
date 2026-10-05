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
> output, on any OS.

---

## Prerequisites

**Python 3.8 or newer, and nothing else.** The scripts use only the standard library (the
Industry Matrix .xlsx is read with `zipfile` + `xml`), so there's nothing to `pip install`.
They behave identically on Windows, macOS and Linux and write byte-identical output (UTF-8,
LF line endings).

**Finding Python is your job, not the user's.** Don't ask the user which OS they're on. Try
these in order and use the first that prints `Python 3.8` or newer:

1. `python3 --version`
2. `python --version`
3. `py -3 --version` (Windows launcher)

On Windows, `python3` can be a Microsoft Store shortcut that prints nothing or opens the
Store; if so, move on to the next one. Call the working command `PY` below. If none works,
tell the user Python 3 needs installing (from python.org, or via their OS package manager)
and stop.

---

## Execution steps

### 1. Get the input

The user provides a path to an Anypoint network-graph export, usually named
`<Org>-network_graphs-<dd_mm_yyyy_hh_mm_ss>.json`. If none is given, ask: "Which Anypoint
network-graph JSON file should I use?" Use the full export, **not** a `*_data.json` file;
those are previous outputs of this skill.

### 2. Build the report (validation is built in)

```
PY "<BASE_DIR>/scripts/build_report.py" "<input.json>"
```

Always quote both paths, because they often contain spaces. The command works the same in
bash, zsh and PowerShell.

- **It validates the export first.** It checks the export structure, that the graph has
  nodes, for edges pointing at missing nodes, for an empty `apps[]` (typical of Runtime
  Fabric estates), whether the customer is in `customer_ou_map.json`, and that the matrix
  is present. Problems print as `WARNING:` / `ERROR:` lines. To validate without building,
  add `--check`.
- **Output:** `{masterOrgName}_Mule_Architecture.html` (characters unsafe in filenames →
  `_`), written next to the input JSON. Options: `-o <folder>` writes elsewhere,
  `--keep-data` also saves the DATA JSON, and `--open` opens the report in the default
  browser on any OS.
- **Exit codes:** 0 = ok, 1 = build failed (e.g. `RECONCILIATION FAILED`), 2 = invalid input.
  On a non-zero exit, **stop and report**. Nothing is written, and you must never ship a
  report with silently-lost edges.

### 3. Review the output and tell the user

`build_report.py` prints to stderr: the input check, the edge reconciliation, the benchmark
line, and a summary (apps, APIs by layer, unclassified count, backends, flows, reuse
metrics, warnings). Check:

- **Reconciliation:** `accounted for` must equal `raw edges`.
- **Benchmark:** the line should read `N peers (OU+API band)`. If it says
  `OU set too small ... using all industries`, the customer is missing from
  `customer_ou_map.json`. If it says `NOT AVAILABLE`, the matrix is missing or unreadable.
  Fix it and re-run. To add a customer, add
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
- the output file path, and that they can open it by double-clicking. If they want it
  opened for them, re-run with `--open`, which works on any OS.
- the customer name and key KPIs: total/running apps, environments, APIs by layer,
  backends, flows, and production reuse rate vs the benchmark
- any warnings, in plain language

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
recipient's machine (`~` = the user's home folder on any OS). Without `data/`, the
benchmark falls back to the generic 38%, and `build_report.py` warns about it. No path
editing or package installs are needed; the recipient only needs Python 3.8+.

The ANA Industry Data Matrix contains peer customer data, so only share it internally.
