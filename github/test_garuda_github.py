# Offline tests: a fake GitHub and a fake Claude, the real context engine.
#   python -m unittest github/test_garuda_github.py

import os
import json
import base64
import unittest
from types import SimpleNamespace

import garuda_github as g

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(HERE, "..", "context", "sample_pr")
PATCH = open(os.path.join(SAMPLE, "pr.diff")).read().split("+++ b/force-app/main/default/classes/OpportunityService.cls\n")[1]
FILE = "force-app/main/default/classes/OpportunityService.cls"

PR_BODY = """When an Opportunity is closed lost, add 1 to Lost_Count__c on its Account.

```intent
schema: soi/v0
goal: Count lost opportunities on each Account
must_hold:
  - closeLostOpportunities stays bulk safe at 200 records
permit:
  paths:
    - force-app/main/default/classes/OpportunityService*.cls
```
"""


class FakeGitHub(g.GitHub):
    def __init__(self, files=None, comments=None):
        super().__init__("t", "o/r")
        self.files = files or [{"filename": FILE, "patch": PATCH}]
        self.comments = comments or []
        self.store = {}
        self.posts = []

    def call(self, method, path, body=None, accept="application/vnd.github+json"):
        self.posts.append((method, path, body))
        if accept.endswith("diff"):
            return open(os.path.join(SAMPLE, "pr.diff")).read()
        if "/files" in path:
            return self.files
        if path.startswith("/pulls/7/comments?"):
            return self.comments
        if path.startswith("/pulls/comments/") and method == "GET":
            return next(c for c in self.comments if str(c["id"]) == path.split("/")[-1])
        if path.startswith("/contents/") and method == "GET":
            name = path[len("/contents/"):].split("?")[0]
            if name not in self.store:
                raise RuntimeError("GET -> 404: missing")
            return {"content": base64.b64encode(self.store[name].encode()).decode(), "sha": "s"}
        if path.startswith("/contents/") and method == "PUT":
            self.store[path[len("/contents/"):]] = base64.b64decode(body["content"]).decode()
            return {"commit": {"sha": "abc1234def"}}
        return {}


class FakeClaude:
    def __init__(self, review):
        self.review, self.seen = review, []
        self.messages = self

    def create(self, **kwargs):
        self.seen.append(kwargs)
        return SimpleNamespace(stop_reason="end_turn",
                               content=[SimpleNamespace(type="text", text=json.dumps(self.review))])


def pr_event(body=PR_BODY):
    return {"pull_request": {"number": 7, "title": "Log a lost count on each Account", "body": body,
                             "head": {"sha": "deadbeef", "ref": "lost-count"}}}


