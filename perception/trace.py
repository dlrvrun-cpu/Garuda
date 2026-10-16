# garuda/perception/trace.py — an observable record of every perception decision
#
# If the agent misses a bug, the first question is "did it ever see the file?"
# The trace answers that without re-running anything.
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .gather import Gathered
from .items import Priority
from .triage import TriageResult


@dataclass
class PerceptionTrace:
    window: int
    files_in_pr: int
    tokens_naive: int          # load every touched file in full
    tokens_selected: int       # what actually went into the window (incl. handles)
    tiers: dict = field(default_factory=dict)
    compressed: list = field(default_factory=list)
    demoted: list = field(default_factory=list)
    handles: list = field(default_factory=list)
    blocked: list = field(default_factory=list)

    @property
    def selectivity(self) -> float:
        return self.tokens_selected / self.tokens_naive if self.tokens_naive else 0.0

    def to_dict(self) -> dict:
        return {**asdict(self), "selectivity": round(self.selectivity, 3)}

    def report(self) -> str:
        w = self.window
        rows = [f"{'Tier':<14}{'Cap':>9}{'Used':>9}{'Items':>7}"]
        for label, t in self.tiers.items():
            rows.append(f"{label:<14}{t['cap']:>9,}{t['used']:>9,}{t['items']:>7}")
        handle_tokens = self.tokens_selected - sum(t["used"] for t in self.tiers.values())
        rows.append(f"{'P3 handles':<14}{'-':>9}{handle_tokens:>9,}{len(self.handles):>7}")
        rows.append(f"{'Reserve':<14}{w - self.tokens_selected:>9,}"
                    f"   ({(w - self.tokens_selected) / w:.0%} of window, for reasoning)")
        out = [f"Context window: {w:,} tokens   Files in PR: {self.files_in_pr}", "",
               *rows, "",
               f"Naive load (every touched file in full): {self.tokens_naive:,} tokens",
               f"Triaged load:                            {self.tokens_selected:,} tokens"
               f"   (selectivity {self.selectivity:.3f})"]
        if self.compressed:
            out += ["", "Compressed (kept the signal, not the bytes):"]
            out += [f"  {n}: {a:,} -> {b:,} tokens" for n, a, b in self.compressed]
        if self.demoted:
            out += ["", "Demoted to a handle (model knows it exists, can fetch it):"]
            out += [f"  {n}: {why}" for n, why in self.demoted]
        if self.blocked:
            out += ["", "Blocked (NEVER tier, not even the diff hunk):"]
            out += [f"  {p}: {why}" for p, why in self.blocked]
        return "\n".join(out)


def build_trace(g: Gathered, r: TriageResult) -> PerceptionTrace:
    names = {Priority.CRITICAL: "P0 critical", Priority.IMPORTANT: "P1 important",
             Priority.SUPPORTING: "P2 supporting"}
    return PerceptionTrace(
        window=r.window,
        files_in_pr=len(g.changes),
        tokens_naive=g.naive_tokens,
        tokens_selected=r.used,
        tiers={names[p]: {"cap": u.cap, "used": u.used, "items": u.items}
               for p, u in r.tiers.items()},
        compressed=r.compressed,
        demoted=r.demoted,
        handles=[h.name for h in r.handles],
        blocked=g.blocked,
    )
