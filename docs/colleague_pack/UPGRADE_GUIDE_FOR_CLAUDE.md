# Upgrade guide for the mulesoft-estate-report skill (v3.9.1 fork)

**Audience: Claude Code**, running in the owner's copy of the `mulesoft-estate-report` skill
(fork version 3.9.1). A human will give you this file and ask you to work through it.

**Origin.** This guide was written by Andy Hampshire's team after comparing your fork
(v3.9.1, 28 Sep 2026) with their version of the same skill (v3.6.0, 5 Nov 2026). Both
started from the same original. The team found bugs in v3.9.1 that change the numbers
customers see, and features of theirs that v3.9.1 lacks. Your fork's own good features
(adoption, data confidence, deployment coverage, business groups, peer-review metrics,
the Integration & Batch section) are already in their version, so you keep all of them.

---

## How to run this guide (instructions for Claude)

1. **Back up first.** Copy the whole skill folder to a sibling folder named
   `mulesoft-estate-report.backup-<today's date>` before changing anything. Tell the user
   where the backup is.
2. **Take a baseline.** Ask the user for 1–3 customer exports (`*-network_graphs-*.json`).
   For each one, run the current `scripts/build_data.py` and save the output as
   `<customer>_before.json` (outside the skill folder). Every later check compares against
   these files.
3. **Work through the changes in order**, one at a time. For each change:
   - **Explain it** in 2–4 plain-English sentences: what's wrong or missing, what the
     user's reports show today, and what will change. Use the change's *Problem* and
     *Effect* text, and quote real numbers from their baseline exports where you can.
   - **Ask the user: apply, skip, or explain more.** Never apply a change without a yes.
     Stop and wait for the answer each time.
   - **If they say apply:** make the change as the *Fix* section describes. Adapt it to the
     code as you find it, but keep the behaviour exactly as described. Then run the
     change's *Verify* steps and report the result.
   - **If verification fails:** undo that change (restore the affected files from the
     backup), say what happened, and continue with the next change.
   - **If they say skip:** note it and move on. Changes marked **depends on** need the
     named earlier change; skip them too if that one was skipped, and say why.
4. **Update the skill's own docs.** After the last change, bring `SKILL.md` and
   `prompt_mulesoft_architecture_html.md` up to date so they describe the new behaviour:
   - `build_report.py` as the way to run the skill (if B4 was applied)
   - the `data/` folder (if B1 was applied)
   - click-to-pin instead of hover (if B3 was applied)
   - a version note

   Ask the user first.
5. **Finish with a summary table:** change, applied or skipped, the result of its check,
   and which numbers moved for each baseline customer. Remind the user that their
   backup folder exists.

**Ground rules:**
- Don't refactor beyond what a change needs.
- Keep the edge reconciliation invariant (`kept + duplicates + self-loops + unresolved =
  raw`) working after every change.
- Keep existing DATA fields unless a change says otherwise. If the template reads a field,
  the field must still exist.
- When in doubt, ask the user rather than guess.

Each change's **Verify** steps tell you what to check. "Re-run" means: run
`build_data.py` on the same exports again and compare with `<customer>_before.json`.

---

## Part A: Data fixes (these change the numbers in reports)

### A1. Layer classification: recognise `-eapi-` / `-papi-` / `-sapi-` in the middle of names (and `-pro-` as Process)
- **Problem:** `layer_of` / `layer_from_name` only match `-eapi`/`-papi`/`-sapi` at the
  **end** of a name, after stripping env and version suffixes, or `exp-`/`prc-`/`sys-`.
  Many estates put the layer token in the middle: JLR uses `eu-jlr-sapi-smart`,
  `eu-jlr-papi-finance` and `rotw-jlr-eapi-commerce-cloud`. Those fall into "other". TalkTalk
  names Process APIs `pro-whs-pro-…`, which isn't recognised either.
- **Effect seen:**
  - **JLR:** 16 of its 19 APIs are classed as "other", so Experience/Process/System shows
    0/3/0 instead of 4/5/10, and **reuse reads 0%** instead of about 26%. Platform
    Adoption and the peer-review metrics collapse with it.
  - **TalkTalk:** Process shows 0 instead of 10.