class ReviewTest(unittest.TestCase):
    def setUp(self):
        os.environ["GITHUB_WORKSPACE"] = os.path.join(SAMPLE, "repo")

    def test_inline_comments_snap_to_diff_and_memory_reaches_the_model(self):
        claude = FakeClaude({"summary": "SOQL and DML in a loop.", "remembered": ["Selector rule -> suggested OpportunitySelector"],
                             "comments": [
                                 {"file": "OpportunityService.cls", "line": 28, "severity": "high", "title": "SOQL inside loop",
                                  "message": "Breaks at 101 records.", "fix": "Query once via OpportunitySelector."},
                                 {"file": "OpportunityBatch.cls", "line": 40, "severity": "low", "title": "Not in diff",
                                  "message": "Elsewhere."}]})
        gh = FakeGitHub()
        payload = g.cmd_review(gh, pr_event(), client=claude)

        system = claude.seen[0]["system"]
        prompt = claude.seen[0]["messages"][0]["content"]
        self.assertIn("Never raise a finding that matches", system)
        self.assertIn("without sharing", prompt)                 # dismissed findings are in context
        self.assertIn("21: ", prompt)                            # numbered added lines
        self.assertEqual(len(payload["comments"]), 1)
        self.assertEqual(payload["comments"][0]["path"], FILE)
        self.assertEqual(payload["comments"][0]["line"], 24)    # 28 is past the hunk, snapped to the nearest added line
        self.assertIn(g.MARKER, payload["comments"][0]["body"])
        self.assertIn("couldn't pin", payload["body"])
        self.assertIn("What I remembered", payload["body"])

    def test_past_failures_are_recalled_into_the_prompt(self):
        import shutil, tempfile
        ws = os.path.join(tempfile.mkdtemp(), "repo")
        shutil.copytree(os.path.join(SAMPLE, "repo"), ws)
        shutil.copy(os.path.join(HERE, "..", "memory", "episodes.jsonl"), os.path.join(ws, g.EPISODES_PATH))
        os.environ["GITHUB_WORKSPACE"] = ws
        claude = FakeClaude({"summary": "ok", "comments": []})
        g.cmd_review(FakeGitHub(), pr_event(), client=claude)
        prompt = claude.seen[0]["messages"][0]["content"]
        self.assertIn("What happened before (episodic memory)", prompt)
        self.assertIn("Too many SOQL queries: 101", prompt)       # PR #198, same mistake in another file
        self.assertNotIn("CaseRouter", prompt.split("What happened before")[1])

    def test_missing_intent_asks_for_one(self):
        claude = FakeClaude({"summary": "ok", "comments": []})
        payload = g.cmd_review(FakeGitHub(), pr_event(body="no intent here"), client=claude)
        self.assertIn("No intent block found", payload["body"])


class PermitTest(unittest.TestCase):
    def test_inside_permit_passes(self):
        self.assertEqual(g.cmd_permit(FakeGitHub(), pr_event()), 0)

    def test_outside_permit_fails(self):
        files = [{"filename": FILE}, {"filename": "force-app/main/default/classes/LeadService.cls"}]
        self.assertEqual(g.cmd_permit(FakeGitHub(files=files), pr_event()), 1)

    def test_memory_is_always_allowed(self):
        files = [{"filename": FILE}, {"filename": g.DISMISSED_PATH}]
        self.assertEqual(g.cmd_permit(FakeGitHub(files=files), pr_event()), 0)


class LearnTest(unittest.TestCase):
    def finding(self):
        meta = {"file": "OpportunityService.cls", "title": "Use a custom label for Closed Lost", "severity": "low", "round": 1}
        return {"id": 11, "line": 21, "body": "x\n" + g.MARKER + json.dumps(meta) + " -->",
                "html_url": "https://github.com/o/r/pull/7#discussion_r11", "user": {"login": "garuda[bot]"}}

    def dismiss(self, who="COLLABORATOR"):
        event = pr_event()
        event["comment"] = {"id": 12, "in_reply_to_id": 11, "author_association": who, "user": {"login": "varun"},
                            "body": "/garuda dismiss It's a standard picklist value"}
        return event

    def test_dismiss_writes_memory_and_ledger(self):
        gh = FakeGitHub(comments=[self.finding()])
        g.cmd_learn(gh, self.dismiss())
        memory = gh.store[g.DISMISSED_PATH]
        self.assertIn('"Use a custom label for Closed Lost" was dismissed on PR #7 by @varun', memory)
        episode = json.loads(gh.store[g.EPISODES_PATH].strip())
        self.assertEqual(episode["label"], "dismissed")
        self.assertIn("It's a standard picklist value", episode["fix"])

    def test_strangers_cannot_change_memory(self):
        gh = FakeGitHub(comments=[self.finding()])
        g.cmd_learn(gh, self.dismiss(who="NONE"))
        self.assertNotIn(g.DISMISSED_PATH, gh.store)

    def test_history_includes_findings_and_decisions(self):
        reply = {"body": "/garuda dismiss intended", "user": {"login": "varun"}}
        text, last = g.history_text([self.finding(), reply])
        self.assertEqual(last, 1)
        self.assertIn("RESULT: OpportunityService.cls line 21: Use a custom label", text)
        self.assertIn("DECISION: @varun dismissed a finding: intended", text)


if __name__ == "__main__":
    unittest.main()
