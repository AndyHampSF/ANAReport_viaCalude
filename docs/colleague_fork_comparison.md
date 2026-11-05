# Comparison with a colleague's fork (v3.9.1, 28 Sep 2026)

Compared on 5 Nov 2026 by building TalkTalk (8 Oct) and JLR (28 Oct) with both versions,
in an isolated folder (`ANA_Compare_v3.9.1/`, outside this repo).

**Shared origin.** Their `SKILL.md` and prompt doc are identical to this repo's first
commit (`51e952e`). After that the two diverged, and neither has the other's changes.

## Adopted from the fork into this repo (v3.6.0)
- Business Groups cards
- Data confidence rating
- Platform Adoption card
- Deployment Coverage card
- Peer-review metrics card
- Data-driven recommendations
- Integration & Batch Applications section, with call badges
- Inventory: business group column, isolated pill, filters for both
- Overview deployment-coverage note
- Env chart and inventory for topology-only exports (with the `prod` token tie-break added)
- `--customer` option

## Not adopted (the fork's version is wrong or redundant)
| Fork behaviour | Effect | This repo |
|---|---|---|
| Layer match only at the end of a name (after an env-suffix strip) | **JLR 0/3/0 layers, 0% reuse** | `-eapi-`/`-papi-`/`-sapi-` matched anywhere, plus `-pro-`: JLR 4/5/10, 25.8% |
| No CH2/RTF hostname-suffix strip | Fake "Cloudhub API" backend; flows +22 (TalkTalk), +10 (JLR) | Suffix stripped; internal calls remapped |
| Client names read from the top-level (sandbox) clientgroup entries, plus `sandbox.clientgroup` | OAuth list shows **test apps**: JLR 9 sandbox and 0 production; TalkTalk 25 sandbox | Production entries only: JLR 3, TalkTalk 91 |
| No brand-TLD or keyword overrides | "Api API", "Staging API", "API Gateway", "Site API", "Microsoft API" | Correct names |
| Env-suffix strip before layer matching | No effect once the layer rules above are in place (0 of 1,224 names change) | Not needed |
| No benchmark, no Reuse Analysis tab, a basic flows graph, no build/validation wrapper | — | All present |

The upgrade pack for the colleague is in `docs/colleague_pack/`.