- **Fix:** classify a name, case-insensitive with the first match winning, as:
  - **experience:** ends `-eapi`, OR contains `-eapi-`, OR contains `exp-`
  - **process:** ends `-papi`, OR contains `-papi-`, OR contains `prc-`, OR contains `-pro-`
  - **system:** ends `-sapi`, OR contains `-sapi-`, OR contains `sys-`
  - otherwise **other**

  Apply these rules to the **raw lowercased name**, and **remove** the existing
  env/version-suffix strip (`_strip_layer_env_suffix`) from layer matching. The strip
  isn't needed: the "contains" rules already handle trailing environments. It's also
  harmful, because `mm-crm-salesforce-exp-prd-v1` strips to `mm-crm-salesforce-exp`, which
  no longer contains `exp-` and falls to "other". Use the same function on both paths, the
  graph nodes and `apps[]`.

  Example cases:

  | Name | Layer |
  |---|---|
  | `eu-jlr-sapi-smart` | system |
  | `rotw-jlr-eapi-commerce-cloud` | experience |
  | `pro-whs-pro-product-ordering-api-v1` | process |
  | `athena-ac-patient-in-consume-papi-prod` | process |
  | `vbc-snowflake-sapi-prod` | system |
  | `mm-crm-salesforce-exp-prd-v1` | experience |
  | `jlr-korea-prod` | other |
- **Verify:**
  - The table above gives exactly those results.
  - Re-run the baselines and report each customer's Experience/Process/System counts,
    before and after.
  - The reconciliation still closes.

### A2. Internal Mule calls: strip the CloudHub 2 / RTF hostname suffix
- **Problem:** CH2/RTF internal hostnames carry a 6-character suffix, for example
  `pro-whs-sys-dise-api-v1-97pqx7.internal-dxakq7.gbr-e1.cloudhub.io`. `strip_host` keeps
  `pro-whs-sys-dise-api-v1-97pqx7`, which matches no Mule app. So these internal calls are
  treated as an external backend.
- **Effect seen:**
  - A fake backend called **"Cloudhub API"** appears.
  - App-to-app links vanish from the graph, and flows are inflated: TalkTalk shows 141 flows
    instead of 119, and JLR 80 instead of 70.
  - The build log shows `internal http remapped: 0`.
- **Fix:** when matching an http node to a Mule app, also try the stem with a trailing
  `-[a-z0-9]{6}` removed (regex `-[a-z0-9]{6}$`). Check, in order: the stem, the raw label,
  then the stem without the suffix. If any equals a Mule app label, remap the node to that
  app.
- **Verify:**
  - Re-run the baselines. "Cloudhub API" is gone from the backends of any customer whose
    internal hostnames have the suffix.
  - `internal http remapped` is above 0 (TalkTalk: 23, JLR: 12).
  - The reconciliation still closes.

### A3. Client app names: production only
- **Problem:** the export's `production.clientgroup` list **mixes two things**:
  - top-level `{key, value}` entries whose `key` is a **sandbox** clientGroup node id
  - one nested **list** of `{key, value}` entries for the **production** clientGroup nodes

  The parser reads only the top-level dicts, and `normalise()` also adds
  `sandbox.clientgroup`. So the OAuth Client Governance list and the Consumption Governance
  card show **test/sandbox apps** and leave out the production ones.
- **Effect seen:**
  - **JLR:** 9 names, all sandbox (`ext-jlr-gtm-qa`, `-sit`, `-preprod`,
    `developer-test app-FR`, `…PenTest…`) and **none** of its 3 production apps.
  - **TalkTalk:** 26 names, 25 of them sandbox (`ETF1SIT`, `SIT appointments app`, …),
    instead of its 91 production partner apps.
- **Fix:** flatten `production.clientgroup`: for each element, take the element itself if
  it's a dict, or its items if it's a list. Keep only entries whose `key` is the id of a
  `clientGroup` node in the **production** dependency graph. Collect their
  `value[].name` and de-duplicate **by name**. **Remove** the code in `normalise()` that
  merges `sandbox.clientgroup` into the list: sandbox client apps must not appear.
- **Verify:**
  - Re-run. Every name in `clientApps` comes from a client group whose key is a production
    clientGroup node id; check this programmatically.
  - For JLR-like data the names should look like production apps (e.g. `…-prod`).
- **Note for the user:** the export lists at most **50** names per API, while
  `numberOfClientApplications` on the node holds the true count. So the name list can be
  shorter than the client-app total (TalkTalk: 91 names against 426 apps). Counts must use
  `numberOfClientApplications`.

