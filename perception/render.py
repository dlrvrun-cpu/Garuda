# garuda/perception/render.py — turn a triage result into the text the model reads
from __future__ import annotations

from .items import Priority
from .triage import TriageResult

SECTIONS = {
    Priority.CRITICAL: "Task, rules and the change",
    Priority.IMPORTANT: "Code under review, tests, errors and impact",
    Priority.SUPPORTING: "Background (summaries and signatures)",
}


# Triage packs smallest-first; the model should *read* in a sensible order instead.
READ_ORDER = ["task", "diff", "evidence", "apex", "lwc", "apex-test", "blast-radius", "memory",
              "fls-fact", "perm-summary", "flow-summary", "schema", "dependency", "config"]


def _order(item) -> tuple:
    k = READ_ORDER.index(item.kind) if item.kind in READ_ORDER else len(READ_ORDER)
    return (k, item.name)


def _escape(text: str) -> str:
    # A file in the PR could contain "</context>" to break out of its box.
    return text.replace("</context>", "<\\/context>")


def render(result: TriageResult) -> tuple[str, str]:
    """Returns (system, user_message). P0 'system' items go to the system prompt."""
    system = "\n\n".join(i.content for i in result.selected if i.kind in ("system", "rules")
                         and i.priority == Priority.CRITICAL)
    parts = []
    for tier, title in SECTIONS.items():
        tier_items = sorted((i for i in result.selected
                             if i.priority == tier and not (tier == Priority.CRITICAL
                                                            and i.kind in ("system", "rules"))),
                            key=_order)
        if not tier_items:
            continue
        parts.append(f"## {tier.label}: {title}")
        for i in tier_items:
            err = ' error="true"' if i.is_error else ""
            parts.append(f'<context name="{i.name}" kind="{i.kind}"{err}>\n'
                         f"{_escape(i.content)}\n</context>")
    if result.handles:
        parts.append("## P3: Available on request (not loaded)\n"
                     + "\n".join(f"- {h.content}" for h in result.handles))
    return system, "\n\n".join(parts)
