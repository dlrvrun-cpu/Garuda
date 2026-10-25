import os
import tempfile
import unittest

import three_memories as m


class ThreeMemoriesTest(unittest.TestCase):
    def test_working_memory_fills_by_priority_and_leaves_handles(self):
        layers = [(3, "big log", "x" * 8000), (0, "diff", "x" * 400), (1, "episodes", "x" * 400)]
        loaded, handles, used = m.working_memory(layers, 500)
        self.assertEqual([name for _, name, _ in loaded], ["diff", "episodes"])
        self.assertEqual([name for _, name, _ in handles], ["big log"])
        self.assertLessEqual(used, 500)

    def test_a_failure_is_recorded_and_recalled_for_the_same_mistake(self):
        path = os.path.join(tempfile.mkdtemp(), "episodes.jsonl")
        error = m.remember_failure(path, 198, "OpportunityBatch.cls",
                                   "System.LimitException: Too many SOQL queries: 101\n")
        self.assertEqual(error, "Too many SOQL queries: 101")
        hits = m.recall(m.load_episodes(path), ["OpportunityService.cls"], {"soql-in-loop"})
        self.assertEqual(hits[0]["pr"], 198)

    def test_rag_finds_the_section_and_abstains_when_nothing_matches(self):
        docs = os.path.join(m.HERE, "org-docs")
        top = m.search(docs, "Can AccountId be null when we add to Lost_Count__c on the Account?")
        self.assertIn("account-rollups.md > Lost and won counts", [src for _, src, _ in top])
        self.assertEqual(m.search(docs, "zebra quantum"), [])


if __name__ == "__main__":
    unittest.main()