### A4. Backend naming: brand-TLD and generic-keyword fixes
- **Problem:** domain extraction mislabels a few endpoints:

  | Endpoint | Current name | Why |
  |---|---|---|
  | `arval.api.bnpparibas` | "Api API" | `.bnpparibas` is a brand top-level domain |
  | `arval.api.staging.bnpparibas` | "Staging API" | same |
  | `prod.fibregateway.com` | "API Gateway" | matches the generic `gateway` keyword |
  | `talktalkwholesale.my.site.com` | "Site API" | it's a Salesforce Experience Cloud site |
  | `login.microsoft.com` | "Microsoft API" | it's Microsoft Entra ID |
- **Fix:** add these as the **first** entries of `BRAND_MAP`, so they're checked before the
  generic `gateway` / `salesforce` keywords:
  - `('fibregateway', 'Fibre Gateway')`
  - `('my.site.com', 'Salesforce Experience Cloud')`
  - `('login.microsoft', 'Microsoft Entra ID')`

  Then add `('arval.api.', 'Arval (BNP Paribas)')` to `PRODUCT_MAP`. Use exactly
  `arval.api.`: a broader `arval` would mislabel internal Mule hostnames such as
  `eu-jlr-sapi-finance-arval-…`, and `bnpparibas` would wrongly catch
  `bnpparibas-pf.com`, which is a different service.
- **Verify:** `consolidate_backend()` returns:

  | Input | Result |
  |---|---|
  | `arval.api.bnpparibas` | Arval (BNP Paribas) |
  | `arval.api.staging.bnpparibas` | Arval (BNP Paribas) |
  | `api-ce.bnpparibas-pf.com` | Bnpparibas Pf API (unchanged) |
  | `prod.fibregateway.com` | Fibre Gateway |
  | `talktalkwholesale.my.site.com` | Salesforce Experience Cloud |
  | `login.microsoft.com` | Microsoft Entra ID |

### A5. Read exports as UTF-8
- **Problem:** `open(path)` uses the OS default encoding (cp1252 on Windows), so an export
  with accented names (e.g. "Nestlé") is misread on Windows.
- **Fix:** `open(path, encoding='utf-8')`. Do the same for every file the scripts read or
  write. Also make console output safe: either keep console messages plain ASCII (replace
  box-drawing characters like `─` with `-`), or call
  `sys.stdout.reconfigure(encoding='utf-8')`. Do the same for `sys.stderr` at start-up.
- **Verify:** re-run the baselines; the output is unchanged for ASCII exports.

### A6. Environment detection: an explicit production token wins
- **Applies to:** the topology-only path (exports without `apps[]`), in `env_of()`.
- **Problem:** when a name contains several environment tokens and none comes before a
  version segment, the first match wins. So `network-test-pxc-prod` is classed as **Test**
  when it's a production app (`test` is part of the app's name).
- **Fix:** in the tie-break, prefer, in order: a match just before a `vN` segment, then a
  token in `{prod, prd, production}`, then the first match.
- **Verify:** this code only runs for exports **without** `apps[]`. If `env_of` is nested
  inside `main()`, test it directly, or build a small synthetic export with `"apps": []` and
  a few Mule nodes using the names below. Standard exports must be byte-identical before
  and after.

  | Name | Result |
  |---|---|
  | `network-test-pxc-prod` | Production |
  | `mm-dev-portal-exp-prd-v1` | Production |
  | `dev-whs-exp-foo` | Development |
  | `test-object-store1` | Test |

### A7. Unidentified inbound traffic is a consumer, not a backend
- **Problem:** every export has one `http` node that is Visualizer's catch-all for callers
  without a recognised client ID. It's normally labelled "External Traffic", but it can be
  renamed: TalkTalk calls it "Partner". The script treats it as a backend. It ends up in
  the Backend column with arrows pointing back to the APIs, is counted in the backend total,
  and is listed on the Backend tab with 0 connections.
- **How to recognise it:** `type == 'http'`, **no `host`**, `clientId` is `OTHER`, and **no
  inbound edges**.
- **Fix:** before the backend loop, turn each matching node into a consumer:
  `{kind:'consumer', layer:'consumer', icon:'web'}`, keeping its label. Add it to
  `consumers`, map its id to it, and skip it in the backend loop.
- **Effect:** the backend count drops by 1 for each customer (TalkTalk 23→22, JLR 23→22).
  Flows and reuse figures are **unchanged**, because its edges were already counted as
  consumers.
