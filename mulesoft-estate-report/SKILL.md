---
name: mulesoft-estate-report
description: >
  Generate a polished, single-file interactive HTML architecture report from a MuleSoft
  Anypoint Platform network-graph JSON export. Use this skill whenever the user wants to
  produce, regenerate, or update the MuleSoft architecture HTML document — including when
  they mention an Anypoint export, a network-graph JSON, an architecture report, or say
  something like "generate the MuleSoft report", "create the architecture HTML", "run the
  mule prompt", or "build the architecture doc from the JSON". Also trigger when the user
  pastes or references a path to a JSON file that looks like an Anypoint network-graph
  export. The output is always a single self-contained .html file — no external
  dependencies, all CSS/JS/SVGs inline.
user-invocable: true
---

# mulesoft-estate-report — MuleSoft Architecture HTML Report Generator

## How this skill works

All CSS, icons, renderers, and scaffolding live in a pre-built template bundled with this
skill. The base directory for this skill is injected automatically — use it to resolve both
support files without any hardcoded paths:

```
<BASE_DIR>/mulesoft_arch_template.html
<BASE_DIR>/prompt_mulesoft_architecture_html.md
```

Where `<BASE_DIR>` is the "Base directory for this skill" path shown above this section
in your context.

**Your job each run is to run the bundled data builder, then inject its output into the
template — not to hand-write the transformation or the HTML.**

> **Why a bundled script (v3.0.0):** the data transformation — clientGroup merge, backend
> consolidation, and above all *edge remapping* — is subtle. Hand-authoring it per run
> previously produced a silent bug that dropped 100% of backend-bound edges (flows showed
> 260 instead of ~584). `scripts/build_data.py` does it once, correctly, and enforces an
> edge **reconciliation invariant** (`raw = kept + duplicates + self-loops + unresolved`)
> that aborts loudly if any edge is ever lost. Do not reimplement this by hand.

---

## Execution steps

1. **Read the JSON input** — the user will provide a path or paste the JSON. If not
   provided, ask: "Which Anypoint network-graph JSON file should I use?"

2. **Run the data builder** and capture the reconciliation report:

   ```bash
   python3 <BASE_DIR>/scripts/build_data.py <input.json> > /tmp/mule_data.json
   ```

   The script prints the edge reconciliation to stderr — **surface those numbers to the
   user** (raw edges, kept flows, duplicates collapsed, internal APIs remapped, backends).
   If the script exits non-zero (`RECONCILIATION FAILED`), stop and report it; do not ship
   a report with silently-lost edges.

3. **Inject and write** — read `<BASE_DIR>/mulesoft_arch_template.html`, replace the line
   `const DATA = /* DATA_PLACEHOLDER */ null;` with `const DATA = <contents of
   /tmp/mule_data.json>;`, and write the output file (Step 6–8 below). You do **not** need
   to read the prompt spec for a normal run — it is reference documentation for the DATA
   shape and the consolidation strategy the script implements.

The DATA shape the script emits is:

```js
const DATA = {
  meta: { customer, masterOrg, extractOn, orgs, generated },
  kpis: { totalApps, running, stopped, prod, sandbox, envs, uniqueApis, backends, expCount, procCount, sysCount, flows },
  envRows: [ { name, type, total, running, stopped } ],
  businessGroups: [ { name, total, running, prod, sandbox, experience, process, system, other } ],
  targets: [],
  layers: { experience: [], process: [], system: [] },
  nodes: [],
  edges: [ { source, target } ],
  backends: [],
  consumers: [],
  reuse: [],
  tagDist: [ [name, count] ],
  clientApps: [],
  inventory: []
};
// Node item shape: { key, label, kind, layer, tag, category, icon, in, out }
```

### What the script does (so you can explain it)

`scripts/build_data.py` implements the full v3.0.0 pipeline. You don't call these pieces
individually — this is documentation for when the user asks how a number was derived:

- **clientGroup merge** — Anypoint emits one `clientGroup` node per API in large tenants.
  All are merged into a single `consumer-merged` node labelled "N Client Apps"; their edges
  remap to it.
- **Backend consolidation (4-tier)** — each `http`/`other`/`db`/`sfdc` backend endpoint is
  named by: Tier 1 brand (Salesforce, AWS DynamoDB, Okta…), Tier 2 product/partner
  (FleetCor API, iConnectData, HotelbedS API…), Tier 3 domain extraction
  (`apiprd.allstaronline.co.uk` → "Allstaronline API"), else a titleized stem. Full strategy
  in `/Users/fernando.cedeno/Documents/claude/mule-general/BACKEND_CONSOLIDATION_STRATEGY.md`.
- **Internal Mule APIs are never backends** — an `http` node whose hostname stem matches a
  deployed Mule app (e.g. `cp-payments-sapi.…mule.fleetcor.com`) is remapped to that app's
  node and excluded from the backend list. This removes double-counting noise.
- **Edge remapping + reconciliation** — a single `{node_id → output_key}` map covers every
  node, so no edge is ever orphaned. `flows` = unique consolidated edges; `flowsRaw` keeps
  the raw count for audit. The script aborts if `kept + duplicates + self-loops + unresolved
  ≠ raw`.
- **Schema flexibility** — handles both the standard export (`production.dependencies`) and
  nodes/edges-only exports. When `apps[]` is absent, every Mule node counts as one running
  app so the Overview and the "0 stopped apps" message stay coherent.
```

4. **Read the template file** at `<BASE_DIR>/mulesoft_arch_template.html`.

5. **Replace the placeholder** — find the line:
   ```js
   const DATA = /* DATA_PLACEHOLDER */ null;
   ```
   and replace it with the fully-populated DATA object.

6. **Set the output filename** — `{CustomerName}_Mule_Architecture.html` where
   `{CustomerName}` = `masterOrg.masterOrgName`.

7. **Write the output file** next to the input JSON (or user-specified location).

8. **Tell the user:**
   - The output file path
   - How to open it (`open <filename>` or double-click)
   - Customer name + key KPIs (total apps, running, environments) for a quick sanity check

---

## Critical constraints

- **Do not rewrite the template.** Only inject DATA.
- **Zero external dependencies** — the template already satisfies this; don't add any.
- **Single file output** — the written HTML is complete and self-contained.
- **MuleSoft branding preserved** — the template handles this; do not modify logo or colors.

---

## Sharing this skill

To share with a colleague, copy the entire skill directory:

```
~/.claude/skills/mulesoft-estate-report/
  SKILL.md
  mulesoft_arch_template.html
  prompt_mulesoft_architecture_html.md
  scripts/build_data.py
```

They place it at `~/.claude/skills/mulesoft-estate-report/` on their machine.
No path editing required — all file references are resolved relative to the skill directory.
