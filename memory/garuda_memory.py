# Garuda's memory: semantic, episodic and working memory, together.
# Run:  python garuda_memory.py
#  or:  python garuda_memory.py ../context/sample_pr
#
# Semantic memory:  facts about the repo, in a .md file. Always loaded.
# Episodic memory:  what happened on past PRs (failures, fixes, dismissals), one JSON line each.
#                   Only the episodes that match this PR are recalled.
# Working memory:   the context window for this one review. Built here, thrown away after.
#
# No libraries needed. Plain Python 3.

import os
import re
import sys
import json
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
WINDOW = 10000          # tokens in the working memory, same as Episode 2


def tokens(text):
    return len(text) // 4 + 1


# ---------------------------------------------------------------------------
# Semantic memory: facts, no story. A small .md file is enough.
# With thousands of facts (a whole org's docs), swap this for a vector DB search.
# ---------------------------------------------------------------------------

def load_semantic(repo):
    path = os.path.join(repo, ".garuda", "memory", "repo-conventions.md")
    return open(path).read().strip() if os.path.exists(path) else ""


# ---------------------------------------------------------------------------
# Episodic memory: records of specific past experiences.
# ---------------------------------------------------------------------------

def load_episodes(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def changed_files(diff):
    return [os.path.basename(p) for p in re.findall(r"^\+\+\+ b/(.+)$", diff, re.M)]


def labels_in(diff):
    """What kind of change is this? A cheap guess from the added lines."""
    added = "\n".join(l for l in diff.split("\n") if l.startswith("+"))
    found = set()
    if re.search(r"\[\s*SELECT", added, re.I) and re.search(r"^\s*for\s*\(", diff.replace("+", " "), re.M):
        found.add("soql-in-loop")
    if re.search(r"without sharing", added):
        found.add("sharing")
    return found


def recall(episodes, files, labels):
    """The PR is the cue. Match by file first, then by failure label (a similar mistake elsewhere).
    With thousands of episodes, the label match is where a vector DB search comes in."""
    by_file = [e for e in episodes if e["file"] in files]
    by_label = [e for e in episodes if e["label"] in labels and e not in by_file]
    return by_file + by_label


def episode_text(e):
    line = "PR #" + str(e["pr"]) + " (" + e["date"] + "), " + e["file"] + ": " + e["what"] + "."
    if e["error"]:
        line += " It failed: " + e["error"] + "."
    return line + " Fix: " + e["fix"] + ". Result: " + e["outcome"] + "."


def record(path, **episode):
    """After a review, write what happened. Today's working memory becomes tomorrow's episode."""
    episode.setdefault("date", datetime.date.today().isoformat())
    with open(path, "a") as f:
        f.write(json.dumps(episode) + "\n")


# ---------------------------------------------------------------------------
# Working memory: where it all comes together for one review
# ---------------------------------------------------------------------------

def build_working_memory(pr_dir, episodes_path):
    repo = os.path.join(pr_dir, "repo")
    diff = open(os.path.join(pr_dir, "pr.diff")).read()
    files = changed_files(diff)
    labels = labels_in(diff)

    recalled = recall(load_episodes(episodes_path), files, labels)
    parts = [
        ("The change", diff),
        ("What is true in this repo (semantic memory)", load_semantic(repo)),
        ("What happened before (episodic memory)", "\n".join("- " + episode_text(e) for e in recalled)),
    ]
    used = sum(tokens(text) for _, text in parts)
    return parts, files, labels, recalled, used


if __name__ == "__main__":
    pr_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "context", "sample_pr")
    episodes_path = os.path.join(HERE, "episodes.jsonl")
    parts, files, labels, recalled, used = build_working_memory(pr_dir, episodes_path)

    print("THE CUE")
    print("  Files changed:  " + ", ".join(files))
    print("  Looks like:     " + (", ".join(sorted(labels)) or "nothing known"))
    print("  Recalled:       " + str(len(recalled)) + " of " + str(len(load_episodes(episodes_path))) + " episodes")
    print("")
    print("WORKING MEMORY (what the model sees for this review)")
    for title, text in parts:
        print("\n## " + title + "  (~" + str(tokens(text)) + " tokens)")
        print(text)
    print("\n~" + format(used, ",") + " of " + format(WINDOW, ",") + " tokens used. The rest is left to think.")
    print("After the review, record() turns what happened into the next episode.")
