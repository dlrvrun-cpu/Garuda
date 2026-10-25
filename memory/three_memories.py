# The three memories, one at a time, on the same sample PR.
# Run:  python three_memories.py
#
# 1. Working memory:  a hierarchy. Fill the window top-down by priority. What doesn't fit becomes a handle.
# 2. Episodic memory: a test fails, the failure is recorded, and the next PR with the same mistake recalls it.
# 3. Semantic memory: a small .md file is always loaded. A big pile of docs is searched (RAG).
#
# Uses garuda_memory.py from this folder. No libraries needed.

import os
import re
import json
import tempfile

from garuda_memory import tokens, load_semantic, load_episodes, changed_files, labels_in, recall, record, episode_text

HERE = os.path.dirname(os.path.abspath(__file__))
PR = os.path.join(HERE, "..", "context", "sample_pr")


# ---------------------------------------------------------------------------
# 1. Working memory: the rough sheet. Small, so fill it in order of priority.
# ---------------------------------------------------------------------------

def working_memory(layers, window):
    used, loaded, handles = 0, [], []
    for priority, name, text in sorted(layers, key=lambda layer: layer[0]):
        size = tokens(text)
        if used + size <= window:
            loaded.append((priority, name, size))
            used += size
        else:
            handles.append((priority, name, size))      # not loaded, but Garuda can ask for it
    return loaded, handles, used


# ---------------------------------------------------------------------------
# 2. Episodic memory: written when something fails, recalled when it looks the same.
# ---------------------------------------------------------------------------

def remember_failure(path, pr, file, test_log):
    error = re.search(r"System\.LimitException: (.+)", test_log).group(1)
    record(path, pr=pr, file=file, label="soql-in-loop", what="Added a SOQL query inside the for loop",
           error=error, fix="Moved the query before the loop and used a Map<Id, Account>",
           outcome="Tests passed at 200 records")
    return error


# ---------------------------------------------------------------------------
# 3. Semantic memory: .md for what is always true, RAG for everything else.
# ---------------------------------------------------------------------------

def chunks(folder):
    """Compile: cut every doc into sections, each with its source. This is the index at the back."""
    for name in sorted(os.listdir(folder)):
        text = open(os.path.join(folder, name)).read()
        for section in re.split(r"\n(?=## )", text)[1:]:
            title, _, body = section.partition("\n")
            yield name + " > " + title.strip("# "), body.strip()


def words(text):
    return set(re.findall(r"[a-z_]{4,}", text.lower()))


def search(folder, question, top=2):
    """Assemble: score each section by the words it shares with the question. Nothing shared, nothing returned."""
    q = words(question)
    scored = sorted(((len(q & words(body)), src, body) for src, body in chunks(folder)), reverse=True)
    return [(score, src, body) for score, src, body in scored[:top] if score > 0]


if __name__ == "__main__":
    diff = open(os.path.join(PR, "pr.diff")).read()
    repo = os.path.join(PR, "repo")

    print("1. WORKING MEMORY  (window: 1,500 tokens)")
    layers = [
        (0, "The diff", diff),
        (0, "Review rules", open(os.path.join(repo, "REVIEW_RULES.md")).read()),
        (1, "Recalled episodes", "\n".join(episode_text(e) for e in
            recall(load_episodes(os.path.join(HERE, "episodes.jsonl")), changed_files(diff), labels_in(diff)))),
        (2, "Repo conventions", load_semantic(repo)),
        (3, "Full CI log", open(os.path.join(PR, "ci-test-run.log")).read()),
    ]
    loaded, handles, used = working_memory(layers, 1500)
    for p, name, size in loaded:
        print("  P" + str(p) + "  " + name.ljust(20) + str(size).rjust(5) + " tokens  loaded")
    for p, name, size in handles:
        print("  P" + str(p) + "  " + name.ljust(20) + str(size).rjust(5) + " tokens  handle, fetch if needed")
    print("  " + str(used) + " of 1,500 used. The bin takes it after the review.")

    print("\n2. EPISODIC MEMORY")
    path = os.path.join(tempfile.mkdtemp(), "episodes.jsonl")
    log = "OpportunityBatchTest.runsAt200: FAIL\nSystem.LimitException: Too many SOQL queries: 101\n"
    print("  PR #198 test run:   " + log.split("\n")[1])
    remember_failure(path, 198, "OpportunityBatch.cls", log)
    print("  Recorded:           " + json.dumps(load_episodes(path)[0])[:86] + "...")
    hits = recall(load_episodes(path), changed_files(diff), labels_in(diff))
    print("  New PR touches:     " + ", ".join(changed_files(diff)) + ", looks like " + ", ".join(labels_in(diff)))
    print("  Recalled:           PR #" + str(hits[0]["pr"]) + ", " + hits[0]["error"] + ". Fix: " + hits[0]["fix"])

    print("\n3. SEMANTIC MEMORY")
    md = load_semantic(repo)
    print("  .md, always loaded (" + str(tokens(md)) + " tokens):")
    for line in md.split("\n")[1:3]:
        print("    " + line)
    question = "closeLostOpportunities adds 1 to Lost_Count__c on each Account. Can AccountId be null?"
    print("  RAG, searched with the PR: \"" + question + "\"")
    for score, src, body in search(os.path.join(HERE, "org-docs"), question):
        best = max(body.split("\n"), key=lambda line: len(words(line) & words(question)))
        print("    [" + src + "]  " + best)
    print("  Nothing matched?  Then say \"I don't know\", don't guess.")