- **Verify:** re-run the baselines.
  - Backends drop by exactly 1 where the node exists.
  - `kpis.flows` and every reuse field are identical to before.
  - `consumers` now includes the node.
  - In the report it appears in the consumer column, not under Backend.

---

## Part B: Features to add

### B1. Peer benchmark and the Reuse Analysis tab
- **What:** a seventh tab, **Reuse Analysis**, and a `reuseAnalysis` DATA field. It holds
  production and sandbox reuse stats, a per-business-group breakdown, and a **peer
  benchmark**: the average reuse rate of comparable customers from MuleSoft's *ANA Industry
  Data Matrix*. The tab shows:
  - headline figures: reuse rate, reusability, reuse index, consumers, APIs, maturity stage
  - a consumer-distribution donut and reuse by layer
  - a metric breakdown table
  - a benchmark bar against the peer average, on bands Incubating < 20%, Developing < 40%,
    Industrialised < 50%, Mature API-led
  - reuse by business group (when there are 2+) and a list of the most consumed APIs
- **Needs from the user:** the Industry Matrix `.xlsx`, saved as
  `data/ANA Industry Data Matrix - Golden Template.xlsx` (sheet `Data Tab`, with columns
  `OU`, `# APIs Total` and `% Reuse rate (over all APIs)`). Plus a `data/customer_ou_map.json`
  mapping a lowercase customer-name fragment to a list of OU values, e.g.
  `{"talktalk": ["Technology, Media, Telecomm"]}`. If they don't have the matrix, **skip
  B1 and B2**. The template then falls back to a generic 38%, so explain that to them.
- **Exact method.** Work on the **raw** `production.dependencies` graph, before any backend
  consolidation, remapping or de-duplication. Use these definitions, so the results match
  the original method:
  - **APIs** = every node with `type == 'mule'`, in every layer, "other" included.
  - **Consumers of an API** = every edge whose `targetId` is that API. An edge whose
    source is a `clientGroup` node counts as that node's `numberOfClientApplications`
    (or 1 if missing); any other edge counts 1. Don't collapse duplicate edges, and don't
    remap internal-http nodes for this calculation.
- **Reuse definitions** (production graph; *consumers* as above):
  - reuse rate = (consumers − APIs with consumers) ÷ consumers
  - reuse index = consumers ÷ APIs with consumers
  - reusability = APIs with 2+ consumers ÷ APIs with consumers

  These match the original spreadsheet ANA method. They aren't the same as the fork's
  `reuseMetrics` (peer-review framing); keep both and label them clearly. Compute the same
  for `sandbox.dependencies` (shown as `sandbox`), and per business group, using
  `organizationId` on the Mule nodes and the names from `orgs[]`.
- **Expected results** (use them to check your implementation):

  | Export | APIs | Consumers | Reuse rate | Reusability | Reuse index |
  |---|---|---|---|---|---|
  | TalkTalk, 8 Oct 2026 | 48 | 470 | **0.9149** | 0.4750 | 11.75 |
  | JLR, 28 Oct 2026 | 34 | 31 | **0.2581** | 0.1739 | 1.3478 |
- **DATA shape** (all rates are fractions 0–1, not percentages):

  ```js
  reuseAnalysis: {
    production: { apisTotal, consumedMore, consumedOnce, consumedNone, consumers, reuseInstances,
                  reuseRate, reuseIndexApis, reuseIndexAll, reusability,
                  perApp:[{name, consumers, layer}],          // consumers > 0, sorted desc
                  byLayer:{ experience|process|system|other: {total, more, once, none, reuseRate} } },
    sandbox: <same shape> | null,
    benchmarkAvg: number | null,                            // fraction, e.g. 0.5808
    byBG: [{ bg, title, apisTotal, consumedMore, consumedOnce, consumedNone, consumers,
             reuseInstances, reuseRate, reusability, perApp }]
  }
  ```

  Here `reuseIndexAll` = consumers ÷ apisTotal, and byLayer's `reuseRate` = more ÷ (more +
  once).
- **The tab:** v3.9.1 has no Reuse Analysis tab, so you'll build it. Lay it out as follows;
  exact styling is up to you:
  - six headline tiles
  - a donut (2+ consumers / 1 consumer / none)
  - reuse by layer
  - a metric table
  - a benchmark bar against maturity bands, with a **fallback to 0.38 labelled
    "MuleSoft customer benchmark"** when `benchmarkAvg` is null
  - a by-business-group list, only when there are 2+ groups
  - a ranked list of the most consumed APIs
