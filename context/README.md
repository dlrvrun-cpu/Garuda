# Garuda Episode 2.1: context code

Two small scripts, plain Python 3, no libraries.

## Context prioritization

    python context_prioritization.py
    python context_prioritization.py my_items.txt 10000

Input: `context_items.txt`, one context item per line (name | priority | tokens | is_error | source | smaller version tokens).
Output: the triage trace per tier, the token totals, and the text the model receives.

## Semantic compaction

    python semantic_compaction.py
    python semantic_compaction.py my_conversation.txt

Input: `conversation.txt`, blocks of turns. Lines starting with RESULT:, DECISION: and OPEN: are kept in a summary. CLOSED: removes an open item. Everything else is dropped.
Output: the conversation before compaction, at level 2 (keep the last 2 blocks), and at level 3 (keep the last block).

The summary here is rule based, so it comes out much smaller (about 100 tokens) than an LLM-written summary would be. A real Garuda would ask the model to write the summary, using the same rule: keep results, decisions and what is still open.
