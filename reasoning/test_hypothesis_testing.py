# Tests for hypothesis_testing.py, on the lost count sample PR.
#   cd reasoning && python -m unittest test_hypothesis_testing.py

import os
import unittest

import hypothesis_testing as ht


class ObserveTest(unittest.TestCase):
    def test_reads_both_failures_from_the_ci_log(self):
        f = ht.observe(os.path.join(ht.SAMPLE, "ci-test-run.log"))
        self.assertEqual([x["test"] for x in f], ["OpportunityServiceTest.bulkClose", "OpportunityServiceTest.expireStaleClosesAll"])
        self.assertEqual((f[0]["class"], f[0]["line"]), ("OpportunityService", 21))
        self.assertIn("Too many SOQL queries: 101", f[0]["error"])


class ProbeTest(unittest.TestCase):
    def setUp(self):
        failure = ht.observe(os.path.join(ht.SAMPLE, "ci-test-run.log"))[0]
        self.ev = ht.evidence_for(failure)

    def test_added_lines_follow_the_hunk_header(self):
        diff = open(self.ev["diff"]).read()
        self.assertEqual(ht._added_lines(diff, "OpportunityService.cls"), {21, 22, 23, 24})
        self.assertEqual(ht._added_lines(diff, "LeadService.cls"), set())

    def test_each_probe_reads_the_outside_world(self):
        self.assertTrue(ht.probe_failing_line_in_diff(self.ev)[0])
        self.assertTrue(ht.probe_fails_only_in_bulk(self.ev)[0])
        self.assertFalse(ht.probe_fails_on_main(self.ev)[0])
        self.assertFalse(ht.probe_runs_more_than_once(self.ev)[0])
        self.assertFalse(ht.probe_diff_touches_test(self.ev)[0])
        held, evidence = ht.probe_queries_per_record(self.ev)
        self.assertTrue(held)
        self.assertIn("101 queries from line 21", evidence)

    def test_every_probe_is_read_only(self):
        for name, (_, needs, _) in ht.PROBES.items():
            self.assertIn(needs, ht.ALLOWED, name)


class DecideTest(unittest.TestCase):
    def setUp(self):
        failure = ht.observe(os.path.join(ht.SAMPLE, "ci-test-run.log"))[0]
        self.ev = ht.evidence_for(failure)

    def test_only_the_new_query_survives(self):
        results, calls = ht.test_hypotheses(ht.saved_hypotheses(), self.ev)
        self.assertEqual({r["id"]: r["verdict"] for r in results},
                         {"H1": "supported", "H2": "refuted", "H3": "refuted", "H4": "refuted"})
        self.assertEqual(ht.decide(results)["id"], "H1")

    def test_cheap_checks_run_first_and_each_runs_once(self):
        _, calls = ht.test_hypotheses(ht.saved_hypotheses(), self.ev)
        costs = [c for _, c in calls]
        self.assertEqual(costs, sorted(costs))
        self.assertEqual(len(calls), len(set(n for n, _ in calls)))
        self.assertEqual(calls[-1][0], "fails_on_main")              # the expensive run on main goes last

    def test_one_wrong_prediction_refutes(self):
        h = [{"id": "X", "claim": "c", "predictions": [
            {"says": "a", "probe": "failing_line_in_diff", "expect": True},
            {"says": "b", "probe": "fails_on_main", "expect": True}]}]
        results, _ = ht.test_hypotheses(h, self.ev)
        self.assertEqual(results[0]["verdict"], "refuted")

    def test_two_survivors_means_not_sure(self):
        h = [{"id": "A", "claim": "a", "predictions": [{"says": "x", "probe": "failing_line_in_diff", "expect": True}]},
             {"id": "B", "claim": "b", "predictions": [{"says": "y", "probe": "fails_only_in_bulk", "expect": True}]}]
        results, _ = ht.test_hypotheses(h, self.ev)
        self.assertIsNone(ht.decide(results))

    def test_nothing_survives_means_not_sure(self):
        h = [{"id": "A", "claim": "a", "predictions": [{"says": "x", "probe": "fails_on_main", "expect": True}]}]
        results, _ = ht.test_hypotheses(h, self.ev)
        self.assertIsNone(ht.decide(results))


if __name__ == "__main__":
    unittest.main()
