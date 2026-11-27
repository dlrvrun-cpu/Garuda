# Garuda thinks before it comments: Tree of Thoughts on a real Salesforce review.
# Run:  python review_with_reasoning.py            (saved answers, no API key)
#       python review_with_reasoning.py --live     (asks Claude, needs ANTHROPIC_API_KEY)
#
# Same PR as Episodes 2 and 3: closeLostOpportunities adds a SOQL query and an update
# inside the loop to count lost Opportunities on each Account. CI fails with
# "Too many SOQL queries: 101". Finding the bug is easy. Picking the right fix is the
# part that needs thinking, so that is the problem we give the search.
#
# Eyes (context) and the notebook (memory) build the problem. Reasoning picks the fix.

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "memory"))

import garuda_memory as memory                     # noqa: E402
import tree_of_thoughts as tot                     # noqa: E402

SAMPLE = os.path.join(HERE, "..", "context", "sample_pr")
SERVICE = os.path.join(SAMPLE, "repo", "force-app", "main", "default", "classes", "OpportunityService.cls")


def method_source(cls_text, name):
    """The doc comment and body of one Apex method, by brace counting."""
    start = cls_text.find(" " + name + "(")
    if start < 0:
        return ""
    doc = cls_text.rfind("/**", 0, start)
    head = doc if doc >= 0 and "}" not in cls_text[doc:start] else start
    begin = cls_text.rfind("\n", 0, head) + 1
    i = cls_text.find("{", start)
    depth = 0
    while i < len(cls_text):
        depth += {"{": 1, "}": -1}.get(cls_text[i], 0)
        if depth == 0:
            return cls_text[begin:i + 1].strip("\n")
        i += 1
    return ""


def build_problem(pr_dir=SAMPLE):
    """Everything the student has on the desk: the question, the eyes, the notebook."""
    parts, files, labels, recalled, used = memory.build_working_memory(pr_dir, os.path.join(HERE, "..", "memory", "episodes.jsonl"))
    intent = open(os.path.join(pr_dir, "pr.md")).read().strip()
    reopen = method_source(open(SERVICE).read(), "reopen")
    sections = ["Problem: Garuda found SOQL and DML inside a loop in OpportunityService.closeLostOpportunities. "
                "CI fails: OpportunityServiceTest.bulkClose, Too many SOQL queries: 101. "
                "Decide which fix Garuda should suggest in its review comment.",
                "## What the PR is for\n" + intent]
    sections += ["## " + title + "\n" + text for title, text in parts if text]
    sections.append("## Another method in the same class that changes the stage\n" + reopen)
    return "\n\n".join(sections)


def show(title, best, root, calls):
    print("=" * 72)
    print(title + "   (" + str(calls["propose"] + calls["score"]) + " model calls: "
          + str(calls["propose"]) + " propose, " + str(calls["score"]) + " score)")
    print("=" * 72)
    tot.print_tree(root)
    print("\nBest path (" + format(best.score, ".2f") + "):")
    for i, s in enumerate(best.steps):
        print("  " + str(i + 1) + ". " + s)
    print("")


if __name__ == "__main__":
    live = "--live" in sys.argv
    llm = tot.claude_llm() if live else tot.ReplayLLM(os.path.join(HERE, "saved_run.json"))
    problem = build_problem()
    print("The problem Garuda reasons about is ~" + format(memory.tokens(problem), ",") + " tokens.\n")

    best, root, calls = tot.tree_search(problem, llm, n=1, beam=1, depth=2)
    show("CHAIN OF THOUGHT: one idea at a time, never looks back", best, root, calls)

    best, root, calls = tot.tree_search(problem, llm, n=4, beam=2, depth=2, prune_below=0.30)
    show("TREE OF THOUGHTS: propose 4, score, prune below 0.30, keep the best 2, go one deeper", best, root, calls)
