# Tests for garuda_memory.py, on the Episode 2 sample PR.
#   cd memory && python -m unittest test_garuda_memory.py

import os
import json
import shutil
import tempfile
import unittest

import garuda_memory as m

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(HERE, "..", "context", "sample_pr")
EPISODES = os.path.join(HERE, "episodes.jsonl")


class SemanticTest(unittest.TestCase):
    def test_conventions_load_from_the_md_file(self):
        facts = m.load_semantic(os.path.join(SAMPLE, "repo"))
        self.assertIn("Queries live in *Selector classes", facts)

    def test_missing_file_means_no_facts(self):
        self.assertEqual(m.load_semantic(tempfile.mkdtemp()), "")


class EpisodicTest(unittest.TestCase):
    def setUp(self):
        self.diff = open(os.path.join(SAMPLE, "pr.diff")).read()
        self.episodes = m.load_episodes(EPISODES)

    def test_the_pr_is_the_cue(self):
        self.assertEqual(m.changed_files(self.diff), ["OpportunityService.cls"])
        self.assertEqual(m.labels_in(self.diff), {"soql-in-loop"})

    def test_recall_by_file_then_by_label(self):
        recalled = m.recall(self.episodes, ["OpportunityService.cls"], {"soql-in-loop"})
        self.assertEqual([e["pr"] for e in recalled], [212, 198])   # same file first, then same mistake

    def test_unrelated_episodes_stay_out(self):
        recalled = m.recall(self.episodes, ["OpportunityService.cls"], {"soql-in-loop"})
        self.assertNotIn(219, [e["pr"] for e in recalled])          # CaseRouter has nothing to do with this PR

    def test_no_cue_no_memory(self):
        self.assertEqual(m.recall(self.episodes, ["LeadService.cls"], set()), [])

    def test_soql_outside_a_loop_is_not_a_loop_mistake(self):
        diff = "+++ b/classes/A.cls\n@@ -1 +1 @@\n+List<Account> a = [SELECT Id FROM Account];\n"
        self.assertEqual(m.labels_in(diff), set())

    def test_episode_text_keeps_the_error_and_the_fix(self):
        text = m.episode_text(next(e for e in self.episodes if e["pr"] == 198))
        self.assertIn("Too many SOQL queries: 101", text)
        self.assertIn("Map<Id, Account>", text)


class RecordTest(unittest.TestCase):
    def test_record_appends_an_episode_that_recall_finds_next_time(self):
        path = os.path.join(tempfile.mkdtemp(), "episodes.jsonl")
        shutil.copy(EPISODES, path)
        m.record(path, pr=230, file="LeadService.cls", label="dml-in-loop",
                 what="update inside the loop", error="Too many DML statements: 151",
                 fix="one update after the loop", outcome="Tests passed")
        last = json.loads(open(path).read().strip().split("\n")[-1])
        self.assertEqual(last["pr"], 230)
        self.assertIn("date", last)
        self.assertEqual([e["pr"] for e in m.recall(m.load_episodes(path), ["LeadService.cls"], set())], [230])


class WorkingMemoryTest(unittest.TestCase):
    def test_all_three_come_together_inside_the_window(self):
        parts, files, labels, recalled, used = m.build_working_memory(SAMPLE, EPISODES)
        titles = [t for t, _ in parts]
        self.assertEqual(titles[0], "The change")
        self.assertIn("semantic memory", titles[1])
        self.assertIn("episodic memory", titles[2])
        self.assertIn("SOQL queries: 101", parts[2][1])
        self.assertLess(used, m.WINDOW)


if __name__ == "__main__":
    unittest.main()
