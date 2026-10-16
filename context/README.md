# Garuda's context code

Plain Python 3. The context scripts need no libraries; `review_agent.py` needs `anthropic`.

## Episode 2.1: one technique per script

### Context prioritization

    python context_prioritization.py
    python context_prioritization.py my_items.txt 10000

Input: `context_items.txt`, one context item per line (name | priority | tokens | is_error | source | smaller version tokens).
Output: the triage trace per tier, the token totals, and the text the model receives.

### Semantic compaction

    python semantic_compaction.py
    python semantic_compaction.py my_conversation.txt

Input: `conversation.txt`, blocks of turns. Lines starting with RESULT:, DECISION: and OPEN: are kept in a summary. CLOSED: removes an open item. Everything else is dropped.
Output: the conversation before compaction, at level 2 (keep the last 2 blocks), and at level 3 (keep the last block).

The summary here is rule based, so it comes out much smaller (about 100 tokens) than an LLM-written summary would be. A real Garuda would ask the model to write the summary, using the same rule: keep results, decisions and what is still open.

## All three together: the context engine

    python context_engine.py
    python context_engine.py sample_pr 10000
    python context_engine.py sample_pr 10000 --show-prompt
    python context_engine.py sample_pr 6000      # a smaller window: watch items become handles

`context_engine.py` reads a real PR folder instead of a list of made-up sizes:

| In `sample_pr/` | What it is |
|---|---|
| `pr.diff` | The change: SOQL and DML added inside the loop in `OpportunityService.closeLostOpportunities` |
| `pr.md` | PR title and description |
| `ci-test-run.log` | 400 tests, about 12,800 tokens. `bulkClose` fails with Too many SOQL queries: 101 |
| `review-history.txt` | Earlier review rounds on this PR |
| `repo/` | A small Salesforce DX project: classes, trigger, custom field, `REVIEW_RULES.md`, PMD rules, `.garuda/memory/` |

It runs in two rounds.

**Round 1, look (progressive discovery).** Start from the diff and follow one hop, no further:

1. The rules and the change (P0): system prompt, safety rules, `REVIEW_RULES.md`, PR description, the diff.
2. The full modified class (P1). The diff hides the sharing keyword, the recursion guard and the rest of the method.
3. The CI failure lines pulled out of the log (P1, error, so it goes first). The full log is P3.
4. The matching test class: `<Name>Test.cls`, `<Name>_Test.cls`, `Test<Name>.cls` (P1).
5. Blast radius: every call to the changed method, one line each (P1). The calling classes are P2.
6. Repo classes the change calls, and the custom fields it touches (P2).
7. `sfdx-project.json`, the PMD ruleset and Garuda's memory (dismissed findings P1, conventions P2).
8. Earlier review rounds (P2), with a compacted summary as the smaller version.

Classes nothing points to (`LeadService.cls`, `CaseRouter.cls`) are never read.

**Triage (context prioritization).** Same rules as Episode 2.1: fill P0, P1, P2 up to their caps, errors first, then smallest. If an item doesn't fit, try its smaller version (Apex signatures only, or the compacted history). If that doesn't fit either, it becomes a handle. P0 never gets dropped. The full version of anything shrunk stays listed as a handle: compact, but never delete.

**Round 2, ask (progressive discovery).** The model gets two tools, `read_context` and `search_context`. It can search the 12,800-token log for the failing lines (about 75 tokens), read a line range of a class that was shrunk to signatures, or pull in a class nobody discovered yet, like `OpportunityTrigger.trigger`. Fetches come out of a fetch budget (20% of the window); a request that is too big is refused with a hint to search instead.

Every decision lands in a `ContextTrace`: what was loaded, shrunk or demoted and why, tokens up front versus fetched, and the re-read ratio (how often the model asked for something it already had; high means triage loaded the wrong things).

## The agent

    pip install anthropic
    export ANTHROPIC_API_KEY=...
    python review_agent.py

`review_agent.py` builds the context with `ContextSession`, sends it to Claude with the two tools, answers the tool calls until the model is done, and prints the JSON review and the context trace.