- **OU lookup:** in `customer_ou_map.json`, skip keys starting with `_` (e.g. `_comment`).
  A key matches when it's a case-insensitive substring of the customer name, or the other
  way round. Use the first match; if nothing matches, use all rows.
- **Peer set:**
  1. Same OU and an API count of 0.35–2.5× the customer's production API count (`apisTotal`
     above).
  2. If that gives fewer than 5 peers, the whole OU.
  3. If still fewer than 5, all rows.

  The benchmark is the mean reuse rate of the set.
- **Implementation:**
  - Read the `.xlsx` with the **standard library only** (`zipfile` + `xml.etree`): no
    pandas, so it runs anywhere.
  - Take formula cells' cached values.
  - Treat non-numeric rate cells as missing.
  - Sum the mean in numpy's **pairwise** order, so 4-decimal rounding matches pandas
    exactly. A plain `sum()` gave a different last digit in about 0.5% of cases.
- **Verify:**
  - The build log prints a line like `benchmark: N peers (OU+API band) -> avg …`.
  - The Reuse Analysis tab renders with no console errors.
  - If pandas is available, cross-check that the reader returns the same usable rows as
    `pandas.read_excel` with `to_numeric(errors='coerce')`. pandas may be in the user's
    site-packages, so don't run Python with `-I`. pandas also drops trailing empty rows that
    a raw XML reader returns, so compare only rows with data.

### B2. Ignore struck-through rows in the Industry Matrix
- **Depends on:** B1.
- **What:** the matrix's owners mark values that shouldn't be used with **strikethrough**.
  Examples include `56.36` with no % sign (read as 5,636%) and `173.00%`. Skip any row whose
  `OU`, `# APIs Total` or reuse-rate cell is struck through.
- **How:** in `xl/styles.xml`, find the fonts that have a `<strike>` element (with no
  `val="0"`). Find the `cellXfs` styles that use those fonts. A cell is struck if its `s`
  attribute is one of those styles, or if it's a shared string with a struck rich-text run.
- **Definitions:**
  - A row is **usable** when its API count is a number above 0 and its reuse rate is
    numeric.
  - Count a row as struck only if it's usable and one of its three cells is struck.
  - Strikethrough in other columns doesn't matter.
- **Effect:** benchmarks typically rise 4–13 points. The exact counts depend on the copy of
  the matrix: Andy's 27 Oct copy gives 175 of 334 struck, leaving 159. A later download of
  the Sheet may differ slightly (one test copy gave 177 of 338). That's expected, so report
  the counts you get.
- **Verify:**
  - The log reports the number of struck rows ignored.
  - No usable peer row has a reuse rate above 100%.

### B3. Integration Flows: a much better graph
- **What:** improvements to the Flows tab:
  - **Arrowheads** on every edge, pointing from the caller to the callee. Backward and
    same-column edges are routed so the arrow stays visible.
  - **Click to pin** replaces hover. Clicking a tile draws what it **calls in blue**
    (`#1E64B0`) and what **calls it in amber** (`#C77700`); both pass a colour-blind check.
    Clicking a highlighted neighbour moves the focus there, to walk the graph. Click again,
    click empty space, or press **Esc** to clear. Hover only shows a tooltip.
  - **Zoom:** −/+, **Fit**, **100%**, and Ctrl/Cmd + wheel, from 30% to 250%. Zoom keeps the
    point under the cursor in place. **Drag the background to pan**; a drag doesn't clear
    the selection. The canvas fills the window (height `max(560px, 100vh − 200px)`), and the
    Flows tab uses the full page width.
  - **Circular view** (hierarchical edge bundling), with a Columns / Circular toggle:
    - Nodes sit on a ring, grouped into layer arcs.
    - Edges are routed through each layer's hub point and bundled (β = 0.85).
    - Labels are 14px semibold, outside the ring, sized to the longest name.
    - A prefix shared by most Mule apps (e.g. `pro-whs-`) is dropped, with a note saying so.
    - Every node has an invisible click area covering the dot and its label.
    - The selection is kept when switching views.
  - **Shorten names only when it's worth it:** an ellipsis must save at least **6**
    characters, otherwise show the full name. In the circular view, shorten in the middle so
    `-v1`/`-v2` stays visible.
