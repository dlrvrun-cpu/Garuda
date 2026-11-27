# Garuda's reasoning: Tree of Thoughts, in plain Python.
#
# Chain of thought walks one line from start to end. If the first step is a bad one,
# everything after it is built on that bad step.
# Tree of Thoughts does what a good student does on the rough sheet:
#
#   1. Propose: write down a few genuinely different ways to start.
#   2. Score:   give each one a quick check. How promising does it look?
#   3. Prune:   cross out the dead ends.
#   4. Expand:  go one step deeper on the best ones only. Repeat.
#
# The search is plain code. The model is only asked two small questions,
# with the two prompts below: "what could come next?" and "how good is this path?"
#
# llm is any function that takes a prompt string and returns the reply text.
# claude_llm() calls Claude. ReplayLLM plays back saved answers, so the demo and
# the tests run with no API key.

import os
import re
import json

PROPOSE_PROMPT = """{path}

Propose {n} genuinely different ways to continue from here.
Different means a different approach, not the same idea in
new words: if two branches would be checked the same way,
they are one branch and you owe another one.

Each line is one step, not a whole solution. Stop at the
next decision worth making, and leave it open.

One per line, each starting with "- ". No preamble, no
numbering, no commentary.
"""

EVAL_PROMPT = """A partial line of reasoning:
{path}

Score how promising this path looks, from 0.00 (a dead end,
or already wrong) to 1.00 (all but solved). The path is
unfinished by design — judge the direction it is heading,
not whether it has arrived. Reserve scores above 0.90 for
paths whose remaining steps you could name.

Reply in exactly this format:
SCORE: <a number between 0.00 and 1.00>
WHY: <one sentence>"""


# ---------------------------------------------------------------------------
# A path is the problem plus the steps taken so far
# ---------------------------------------------------------------------------

def path_text(problem, steps):
    lines = [problem.strip(), ""]
    if steps:
        lines.append("Steps so far:")
        lines += [str(i + 1) + ". " + s for i, s in enumerate(steps)]
    else:
        lines.append("Steps so far: none yet.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Reading the model's replies
# ---------------------------------------------------------------------------

def _same_idea(text):
    """Lowercase words only, so 'Use a Map.' and 'use a map' count as one branch."""
    return " ".join(re.findall(r"[a-z0-9_]+", text.lower()))


def parse_branches(reply, n):
    """Lines starting with '- ', duplicates dropped, at most n."""
    branches, seen = [], set()
    for line in reply.splitlines():
        line = line.strip()
        if not line.startswith("- "):
            continue
        step = line[2:].strip()
        key = _same_idea(step)
        if step and key not in seen:
            seen.add(key)
            branches.append(step)
    return branches[:n]


def parse_score(reply):
    """(score, why). A reply we can't read scores 0.00, so it gets pruned, not trusted."""
    m = re.search(r"SCORE:\s*([0-9]*\.?[0-9]+)", reply)
    why = re.search(r"WHY:\s*(.+)", reply)
    if not m:
        return 0.0, "Could not read a score."
    score = min(1.0, max(0.0, float(m.group(1))))
    return score, why.group(1).strip() if why else ""


# ---------------------------------------------------------------------------
# The search
# ---------------------------------------------------------------------------

class Node:
    def __init__(self, steps, score=None, why="", depth=0):
        self.steps = steps
        self.score = score
        self.why = why
        self.depth = depth
        self.status = "open"        # open, kept, pruned, cut (scored fine, but not in the top `beam`)
        self.children = []

    @property
    def step(self):
        return self.steps[-1] if self.steps else "(start)"


def tree_search(problem, llm, n=4, beam=2, depth=2, prune_below=0.30):
    """Propose n branches from each kept node, score them, prune the weak, keep the best `beam`.
    Returns (best_node, root, calls). With n=1 and beam=1 this is plain chain of thought."""
    calls = {"propose": 0, "score": 0}
    root = Node([])
    frontier = [root]

    for level in range(1, depth + 1):
        candidates = []
        for node in frontier:
            calls["propose"] += 1
            reply = llm(PROPOSE_PROMPT.format(path=path_text(problem, node.steps), n=n))
            for step in parse_branches(reply, n):
                child = Node(node.steps + [step], depth=level)
                calls["score"] += 1
                child.score, child.why = parse_score(llm(EVAL_PROMPT.format(path=path_text(problem, child.steps))))
                node.children.append(child)
                candidates.append(child)

        for c in candidates:
            if c.score < prune_below:
                c.status = "pruned"
        alive = sorted((c for c in candidates if c.status != "pruned"), key=lambda c: -c.score)
        for c in alive[beam:]:
            c.status = "cut"
        frontier = alive[:beam]
        for c in frontier:
            c.status = "kept"
        if not frontier:
            break

    scored = [c for c in _walk(root) if c.score is not None and c.status != "pruned"]
    best = max(scored, key=lambda c: (c.depth, c.score)) if scored else root
    return best, root, calls


def _walk(node):
    for c in node.children:
        yield c
        yield from _walk(c)


def print_tree(node, indent=""):
    marks = {"kept": "KEEP ", "pruned": "PRUNE", "cut": "CUT  ", "open": "     "}
    for c in node.children:
        print(indent + marks[c.status] + " " + format(c.score, ".2f") + "  " + c.step)
        print(indent + "             " + c.why)
        print_tree(c, indent + "    ")


# ---------------------------------------------------------------------------
# Two ways to answer: Claude, or saved answers
# ---------------------------------------------------------------------------

def claude_llm(model=None, max_tokens=400):
    import anthropic
    client = anthropic.Anthropic()
    model = model or os.environ.get("GARUDA_MODEL", "claude-sonnet-5-5")

    def ask(prompt):
        r = client.messages.create(model=model, max_tokens=max_tokens,
                                   messages=[{"role": "user", "content": prompt}])
        return r.content[0].text
    return ask


class ReplayLLM:
    """Plays back saved answers from a JSON file:
         {"propose": {"<last step, or (start)>": "- a\\n- b"}, "score": {"<last step>": "SCORE: ...\\nWHY: ..."}}
    Keyed by the last step, so the same file works for any n and beam."""

    def __init__(self, path):
        with open(path) as f:
            self.saved = json.load(f)

    def __call__(self, prompt):
        steps = re.findall(r"^\d+\. (.+)$", prompt, re.M)
        last = steps[-1] if steps else "(start)"
        kind = "score" if prompt.startswith("A partial line of reasoning") else "propose"
        if kind == "propose":
            return self.saved["propose"].get(last, "")
        return self.saved["score"].get(last, "SCORE: 0.00\nWHY: No saved answer for this path.")
