# Garuda's reasoning

Building Garuda, Episode 4. Plain Python, no libraries needed for the demos.

## Hypothesis testing: why did CI fail?

| File | What it does |
|---|---|
| `hypothesis_testing.py` | Observe the failure, take a few hypotheses with checkable predictions, test each against the diff, the CI log, the debug log and a run on main (cheapest first), keep the one whose predictions all held, and hand the fix to a person. Probes are read-only. Verdicts come from evidence, never from the model. |
| `saved_hypotheses.json` | Four saved hypotheses for the sample PR. `--live` asks Claude for them instead. |
| `evidence/` | Sample outside state: the test class run on main, and the Apex debug log for bulkClose. |
| `test_hypothesis_testing.py` | 9 tests. |

```bash
cd reasoning
python hypothesis_testing.py           # H1 (new query in the loop) supported, H2-H4 refuted
python -m unittest test_hypothesis_testing.py
```

## Tree of Thoughts: which fix to suggest?

| File | What it does |
|---|---|
| `tree_of_thoughts.py` | The search. `PROPOSE_PROMPT` asks for n genuinely different next steps. `EVAL_PROMPT` scores a partial path from 0.00 to 1.00. `tree_search()` proposes, scores, prunes below a threshold, keeps the best `beam`, and goes one level deeper. With `n=1, beam=1` it is plain chain of thought. |
| `review_with_reasoning.py` | Runs it on the sample PR from Episodes 2 and 3. Context and memory build the problem, reasoning picks the fix. |
| `saved_run.json` | Saved answers, so the demo and the tests run with no API key. |
| `test_tree_of_thoughts.py` | 13 tests. |

```bash
cd reasoning
python review_with_reasoning.py          # saved answers
python review_with_reasoning.py --live   # asks Claude (pip install anthropic, set ANTHROPIC_API_KEY)
python -m unittest test_tree_of_thoughts.py
```

## What it shows

The PR counts lost Opportunities with a query and an update inside the loop. CI fails at 101 queries.
Finding that is easy. Picking the fix is the hard part.

- **Chain of thought** (4 calls) goes with the first idea, the fix that worked on PR #198:
  read the Accounts once, add 1 in a Map. It fixes the 101 error, but the count never comes down
  when `reopen()` undoes a bad mass update.
- **Tree of Thoughts** (13 calls) proposes 4 fixes, prunes the Queueable (0.18), cuts the roll-up
  field (0.48), keeps two, and finds the path that scores 0.93: recompute the count with one
  aggregate query, and call the same recompute from `reopen()`.

The saved scores are an example run. A live run will give different numbers, so treat them as the shape of the search, not a benchmark.
