# garuda/perception/items.py — what one piece of context looks like
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class Priority(IntEnum):
    """Higher number = more important. Labels match the triage diagram (P0 is top)."""

    CRITICAL = 4    # P0: system prompt, safety rules, the task, the diff itself
    IMPORTANT = 3   # P1: changed Apex in full, tests, errors, blast radius
    SUPPORTING = 2  # P2: summaries (flows, permissions), signatures, conventions
    DEFERRABLE = 1  # P3: not loaded; the model sees a one-line handle

    @property
    def label(self) -> str:
        return f"P{4 - self.value}"


def estimate_tokens(text: str) -> int:
    """Roughly 4 characters per token. Good enough for budgeting, free to compute."""
    return max(1, len(text) // 4)


@dataclass
class ContextItem:
    name: str                 # what the model sees in the header, e.g. a file path
    content: str
    priority: Priority
    kind: str = "other"       # "diff", "apex", "test", "flow-summary", "evidence", ...
    tokens: int | None = None
    source_tokens: int | None = None   # size of the raw thing this item stands for
    is_error: bool = False             # failed tests / deploys: packed first in their tier
    fallback: ContextItem | None = None  # smaller version to use if this doesn't fit
    fetch_hint: str = "read_file"      # tool the model can call to get the full thing

    def __post_init__(self):
        if self.tokens is None:
            self.tokens = estimate_tokens(self.content)
        if self.source_tokens is None:
            self.source_tokens = self.tokens


def as_handle(item: ContextItem, why: str = "") -> ContextItem:
    """P3: keep the *existence* of something in context, not its content (~20 tokens)."""
    note = f" ({why})" if why else ""
    return ContextItem(
        name=item.name,
        content=f"{item.name}: ~{item.source_tokens:,} tokens, not loaded{note}. "
                f"Fetch with {item.fetch_hint}.",
        priority=Priority.DEFERRABLE,
        kind="handle",
        source_tokens=item.source_tokens,
        fetch_hint=item.fetch_hint,
    )