- **How:** this is template-only, with no DATA change. Implement the behaviour above; the
  exact code doesn't need to match.
  - **Edge routing:**
    - left-to-right edges go from the source's right edge to the target's left edge
    - backward edges leave from the source's left edge and arrive at the target's right edge
    - same-column edges loop out to the right
  - **Shared prefix:** the first two hyphen tokens, when 60% or more of the Mule apps (and
    at least 5) share them.
  - **Description text:** update the Flows tab's description so it no longer says "hover".
- **Verify:** in a browser, or headless Chrome/Edge with simulated clicks. Testing tips:
  - In headless mode, `requestAnimationFrame` may not fire under `--virtual-time-budget`,
    so call `buildGraph()` directly before testing.
  - On Windows, pass `--screenshot`, `--print-to-pdf` and `--user-data-dir` as
    Windows-style paths, or nothing is written.

  Check that:
  - Every node's **name** selects that node, at both Fit and 100% zoom.
  - Esc clears the selection.
  - The selection survives a filter change and a view toggle.
  - No tab shows a console error.

### B4. One-command, platform-independent build
- **What:** `scripts/build_report.py <export.json>`, a single command that:
  1. **validates** the export: its structure, edges pointing at missing nodes, an empty
     `apps[]` (typical of Runtime Fabric), whether the customer is in the OU map, whether the
     matrix is present. Exit code 2 means invalid input; `--check` validates only.
  2. runs `build_data.py`. Exit code 1 means a build failure, and nothing is written.
  3. injects DATA into the template.
  4. writes `{Customer}_Mule_Architecture.html` with a filename that's safe on every OS.
  5. prints a summary of the key numbers.

  Options: `-o DIR`, `--keep-data`, `--open`, `--customer NAME`. `build_report.py` passes
  `--customer` to `build_data.py` as `--customer=NAME`. By default the output goes next to
  the input export. On a failure, nothing at all is written, including the `--keep-data`
  file.
- **Why:** it replaces hand-assembling the HTML, which risks a truncated file, and makes
  every run reproducible.
- **Platform rules:**
  - standard library only (no pip installs)
  - read and write files as UTF-8 with LF line endings (`newline='\n'`)
  - plain-ASCII console messages
  - add `.gitattributes` with `* text=auto eol=lf` if the skill lives in git

  The same input then gives byte-identical HTML on Windows, macOS and Linux.
- **Verify:** build the same export twice; the HTML files must be byte-identical and
  contain no CR characters. If you can, also compare a build from a second OS; a single
  machine can't check this, so just note it.

### B5. Regression check tool (strongly recommended)
- **What:** `tools/regression_check.py` with two commands:
  - `snapshot <label>` runs `build_data.py` on every export in the **current folder** (or
    `--exports DIR`) and saves the outputs under `_regress/<label>/` in the current folder.
    Keep `_regress/` out of version control, because it contains customer data.
  - `compare <a> <b>` reports, for each customer, either `identical` or exactly which DATA
    keys and KPIs changed.
- **Why:** fixes for one customer have changed others before; A2, for example, changed JLR
  and Informa. Run it before and after every script change.
- **Verify:** take a snapshot twice with no changes in between; the compare shows
  `identical` for every export.

---

## Learnings worth keeping in the skill's notes
- **The export, and what to watch for:**
  - `production.clientgroup` holds sandbox entries as top-level dicts and production
    entries as a nested list (A3).
  - The named client list is capped at **50 per API**; `numberOfClientApplications` is the
    true count. The old spreadsheet ANA process counted names, so it under-counts reuse
    (TalkTalk: 365 against 430 consumers).
  - **Empty `apps[]`** (Runtime Fabric): there's no status or inventory. Ask for a
    re-export that includes it.
  - **Hybrid estates** (`target: SERVER`): the dependency graph is empty unless the
    **Anypoint Monitoring agent** is installed on the customer's servers (seen with British
    Sugar).
  - Same-named environments exist in some business groups (two "Dev"), so key app
    comparisons on `envId`.
  - Apps in deleted environments are missing from the export entirely.
  - Two exports can come from the same session, one with `apps[]` and one without; use the
    larger one.
- **The Industry Matrix:** keep a local `.xlsx` copy of the master Google Sheet. A Google
  API or CSV export loses the strikethrough formatting. Refresh it by downloading `.xlsx`
  from the Sheet.
- **Verify, don't assume:** after any script change, re-run every export and report exactly
  which numbers moved for which customer. Click-test the Flows tab in a browser after any
  template change.
- **Fixed recommendation text** on the Insights tab (e.g. "All apps are at 0.1 vCore
  replicas") isn't calculated from data. Sense-check it before presenting.
