# garuda/perception/triage.py — fit the gathered items into the context window
#
#   P0 critical    10%  always in. If it doesn't fit, that's a bug: fail loudly.
#   P1 important   30%  errors first, then smallest first; too big -> fallback -> handle
#   P2 supporting  15%  same rules
#   P3 deferrable   0%  one-line handles only
#   reserve        45%  never filled: room to think, call tools, and write the review
#
# Per-tier caps (instead of one shared pool) are what keep P1 from eating the reserve,
# and demotion (instead of dropping) is what keeps a skipped file visible to the model.
from __future__ import annotations

from dataclasses import dataclass, field

from .items import ContextItem, Priority, as_handle

DEFAULT_SHARES = {
    Priority.CRITICAL: 0.10,
    Priority.IMPORTANT: 0.30,
    Priority.SUPPORTING: 0.15,
}


class BudgetError(ValueError):
    pass


@dataclass
class TierUsage:
    cap: int
    used: int = 0
    items: int = 0


@dataclass
class TriageResult:
    window: int
    selected: list[ContextItem] = field(default_factory=list)
    handles: list[ContextItem] = field(default_factory=list)
    compressed: list[tuple[str, int, int]] = field(default_factory=list)  # name, before, after
    demoted: list[tuple[str, str]] = field(default_factory=list)          # name, reason
    tiers: dict[Priority, TierUsage] = field(default_factory=dict)

    @property
    def used(self) -> int:
        return sum(i.tokens for i in self.selected) + sum(h.tokens for h in self.handles)

    @property
    def reserve(self) -> int:
        return self.window - self.used


def triage(items: list[ContextItem], window: int = 200_000,
           shares: dict[Priority, float] | None = None) -> TriageResult:
    shares = shares or DEFAULT_SHARES
    res = TriageResult(window=window)

    for tier in (Priority.CRITICAL, Priority.IMPORTANT, Priority.SUPPORTING):
        usage = res.tiers[tier] = TierUsage(cap=int(window * shares[tier]))
        tier_items = sorted((i for i in items if i.priority == tier),
                            key=lambda i: (not i.is_error, i.tokens))
        for item in tier_items:
            room = usage.cap - usage.used
            if item.tokens <= room:
                choice = item
            elif tier == Priority.CRITICAL:
                raise BudgetError(
                    f"P0 item '{item.name}' needs {item.tokens:,} tokens but only {room:,} of "
                    f"the {usage.cap:,} P0 budget is left. Shrink the prompt or split the PR; "
                    f"never drop P0 silently.")
            elif item.fallback is not None and item.fallback.tokens <= room:
                choice = item.fallback
                res.compressed.append((item.name, item.tokens, choice.tokens))
                res.handles.append(as_handle(item, "full text didn't fit; signatures loaded"))
            else:
                res.demoted.append((item.name, f"{tier.label} budget full "
                                               f"({item.tokens:,} > {room:,} left)"))
                res.handles.append(as_handle(item, f"demoted from {tier.label}"))
                continue
            res.selected.append(choice)
            usage.used += choice.tokens
            usage.items += 1
            if choice is item and item.source_tokens > item.tokens:
                res.compressed.append((item.name, item.source_tokens, item.tokens))

    res.handles += [i for i in items if i.priority == Priority.DEFERRABLE]
    return res
