# garuda/classic.py — Garuda v1, the classic way (no AI)
import re

# The rule I wrote by hand: a dynamic SOQL call that glues a variable into the query string
SOQL_INJECTION = re.compile(r"Database\.(query|countQuery)\s*\(.*['\"]\s*\+\s*\w+")


def review_diff(diff: str) -> dict:
    """Input -> Business logic -> Output.

    Input:          the diff text
    Business logic: run my regex on every added line
    Output:         list of SOQL injections found
    """

    # --- INPUT: read the diff, keep only added lines with file + line number ---
    added_lines = []
    file, line_no = None, 0
    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            file = raw[6:]                       # "+++ b/classes/AccountService.cls"
        elif raw.startswith("@@"):
            line_no = int(re.search(r"\+(\d+)", raw).group(1)) - 1
        elif raw.startswith("+"):
            line_no += 1
            added_lines.append((file, line_no, raw[1:]))
        elif not raw.startswith("-"):
            line_no += 1

    # --- BUSINESS LOGIC: check every line against the rule ---
    comments = []
    for file, line, code in added_lines:
        if SOQL_INJECTION.search(code) and "escapeSingleQuotes" not in code:
            comments.append({
                "file": file,
                "line": line,
                "severity": "high",
                "message": "Possible SOQL injection: user input concatenated into Database.query",
            })

    # --- OUTPUT: same shape every time ---
    return {
        "summary": f"{len(comments)} SOQL injection(s) found" if comments else "No issues",
        "comments": comments,
    }
