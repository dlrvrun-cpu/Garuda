# Garuda v2: Perception

> Adding context vs. removing noise is a false tradeoff. The real decision is **what form**
> each piece takes: full text, a summary, signatures, a one-line handle, or nothing at all.

v1 handed the model the raw diff. That works for a 9-line diff and falls apart on a real
Salesforce PR, where a 3-line Apex fix arrives with a 4,000-line profile and a regenerated
flow. This package decides what the reviewer sees, and records why.

```
diff + repo ──▶ gather() ──▶ triage() ──▶ render() ──▶ system + user message
                   │             │                         │
                   │             └─▶ trace: kept / compressed / demoted / blocked
                   └─▶ NEVER tier: secrets, symlinks, binaries stop here
```

## The tiers

| Tier | Budget | What goes here for a Salesforce PR | Form |
|---|---|---|---|
| **P0 critical** | 10% | System prompt, safety rules, `REVIEW_RULES.md`, PR title/description/acceptance criteria, diff hunks of changed code, notes for added and deleted files | Full. If it doesn't fit, `BudgetError`. Never dropped silently. |
| **P1 important** | 30% | Changed Apex/trigger/LWC in full, their test classes, **CI failures** (packed first), blast radius (unchanged code calling what changed), dismissed findings for touched files | Full → signatures → handle |
| **P2 supporting** | 15% | Flow summaries, permission-change summaries, FLS facts for new fields, signatures of classes the change calls, conventions, `sfdx-project.json` | Already compressed |
| **P3 deferrable** | 0% | Full profile/flow XML, raw XML diffs, layouts, anything demoted | ~20-token handle: name, size, tool to fetch it |
| **NEVER** | — | `*.key`, `.env`, symlinks leaving the repo, binaries, static resources, CSV data | Not loaded. Not even the diff hunk. |
| **Reserve** | 45% | Nothing. Room to think, call tools, and write the review. | |

Two rules make the tiers work:

1. **Per-tier caps, not one shared pool.** Otherwise P1 eats the reasoning reserve.
2. **Demote, don't drop.** Anything that doesn't fit becomes a handle, so the model still
   knows it exists and can ask for it. Nothing vanishes without a line in the trace.

## In Apex terms

| Perception | Apex analogy |
|---|---|
| Context window | Heap limit for the transaction |
| P0 | `Trigger.new`: the records being changed. Never skipped. |
| Deepen (classes the change calls) | Querying parent records through lookups |
| Blast radius (who calls the change) | "Where is this used?" in Setup |
| Summaries / signatures | `AggregateResult` rollups instead of detail rows |
| P3 handles | Record Ids you can re-query later instead of holding the record |
| NEVER tier | A `without sharing` boundary you refuse to cross on untrusted input |
| `PerceptionTrace` | Logging `Limits.*` usage so you can debug why a run behaved as it did |

## PR #482: the worked example

`examples/pr482/` is a small SFDX repo plus the diff of a PR that replaces a flat discount
with a tier-based `DiscountService`. Five problems are planted in it:

1. SOQL inside a loop in `DiscountService.recalc` (and CI already failed on it)
2. `Discount_Percent__c` granted to the Admin profile but not the `Sales_User` permission set
3. An after-save flow overwrites the discount to 0 on Closed Won
4. `LegacyDiscountCalc` is deleted, but `QuoteController` (unchanged) still calls it
5. A developer accidentally committed `config/server.key`

```
$ python perceive.py

Tier                Cap     Used  Items
P0 critical      20,000      734     10
P1 important     60,000      878      8
P2 supporting    30,000      486      8
P3 handles            -      175      6
Reserve         197,727   (99% of window, for reasoning)

Naive load (every touched file in full): 33,148 tokens
Triaged load:                            2,273 tokens   (selectivity 0.069)

Compressed (kept the signal, not the bytes):
  permission change: .../Admin.profile-meta.xml: 17,914 -> 44 tokens
  flow summary: .../Opp_Approval.flow-meta.xml: 12,575 -> 76 tokens
  ...
Blocked (NEVER tier, not even the diff hunk):
  config/server.key: secret file (*.key)
```

About 7% of the naive token cost, and all four review findings are still visible to the
model; the fifth (the key) is withheld on purpose. `tests/test_perception.py` asserts each
one, so a change that makes perception "cheaper" but blinder fails the build.

Squeeze the budget to watch the fallbacks work:

```
$ python perceive.py --shares 0.10,0.02,0.01 --window 20000
Compressed:   DiscountService.cls: 144 -> 40 tokens        (signatures)
Demoted:      OpportunityTriggerHandler.cls: P1 budget full (230 > 37 left)
```

## Files

| File | Job |
|---|---|
| `items.py` | `Priority`, `ContextItem` (with `fallback` and `source_tokens`), `as_handle()` |
| `diff.py` | Unified diff → per-file `FileChange` (added/modified/deleted, line numbers) |
| `safety.py` | The NEVER tier: block list, symlink and traversal checks, binary detection |
| `salesforce.py` | File classification, flow and permission summaries, Apex references, signatures |
| `gather.py` | Forage (diff) → Focus (changed code, tests, CI) → Deepen (callees, callers, FLS) |
| `triage.py` | Per-tier caps, errors first, smallest first, fallback, demote |
| `render.py` | Reading order, `<context>` boxes, escaping, P3 handle list |
| `trace.py` | `PerceptionTrace`: what was kept, compressed, demoted, blocked, and selectivity |

Everything is standard library only, so it runs without an API key.

## Known limits (next episodes)

- Token counts are `chars // 4`. Swap in a real tokenizer when budgets get tight.
- Blast radius is a text search, so it can over-match names inside comments.
- Flow summaries cover record writes and calls, not decision logic.
- Perception doesn't verify org facts (row counts, indexes). That needs a Salesforce MCP tool,
  which belongs in the agent loop, not here.
