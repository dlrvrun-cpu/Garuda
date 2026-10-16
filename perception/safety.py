# garuda/perception/safety.py — the "NEVER" tier
#
# A priority can be outranked. A block list can't. So things that must never reach the
# model are stopped here, before triage ever sees them. Remember: the PR author controls
# every file in the PR, including symlinks.
from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path, PurePosixPath

BLOCKED = {
    "secret file": ["*.key", "*.pem", "*.p12", "*.jks", "*.crt", ".env", ".env.*",
                    "*credentials*.json", "*.namedCredential-meta.xml"],
    "tool cache": [".sfdx/*", ".sf/*", "node_modules/*", ".git/*"],
    "binary / generated": ["*/staticresources/*", "*.zip", "*.png", "*.jpg", "*.gif",
                           "*.pdf", "*.min.js"],
    "possible customer data": ["*/data/*.csv", "*.csv"],
}
MAX_BYTES = 1_000_000


def blocked_reason(rel: str) -> str | None:
    p = PurePosixPath(rel)
    if p.is_absolute() or ".." in p.parts:
        return "path escapes repo"
    for reason, globs in BLOCKED.items():
        for g in globs:
            if fnmatch(p.name, g) or fnmatch(str(p), g) or fnmatch(str(p), "*/" + g):
                return f"{reason} ({g})"
    return None


def safe_read(root: Path, rel: str) -> tuple[str | None, str | None]:
    """Returns (text, None) or (None, why_not)."""
    reason = blocked_reason(rel)
    if reason:
        return None, reason
    root = root.resolve()
    try:
        real = (root / rel).resolve(strict=True)
    except (FileNotFoundError, RuntimeError):
        return None, "missing"
    if not real.is_relative_to(root):
        return None, "resolves outside repo (symlink?)"
    if not real.is_file():
        return None, "not a file"
    if real.stat().st_size > MAX_BYTES:
        return None, f"over {MAX_BYTES:,} bytes"
    data = real.read_bytes()
    if b"\x00" in data[:8192]:
        return None, "binary"
    return data.decode("utf-8", errors="replace"), None
