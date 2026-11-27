# Garuda's reasoning: hypothesis testing, in plain Python.
#
# A CI test failed. Garuda doesn't guess why, and it doesn't trust a confident paragraph either.
# It works like a mechanic with a car that won't start:
#
#   1. Observe:  what exactly failed, and where.
#   2. Suspect:  a few hypotheses, each with a prediction you can check.
#                "If it's the battery, the headlights will be dim."
#   3. Test:     check each prediction against the outside world (the diff, the logs, a run on main),
#                cheapest check first. The model never marks its own homework.
#   4. Decide:   keep the hypothesis whose predictions all came true, reject the rest, cite the evidence.
#   5. Hand over: suggest the fix. Garuda may read anything, but it never pushes, re-runs or skips
#                a test on its own. Fixing is a person's call.
#
# The hypotheses can come from the model (claude_hypotheses) or from a saved file (saved_hypotheses.json).
# The verdicts always come from code and evidence, never from the model.

import os
import re
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(HERE, "..", "context", "sample_pr")
EVIDENCE = os.path.join(HERE, "evidence")

# What Garuda may do while testing: read-only probes. Nothing in this file can change the repo or the org.
ALLOWED = {"read_diff", "read_ci_log", "read_debug_log", "read_base_run"}


# ---------------------------------------------------------------------------
# 1. Observe
# ---------------------------------------------------------------------------

def observe(ci_log):
    """Every failing test, with its error and the first line of our code in the stack."""
    failures = []
    lines = open(ci_log).read().splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^(\w+)\.(\w+)\s+Fail\b", line)
        if m:
            error = lines[i + 1].strip()
            at = re.search(r"Class\.(\w+)\.(\w+): line (\d+)", lines[i + 2])
            failures.append({"test": m.group(1) + "." + m.group(2), "error": error,
                             "class": at.group(1), "method": at.group(2), "line": int(at.group(3)),
                             "where": os.path.basename(ci_log) + ":" + str(i + 1)})
    return failures


# ---------------------------------------------------------------------------
# 3. Probes: small questions answered by the outside world, cheapest first
# ---------------------------------------------------------------------------

def _added_lines(diff, file_name):
    """Line numbers (in the new file) that this diff added to file_name."""
    added, line, inside = set(), 0, False
    for row in diff.splitlines():
        if row.startswith("+++ b/"):
            inside = row.endswith("/" + file_name)
        elif inside and row.startswith("@@"):
            line = int(re.search(r"\+(\d+)", row).group(1))
        elif inside and row.startswith("+"):
            added.add(line); line += 1
        elif inside and not row.startswith("-"):
            line += 1
    return added


def _result(log, test):
    m = re.search(re.escape(test) + r"\s+(Pass|Fail)", open(log).read())
    return m.group(1) if m else None


def probe_failing_line_in_diff(ev):
    f = ev["failure"]
    added = _added_lines(open(ev["diff"]).read(), f["class"] + ".cls")
    return f["line"] in added, f["class"] + ".cls line " + str(f["line"]) + (" was added by this PR" if f["line"] in added else " was not touched by this PR")


def probe_fails_only_in_bulk(ev):
    one, bulk = _result(ev["ci_log"], "OpportunityServiceTest.closeOne"), _result(ev["ci_log"], ev["failure"]["test"])
    return (one == "Pass" and bulk == "Fail"), "closeOne (1 record): " + str(one) + ", bulkClose (200 records): " + str(bulk)


def probe_fails_on_main(ev):
    r = _result(ev["base_run"], ev["failure"]["test"])
    return r == "Fail", ev["failure"]["test"] + " on main: " + str(r)


def probe_runs_more_than_once(ev):
    entries = open(ev["debug_log"]).read().count("METHOD_ENTRY|[36]|OpportunityService.closeLostOpportunities")
    return entries > 1, "closeLostOpportunities entered " + str(entries) + " time(s) in the debug log"


def probe_diff_touches_test(ev):
    touched = "OpportunityServiceTest.cls" in open(ev["diff"]).read()
    return touched, "the diff " + ("changes" if touched else "does not change") + " OpportunityServiceTest.cls"


def probe_queries_per_record(ev):
    log = open(ev["debug_log"]).read()
    in_loop = len(re.findall(r"SOQL_EXECUTE_BEGIN\|\[" + str(ev["failure"]["line"]) + r"\]", log))
    return in_loop > 1, str(in_loop) + " queries from line " + str(ev["failure"]["line"]) + " in one transaction, one per record"


