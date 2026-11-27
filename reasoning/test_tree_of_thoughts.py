# Tests for the reasoning module, on the Episode 2 sample PR.
#   cd reasoning && python -m unittest test_tree_of_thoughts.py

import os
import re
import unittest

import tree_of_thoughts as tot
import review_with_reasoning as r

HERE = os.path.dirname(os.path.abspath(__file__))
SAVED = os.path.join(HERE, "saved_run.json")


class ParseTest(unittest.TestCase):
    def test_branches_are_lines_starting_with_a_dash(self):
        reply = "Here you go:\n- Use a Map\n1. numbered\n- Recompute with COUNT()\n"
        self.assertEqual(tot.parse_branches(reply, 4), ["Use a Map", "Recompute with COUNT()"])

    def test_the_same_idea_in_new_words_is_one_branch(self):
        reply = "- Use a Map.\n- use a map\n- Use a roll-up field"
        self.assertEqual(tot.parse_branches(reply, 4), ["Use a Map.", "Use a roll-up field"])

    def test_at_most_n_branches(self):
        self.assertEqual(len(tot.parse_branches("- a\n- b\n- c\n- d\n- e", 3)), 3)

    def test_score_and_why(self):
        self.assertEqual(tot.parse_score("SCORE: 0.78\nWHY: One query."), (0.78, "One query."))

    def test_scores_are_kept_between_0_and_1(self):
        self.assertEqual(tot.parse_score("SCORE: 7\nWHY: x")[0], 1.0)

    def test_a_reply_we_cannot_read_scores_zero(self):
        self.assertEqual(tot.parse_score("I think it's quite good!")[0], 0.0)


class FakeLLM:
    """Every node proposes the same three steps; scores come from a table."""
    def __init__(self, scores):
        self.scores = scores
        self.calls = 0

    def __call__(self, prompt):
        self.calls += 1
        if prompt.startswith("A partial line of reasoning"):
            last = re.findall(r"^\d+\. (.+)$", prompt, re.M)[-1]
            return "SCORE: " + str(self.scores[last]) + "\nWHY: table"
        return "- good\n- okay\n- bad"


class SearchTest(unittest.TestCase):
    def test_weak_branches_are_pruned_and_only_the_best_are_expanded(self):
        llm = FakeLLM({"good": 0.9, "okay": 0.5, "bad": 0.1})
        best, root, calls = tot.tree_search("p", llm, n=3, beam=1, depth=2)
        self.assertEqual([c.status for c in root.children], ["kept", "cut", "pruned"])
        self.assertEqual(root.children[1].children, [])          # only the kept node goes deeper
        self.assertEqual(best.steps, ["good", "good"])
        self.assertEqual(calls, {"propose": 2, "score": 6})
        self.assertEqual(llm.calls, 8)

    def test_if_everything_is_a_dead_end_the_search_stops(self):
        llm = FakeLLM({"good": 0.1, "okay": 0.1, "bad": 0.1})
        best, root, calls = tot.tree_search("p", llm, n=3, beam=2, depth=3)
        self.assertEqual(calls["propose"], 1)
        self.assertIs(best, root)

    def test_the_propose_prompt_carries_the_path(self):
        seen = []
        tot.tree_search("Solve AB x AB = CAB", lambda p: seen.append(p) or "", n=4, depth=1)
        self.assertIn("Solve AB x AB = CAB", seen[0])
        self.assertIn("Propose 4 genuinely different ways", seen[0])


class SalesforceReviewTest(unittest.TestCase):
    def setUp(self):
        self.llm = tot.ReplayLLM(SAVED)
        self.problem = r.build_problem()

    def test_the_problem_has_eyes_notebook_and_the_method_that_undoes(self):
        self.assertIn("Too many SOQL queries: 101", self.problem)          # CI
        self.assertIn("Queries live in *Selector classes", self.problem)  # semantic memory
        self.assertIn("PR #198", self.problem)                             # episodic memory
        self.assertIn("public static void reopen(", self.problem)          # the method that undoes a loss
        self.assertIn("bad mass update", self.problem)

    def test_chain_of_thought_takes_the_first_idea_and_keeps_the_drift(self):
        best, root, calls = tot.tree_search(self.problem, self.llm, n=1, beam=1, depth=2)
        self.assertTrue(best.steps[0].startswith("Do what PR #198 did"))
        self.assertIn("drifts", best.why)
        self.assertEqual(calls["propose"] + calls["score"], 4)

    def test_tree_of_thoughts_finds_the_recompute_and_prunes_the_queueable(self):
        best, root, calls = tot.tree_search(self.problem, self.llm, n=4, beam=2, depth=2, prune_below=0.30)
        self.assertTrue(best.steps[0].startswith("Stop adding 1"))
        self.assertIn("reopen()", best.steps[1])
        self.assertEqual(best.score, 0.93)
        status = {c.step.split(",")[0]: c.status for c in root.children}
        self.assertEqual(status["Move the counting into a Queueable"], "pruned")
        self.assertEqual(calls, {"propose": 3, "score": 10})

    def test_method_source_reads_one_method(self):
        src = r.method_source(open(r.SERVICE).read(), "reopen")
        self.assertTrue(src.startswith("    /**"))
        self.assertTrue(src.rstrip().endswith("}"))
        self.assertNotIn("expireStale", src)


if __name__ == "__main__":
    unittest.main()
