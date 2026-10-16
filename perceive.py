# garuda/perceive.py — Garuda v2: build the reviewer's context window for a PR
#
#   python perceive.py                    # PR #482 fixture, 200K window, trace report
#   python perceive.py --shares 0.10,0.02,0.01 --window 20000   # squeeze P1/P2: watch
#                                         # compression and demotion happen
#   python perceive.py --show             # print exactly what the model would read
#   python perceive.py --json             # trace as JSON (log this on every run)
#   python perceive.py --review           # send it to Claude (needs ANTHROPIC_API_KEY)
#   python perceive.py --diff my.diff --repo ../my-sfdx-repo
from __future__ import annotations

import argparse
import json
from pathlib import Path

from perception import BudgetError, Priority, build_context

HERE = Path(__file__).parent
FIXTURE = HERE / "examples" / "pr482"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--diff", default=str(FIXTURE / "pr482.diff"))
    ap.add_argument("--repo", default=str(FIXTURE / "repo"))
    ap.add_argument("--pr", default=str(FIXTURE / "pr.json"), help="PR metadata JSON")
    ap.add_argument("--evidence", nargs="*", default=[str(FIXTURE / "ci" / "validation-deploy.txt")],
                    help="CI logs / failed test output (treated as protected errors)")
    ap.add_argument("--window", type=int, default=200_000)
    ap.add_argument("--shares", default="0.10,0.30,0.15",
                    help="P0,P1,P2 budget shares of the window (rest is reasoning reserve)")
    ap.add_argument("--show", action="store_true", help="print the rendered context")
    ap.add_argument("--json", action="store_true", help="print the trace as JSON")
    ap.add_argument("--review", action="store_true", help="send the context to Claude")
    args = ap.parse_args()

    pr = json.loads(Path(args.pr).read_text()) if args.pr and Path(args.pr).exists() else None
    evidence = [(f"CI: {Path(p).name}", Path(p).read_text()) for p in args.evidence
                if Path(p).exists()]
    p0, p1, p2 = (float(x) for x in args.shares.split(","))
    shares = {Priority.CRITICAL: p0, Priority.IMPORTANT: p1, Priority.SUPPORTING: p2}
    try:
        system, user, trace = build_context(Path(args.diff).read_text(), args.repo,
                                            window=args.window, pr=pr, evidence=evidence,
                                            shares=shares)
    except BudgetError as e:
        raise SystemExit(f"Budget error: {e}")

    if args.json:
        print(json.dumps(trace.to_dict(), indent=2))
    else:
        title = f'PR #{pr["number"]}: {pr["title"]}' if pr else args.diff
        print(f"Garuda perception for {title}\n")
        print(trace.report())
    if args.show:
        print("\n" + "=" * 30 + " SYSTEM " + "=" * 30 + f"\n{system}")
        print("\n" + "=" * 30 + " USER " + "=" * 32 + f"\n{user}")
    if args.review:
        import anthropic
        msg = anthropic.Anthropic().messages.create(
            model="claude-sonnet-4-6", max_tokens=4096, system=system,
            messages=[{"role": "user", "content": user}])
        print("\n" + "=" * 30 + " REVIEW " + "=" * 30 + "\n" + msg.content[0].text)


if __name__ == "__main__":
    main()
