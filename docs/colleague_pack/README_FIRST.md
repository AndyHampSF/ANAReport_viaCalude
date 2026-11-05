# Upgrading your mulesoft-estate-report skill (v3.9.1): read me first

Hi. This pack updates your fork of the ANA architecture report skill. It fixes bugs that
change the numbers customers see, and adds features from Andy Hampshire's version. Your
Claude does the work. It explains each change and **asks you before applying it**, so
you're always in control.

**Takes about 20–40 minutes. You'll need Claude Code and 1–3 customer exports to test with.**

## What's in the pack
| File | What it is |
|---|---|
| `README_FIRST.md` | This file: what to do |
| `UPGRADE_GUIDE_FOR_CLAUDE.md` | The instructions your Claude follows. You don't need to read it, but you can |
| `CHANGES_AT_A_GLANCE.md` | A one-page summary of every change, to help you decide |
| `examples/` | Before/after example reports for TalkTalk and JLR. Open them in a browser to compare |

## Why upgrade? The short version
With v3.9.1, **JLR's report shows 0% API reuse**. Fixed, it shows **25.8%**. The cause is
that v3.9.1 doesn't recognise layer names like `eu-jlr-sapi-smart`, so 16 of JLR's 19 APIs
drop to "other". Other issues: a fake "Cloudhub API" backend and inflated flow counts; the
OAuth client list showing **test/sandbox apps instead of production**; and a few mislabelled
backends ("Api API", "Site API"). The upgrade also adds a peer **benchmark** and **Reuse
Analysis** tab, plus a much better Integration Flows graph: arrows, click-to-explore, zoom,
and a circular view.

All your fork's own features (adoption, data confidence, deployment coverage, business
groups, peer-review metrics, Integration & Batch) are kept.

## Tested
The guide was test-run end to end on a copy of v3.9.1 by a separate Claude Code session,
following it exactly as your Claude will. All 11 changes applied and every check passed.
The upgraded copy then produced **exactly the same numbers** as Andy's version for TalkTalk
and JLR: reuse 91.5% and 25.8%, flows 119 and 70, client apps 91 and 3, benchmarks 58.1% and
46.9%. The guide was refined afterwards using that run's notes.

## Before you start
1. **Find your skill folder.** It's the folder containing `SKILL.md`, `scripts/build_data.py`
   and `mulesoft_arch_template.html`, usually `~/.claude/skills/mulesoft-estate-report/`.
   (`~` is your home folder: `C:\Users\<you>` on Windows, `/Users/<you>` on a Mac.)
2. **Have 1–3 customer exports ready** (`*-network_graphs-*.json`) to test against. Ideally
   include one with mid-name layer tokens (like JLR), which shows the biggest difference.
3. **Optional, for the benchmark (change B1):** the *ANA Industry Data Matrix* spreadsheet as
   an `.xlsx`. Download it from the master Google Sheet with **File → Download → Microsoft
   Excel (.xlsx)**. Without it, everything else still works; just skip B1 and B2 when asked.
4. **Python 3.8+** must be installed. Nothing else is needed: no pip installs.

## Run it (step by step)
1. **Open Claude Code in your skill folder.** In a terminal, run
   `cd ~/.claude/skills/mulesoft-estate-report` and then `claude`. Or, if Claude Code is
   already open, use `/cd <path to the skill folder>`.
2. **Copy the pack into that folder,** or anywhere you like, and note the path.
3. **Paste this prompt into Claude Code** (adjust the paths):

   > Please read `<path>/UPGRADE_GUIDE_FOR_CLAUDE.md` and follow its instructions to upgrade this skill. Back up the skill folder first. My test exports are: `<path to export 1>`, `<path to export 2>`. *(Optional:)* The Industry Matrix is at `<path to .xlsx>`. Go through the changes one at a time, explain each, and ask me before applying anything.

4. **For each change, Claude will explain it and ask:** *apply, skip, or explain more?*
   - Not sure? Say **"explain more"**, or open the matching example report in `examples/`.
   - Recommended answer: **apply** for everything in Part A (data fixes) and B3 (graph). B1 and B2 need
     the matrix file. B4 and B5 are strongly recommended.
5. **After each change, Claude checks it** and tells you the result. If a check fails, it
   undoes that change automatically and moves on.
6. **At the end, Claude gives you a summary table:** what was applied, what was skipped, and
   which numbers moved for each test customer.

## Afterwards
- **Build a report:** `python3 scripts/build_report.py "<export>.json"`, or just ask
  Claude to "generate the MuleSoft report for <export>". On Windows, use `python` if
  `python3` doesn't work.
- **Compare** the new report with an old one for the same customer. The numbers should
  match the "after" example in `examples/`, if you used the same export.
- **If anything looks wrong,** your backup is in `mulesoft-estate-report.backup-<date>`.
  Ask Claude to restore it.

## Questions
Contact Andy Hampshire. If a change behaves differently on your exports, send the summary
table from step 6.
