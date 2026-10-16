# garuda/perception — Garuda v2: deciding what the reviewer sees
#
#   gather()  -> every candidate item, already in its best form (full / summary / handle)
#   triage()  -> fit them into tiered budgets, leave a reasoning reserve
#   render()  -> the system prompt + user message the model actually reads
#   trace     -> what was kept, compressed, demoted and blocked, and why
from __future__ import annotations

from pathlib import Path

from .gather import Gathered, gather
from .items import ContextItem, Priority
from .render import render
from .trace import PerceptionTrace, build_trace
from .triage import BudgetError, TriageResult, triage


def build_context(diff: str, repo_root: str | Path, *, window: int = 200_000,
                  pr: dict | None = None, evidence: list[tuple[str, str]] | None = None,
                  system_prompt: str | None = None,
                  shares: dict[Priority, float] | None = None):
    """One call: diff + repo in, (system, user_message, trace) out."""
    g = gather(diff, repo_root, pr=pr, evidence=evidence, system_prompt=system_prompt)
    r = triage(g.items, window=window, shares=shares)
    system, user = render(r)
    return system, user, build_trace(g, r)


__all__ = ["build_context", "gather", "triage", "render", "build_trace", "BudgetError",
           "ContextItem", "Priority", "Gathered", "TriageResult", "PerceptionTrace"]
