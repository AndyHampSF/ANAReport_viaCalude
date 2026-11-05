# Changes at a glance

Effects are shown on the same exports (TalkTalk 8 Oct 2026, JLR 28 Oct 2026), using your
v3.9.1 and the upgraded version.

## Part A: Data fixes (change the numbers)
| # | Change | Your v3.9.1 shows | After the fix | Recommend |
|---|---|---|---|---|
| A1 | Recognise `-eapi-`/`-papi-`/`-sapi-` mid-name, and `-pro-` as Process | **JLR: 0/3/0 layers, 0% reuse.** TalkTalk: 0 Process APIs | JLR: 4/5/10, **25.8% reuse**. TalkTalk: 10 Process | **Apply** |
| A2 | Strip the CH2/RTF hostname suffix when matching internal calls | Fake "Cloudhub API" backend; flows 141 (TalkTalk) / 80 (JLR) | Internal calls linked to the right app; flows 119 / 70 | **Apply** |
| A3 | OAuth client list: production apps only | JLR: 9 **sandbox** names, 0 production. TalkTalk: 25 sandbox names | JLR: its 3 production apps. TalkTalk: 91 production partners | **Apply** |
| A4 | Backend names | "Api API", "Staging API", "API Gateway", "Site API", "Microsoft API" | Arval (BNP Paribas), Fibre Gateway, Salesforce Experience Cloud, Microsoft Entra ID | **Apply** |
| A5 | Read exports as UTF-8 | Accented names garbled on Windows | Correct everywhere | **Apply** |
| A6 | Env detection prefers an explicit `prod` token | `network-test-pxc-prod` classed as Test | Production | Apply (affects exports without app data only) |

## Part B: Features
| # | Feature | Needs | Recommend |
|---|---|---|---|
| B1 | **Peer benchmark + Reuse Analysis tab**: reuse rate against comparable customers, maturity stage, by-layer and by-group breakdowns | Industry Matrix `.xlsx` | Apply if you have the matrix |
| B2 | Ignore struck-through rows in the matrix (invalid values such as `56.36` or `173%`) | B1 | Apply with B1 |
| B3 | **Integration Flows**: arrows, click to pin (blue = calls, amber = called by), walk the graph, zoom and pan, full-size canvas, **circular view**, readable labels, sensible name shortening | none | **Apply** |
| B4 | One-command build (`build_report.py`), with input checks; works identically on Windows, Mac and Linux, with nothing to install | none | **Apply** |
| B5 | Regression check tool: see exactly which numbers a change moves, for every customer | none | **Apply** |

## Already in your version (kept as-is)
Platform Adoption · Data confidence · Deployment Coverage · Business Groups · peer-review
metrics · Integration & Batch section · Business group / isolated inventory filters ·
`--customer` option.
