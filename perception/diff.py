# garuda/perception/diff.py — turn a unified diff into per-file changes
from __future__ import annotations

import re
from dataclasses import dataclass, field

HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass
class FileChange:
    path: str
    status: str                                    # "added" | "modified" | "deleted"
    added: list[tuple[int, str]] = field(default_factory=list)    # (new line no, text)
    removed: list[tuple[int, str]] = field(default_factory=list)  # (old line no, text)
    lines: list[str] = field(default_factory=list)                # raw hunk lines

    @property
    def patch(self) -> str:
        return "\n".join(self.lines)


def _path(raw: str) -> str | None:
    p = raw.split("\t")[0].strip()          # git adds a tab after paths with spaces
    if p == "/dev/null":
        return None
    return p[2:] if p[:2] in ("a/", "b/") else p


def parse_diff(text: str) -> list[FileChange]:
    changes: list[FileChange] = []
    cur: FileChange | None = None
    old_left = new_left = 0                 # lines still expected in the current hunk
    old_no = new_no = 0
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        in_hunk = old_left > 0 or new_left > 0

        if not in_hunk and line.startswith("--- ") and i + 1 < len(lines) \
                and lines[i + 1].startswith("+++ "):
            old, new = _path(line[4:]), _path(lines[i + 1][4:])
            status = "added" if old is None else "deleted" if new is None else "modified"
            cur = FileChange(new or old, status)
            changes.append(cur)
            i += 2
            continue

        m = HUNK.match(line) if (cur and not in_hunk) else None
        if m:
            old_no, new_no = int(m[1]), int(m[3])
            old_left = int(m[2]) if m[2] is not None else 1
            new_left = int(m[4]) if m[4] is not None else 1
            cur.lines.append(line)
        elif cur and in_hunk:
            cur.lines.append(line)
            tag, body = line[:1], line[1:]
            if tag == "+":
                cur.added.append((new_no, body)); new_no += 1; new_left -= 1
            elif tag == "-":
                cur.removed.append((old_no, body)); old_no += 1; old_left -= 1
            elif tag == "\\":
                pass                         # "\ No newline at end of file"
            else:
                old_no += 1; new_no += 1; old_left -= 1; new_left -= 1
        i += 1
    return changes