# name: (function, what it reads, cost: 0 = free, 1 = read a log, 2 = needs a fresh run)
PROBES = {
    "failing_line_in_diff": (probe_failing_line_in_diff, "read_diff", 0),
    "diff_touches_test":    (probe_diff_touches_test, "read_diff", 0),
    "fails_only_in_bulk":   (probe_fails_only_in_bulk, "read_ci_log", 1),
    "queries_per_record":   (probe_queries_per_record, "read_debug_log", 1),
    "runs_more_than_once":  (probe_runs_more_than_once, "read_debug_log", 1),
    "fails_on_main":        (probe_fails_on_main, "read_base_run", 2),
}


# ---------------------------------------------------------------------------
# 2 + 4. Test every hypothesis, then decide
# ---------------------------------------------------------------------------

def test_hypotheses(hypotheses, ev):
    """Each prediction says which probe to run and what it should return if the hypothesis is true.
    One wrong prediction refutes a hypothesis. Probes are cached, so a check is only paid for once."""
    cache, calls = {}, []
    order = sorted({p["probe"] for h in hypotheses for p in h["predictions"]}, key=lambda n: PROBES[n][2])
    for name in order:
        fn, needs, cost = PROBES[name]
        assert needs in ALLOWED, "probe " + name + " is not read-only"
        cache[name] = fn(ev)
        calls.append((name, cost))

    results = []
    for h in hypotheses:
        checks = []
        for p in h["predictions"]:
            value, evidence = cache[p["probe"]]
            checks.append({"prediction": p["says"], "held": value == p["expect"], "evidence": evidence})
        verdict = "supported" if all(c["held"] for c in checks) else "refuted"
        results.append({"id": h["id"], "claim": h["claim"], "verdict": verdict, "checks": checks})
    return results, calls


def decide(results):
    supported = [r for r in results if r["verdict"] == "supported"]
    if len(supported) == 1:
        return supported[0]
    return None        # none, or more than one: say "I don't know yet" and ask for a better probe


# ---------------------------------------------------------------------------
# Where hypotheses come from
# ---------------------------------------------------------------------------

def saved_hypotheses():
    with open(os.path.join(HERE, "saved_hypotheses.json")) as f:
        return json.load(f)["hypotheses"]


HYPOTHESIS_PROMPT = """A CI test failed on a Salesforce pull request.
{failure}

Suggest up to 4 different explanations. For each, give predictions that would be true if it
were the cause, using only these checks: {probes}.
Reply with JSON only: {{"hypotheses": [{{"id": "H1", "claim": "...",
"predictions": [{{"says": "...", "probe": "<check>", "expect": true}}]}}]}}"""


def claude_hypotheses(failure, model=None):
    import anthropic
    r = anthropic.Anthropic().messages.create(
        model=model or os.environ.get("GARUDA_MODEL", "claude-sonnet-5-5"), max_tokens=1200,
        messages=[{"role": "user", "content": HYPOTHESIS_PROMPT.format(failure=json.dumps(failure), probes=", ".join(PROBES))}])
    text = r.content[0].text
    return json.loads(text[text.index("{"):text.rindex("}") + 1])["hypotheses"]


# ---------------------------------------------------------------------------
# Run it
# ---------------------------------------------------------------------------

def evidence_for(failure):
    return {"failure": failure, "diff": os.path.join(SAMPLE, "pr.diff"), "ci_log": os.path.join(SAMPLE, "ci-test-run.log"),
            "base_run": os.path.join(EVIDENCE, "base-run.log"), "debug_log": os.path.join(EVIDENCE, "bulkClose-debug.log")}


if __name__ == "__main__":
    failures = observe(os.path.join(SAMPLE, "ci-test-run.log"))
    failure = failures[0]
    print("OBSERVE")
    for f in failures:
        print("  " + f["test"] + ": " + f["error"] + "  (" + f["class"] + " line " + str(f["line"]) + ", " + f["where"] + ")")

    hypotheses = claude_hypotheses(failure) if "--live" in sys.argv else saved_hypotheses()
    results, calls = test_hypotheses(hypotheses, evidence_for(failure))

    print("\nTEST  (" + str(len(calls)) + " read-only checks, cheapest first: " + ", ".join(n for n, _ in calls) + ")")
    for r in results:
        print("\n  " + r["id"] + "  " + r["verdict"].upper() + "  " + r["claim"])
        for c in r["checks"]:
            print("      " + ("held  " if c["held"] else "FAILED") + "  " + c["prediction"])
            print("              " + c["evidence"])

    best = decide(results)
    print("\nDECIDE")
    if best:
        print("  Cause: " + best["claim"])
        print("  Ruled out: " + ", ".join(r["id"] for r in results if r["verdict"] == "refuted"))
        print("  Fix: suggested in the review comment. Garuda does not push, re-run or skip tests. A person decides.")
    else:
        print("  Not sure yet. Garuda says so, and asks for a better check instead of guessing.")
