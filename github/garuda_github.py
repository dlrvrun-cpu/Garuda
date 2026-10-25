# Garuda on GitHub: the context engine, wired to real pull requests.
#
#   python garuda_github.py review    on pull_request: build context, review, post inline comments
#   python garuda_github.py permit    on pull_request: fail if the PR touches files outside its intent
#   python garuda_github.py learn     on a reply "/garuda dismiss <why>": write it to .garuda/memory
#
# Runs inside GitHub Actions (see action.yml). Needs GITHUB_TOKEN, GITHUB_REPOSITORY,
# GITHUB_EVENT_PATH, and ANTHROPIC_API_KEY for review.
#
# Memory lives in the repo, so you can read it, review it and revert it like code:
#   .garuda/memory/repo-conventions.md     semantic: facts about this repo
#   .garuda/memory/dismissed-findings.md   episodic: what people told Garuda not to say again
#   .garuda/memory/episodes.jsonl          episodic: what happened on past PRs (failures, fixes, dismissals)

import os
import re
import sys
import json
import base64
import fnmatch
import logging
import tempfile
import datetime
import urllib.request
import urllib.error

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "context"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "memory"))

import garuda_memory

logger = logging.getLogger("garuda.github")

MARKER = "<!-- garuda:finding "
DISMISSED_PATH = ".garuda/memory/dismissed-findings.md"
EPISODES_PATH = ".garuda/memory/episodes.jsonl"
TRUSTED = ("OWNER", "MEMBER", "COLLABORATOR")

REVIEW_INSTRUCTIONS = """
Memory rules:
- Never raise a finding that matches an entry in "Dismissed findings". People already said no.
- Follow "repo-conventions.md". When a finding breaks a convention, say which one.
- If "What happened before" lists a past failure like this one, say so and point to the fix that worked.
- If the PR description has an intent block, check the change against its goal and must_hold rules.
Extra JSON fields: give every comment a short "title" (under 8 words), and add a top-level
"remembered": ["<memory entry> -> <what you did differently because of it>", ...]."""


# ---------------------------------------------------------------------------
# GitHub REST, with nothing but the standard library
# ---------------------------------------------------------------------------

class GitHub:
    def __init__(self, token, repo, api="https://api.github.com"):
        self.token, self.repo, self.api = token, repo, api

    def call(self, method, path, body=None, accept="application/vnd.github+json"):
        url = path if path.startswith("http") else self.api + "/repos/" + self.repo + path
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": "Bearer " + self.token, "Accept": accept,
            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "garuda"})
        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read().decode()
        except urllib.error.HTTPError as e:
            raise RuntimeError(method + " " + path + " -> " + str(e.code) + ": " + e.read().decode()[:500])
        if accept.endswith("diff"):
            return raw
        return json.loads(raw) if raw else None

    def paged(self, path):
        out, page = [], 1
        while True:
            sep = "&" if "?" in path else "?"
            batch = self.call("GET", path + sep + "per_page=100&page=" + str(page))
            out += batch
            if len(batch) < 100:
                return out
            page += 1

    def read_file(self, path, ref):
        """Returns (text, sha). Missing file gives ("", None)."""
        try:
            got = self.call("GET", "/contents/" + path + "?ref=" + ref)
        except RuntimeError as e:
            if "-> 404" in str(e):
                return "", None
            raise
        return base64.b64decode(got["content"]).decode(), got["sha"]

    def write_file(self, path, branch, text, sha, message):
        body = {"message": message, "branch": branch, "content": base64.b64encode(text.encode()).decode()}
        if sha:
            body["sha"] = sha
        return self.call("PUT", "/contents/" + path, body)["commit"]["sha"]


# ---------------------------------------------------------------------------
# Intent: what this PR is meant to do, and which files it may touch
# ---------------------------------------------------------------------------

INTENT_BLOCK = re.compile(r"```intent\s*\n(.*?)```", re.DOTALL)


def parse_intent(pr_body):
    """The intent lives in the PR description, in a ```intent block (schema soi/v0)."""
    match = INTENT_BLOCK.search(pr_body or "")
    if not match:
        return None
    return yaml.safe_load(match.group(1)) or {}


def outside_permit(files, intent):
    """Files the PR changes that no permit glob covers. Garuda's own memory is always allowed."""
    globs = (intent.get("permit") or {}).get("paths") or []
    allowed = globs + [".garuda/memory/*"]
    return [f for f in files if not any(fnmatch.fnmatch(f, g) for g in allowed)]


# ---------------------------------------------------------------------------
# Diff lines: GitHub only takes inline comments on lines that are in the diff
# ---------------------------------------------------------------------------

def commentable_lines(patch):
    """Right-side line numbers in a file's patch, and which of them were added."""
    lines, added, new_line = set(), {}, 0
    for row in (patch or "").split("\n"):
        hunk = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)", row)
        if hunk:
            new_line = int(hunk.group(1))
            continue
        if row.startswith("-"):
            continue
        if row.startswith("+"):
            added[new_line] = row[1:]
        lines.add(new_line)
        new_line += 1
    return lines, added


def snap(line, lines, added):
    """The model's line number can be a little off. Move it to the nearest line in the diff,
    preferring an added line. Too far away means it goes in the summary instead."""
    if line in lines:
        return line
    pool = added or lines
    nearest = min(pool, key=lambda n: abs(n - line), default=None)
    return nearest if nearest is not None and abs(nearest - line) <= 6 else None


# ---------------------------------------------------------------------------
# Episodic memory, part 1: earlier Garuda rounds on this PR become review-history.txt
# ---------------------------------------------------------------------------

def finding_meta(body):
    match = re.search(re.escape(MARKER) + r"(\{.*?\}) -->", body or "")
    return json.loads(match.group(1)) if match else None


def history_text(review_comments):
    """Same format as sample_pr/review-history.txt, so semantic compaction can shrink it."""
    rounds = {}
    for c in review_comments:
        meta = finding_meta(c["body"])
        if meta:
            rounds.setdefault(meta.get("round", 1), []).append(
                "RESULT: " + meta["file"] + " line " + str(c.get("line") or c.get("original_line")) +
                ": " + meta["title"])
        elif c["body"].strip().lower().startswith("/garuda dismiss"):
            rounds.setdefault(max(rounds or [1]), []).append(
                "DECISION: @" + c["user"]["login"] + " dismissed a finding: " + c["body"].strip()[15:].strip())
    out = []
    for n in sorted(rounds):
        out += ["=== Review round " + str(n), "Garuda reviewed this PR."] + rounds[n] + [""]
    return "\n".join(out), (max(rounds) if rounds else 0)


# ---------------------------------------------------------------------------
# review
# ---------------------------------------------------------------------------

def recall_episodes(workspace, diff):
    path = os.path.join(workspace, EPISODES_PATH)
    if not os.path.exists(path):
        return []
    files = garuda_memory.changed_files(diff)
    recalled = garuda_memory.recall(garuda_memory.load_episodes(path), files, garuda_memory.labels_in(diff))
    logger.info("Recalled %d episode(s) for %s", len(recalled), ", ".join(files))
    return recalled


def build_pr_dir(gh, pr, files, workspace):
    """Lay the PR out the way the context engine expects: pr.diff, pr.md, review-history.txt, repo/."""
    pr_dir = tempfile.mkdtemp(prefix="garuda-")
    diff = gh.call("GET", "/pulls/" + str(pr["number"]), accept="application/vnd.github.diff")
    with open(os.path.join(pr_dir, "pr.diff"), "w") as f:
        f.write(diff)

    # The full file in context has no line numbers. Give the model the new line numbers here.
    numbered = []
    for item in files:
        _, added = commentable_lines(item.get("patch"))
        if added and item["filename"].endswith((".cls", ".trigger")):
            numbered.append("Lines added in " + item["filename"] + " (new line numbers):")
            numbered += [str(n) + ": " + text for n, text in sorted(added.items())]
    # Episodic memory: the PR is the cue. Recall past episodes by file, then by failure label.
    recalled = recall_episodes(workspace, diff)
    if recalled:
        numbered += ["", "What happened before (episodic memory):"]
        numbered += ["- " + garuda_memory.episode_text(e) for e in recalled]
    with open(os.path.join(pr_dir, "pr.md"), "w") as f:
        f.write("# " + pr["title"] + "\n" + (pr.get("body") or "") + "\n\n" + "\n".join(numbered))

    history, last_round = history_text(gh.paged("/pulls/" + str(pr["number"]) + "/comments"))
    if history:
        with open(os.path.join(pr_dir, "review-history.txt"), "w") as f:
            f.write(history)

    ci_log = os.environ.get("GARUDA_CI_LOG")
    if ci_log and os.path.exists(ci_log):
        os.symlink(os.path.abspath(ci_log), os.path.join(pr_dir, "ci-test-run.log"))
    os.symlink(os.path.abspath(workspace), os.path.join(pr_dir, "repo"))
    return pr_dir, last_round + 1


def review_body(review, trace, leftovers, intent, blocked, round_no):
    out = ["### 🦅 Garuda review, round " + str(round_no), "", review.get("summary", "")]
    if leftovers:
        out += ["", "**Findings I couldn't pin to a changed line**"]
        out += ["- **" + c.get("severity", "") + "** `" + str(c.get("file")) + ":" + str(c.get("line")) + "` " +
                c.get("message", "") for c in leftovers]
    if review.get("remembered"):
        out += ["", "**What I remembered**"] + ["- " + r for r in review["remembered"]]
    if intent is None:
        out += ["", "**No intent block found.** Add one to the description so I can check the change "
                    "against what you meant to build:", "", "```intent", "schema: soi/v0",
                "goal: <one line>", "must_hold:", "  - <a rule this change must not break>",
                "permit:", "  paths:", "    - force-app/main/default/classes/<File>.cls", "```"]
    elif blocked:
        out += ["", "**Outside the permit:** " + ", ".join("`" + f + "`" for f in blocked)]
    out += ["", "<details><summary>What I looked at</summary>", "",
            "Discovered " + str(trace.items_discovered) + " items, loaded " + str(trace.items_loaded) +
            " up front (~" + format(trace.tokens_loaded, ",") + " tokens, " +
            str(round(trace.selectivity * 100)) + "% of what I found), fetched ~" +
            format(trace.tokens_fetched, ",") + " more in " + str(trace.fetches) + " tool call(s).",
            "", "</details>", "", "_Reply `/garuda dismiss <why>` on any comment to teach me. "
            "It's saved to `" + DISMISSED_PATH + "` and I won't raise it again._"]
    return "\n".join(out)


def cmd_review(gh, event, client=None):
    from review_agent import review_pr

    pr = event["pull_request"]
    files = gh.paged("/pulls/" + str(pr["number"]) + "/files")
    pr_dir, round_no = build_pr_dir(gh, pr, files, os.environ.get("GITHUB_WORKSPACE", "."))
    review, trace = review_pr(pr_dir, int(os.environ.get("GARUDA_WINDOW", "10000")), client=client,
                              extra_system=REVIEW_INSTRUCTIONS)

    by_file = {f["filename"]: commentable_lines(f.get("patch")) for f in files}
    inline, leftovers = [], []
    for c in review.get("comments", []):
        path = str(c.get("file", "")).lstrip("/")
        path = next((f for f in by_file if f == path or f.endswith("/" + path)), path)
        line = snap(int(c.get("line") or 0), *by_file[path]) if path in by_file else None
        if line is None:
            leftovers.append(c)
            continue
        meta = {"file": os.path.basename(path), "title": c.get("title") or c.get("message", "")[:60],
                "severity": c.get("severity"), "round": round_no}
        body = ("**" + str(c.get("severity", "")).upper() + ": " + meta["title"] + "**\n\n" + c.get("message", "") +
                ("\n\n**Fix:** " + c["fix"] if c.get("fix") else "") +
                "\n\n" + MARKER + json.dumps(meta) + " -->")
        inline.append({"path": path, "line": line, "side": "RIGHT", "body": body})

    intent = parse_intent(pr.get("body"))
    blocked = outside_permit([f["filename"] for f in files], intent) if intent else []
    payload = {"commit_id": pr["head"]["sha"], "event": "COMMENT", "comments": inline,
               "body": review_body(review, trace, leftovers, intent, blocked, round_no)}
    gh.call("POST", "/pulls/" + str(pr["number"]) + "/reviews", payload)
    logger.info("Posted review round %d: %d inline comment(s), %d in the summary", round_no, len(inline), len(leftovers))
    return payload


# ---------------------------------------------------------------------------
# permit
# ---------------------------------------------------------------------------

def cmd_permit(gh, event):
    pr = event["pull_request"]
    intent = parse_intent(pr.get("body"))
    if intent is None:
        print("No ```intent block in the PR description. Nothing to check yet.")
        return 0
    files = [f["filename"] for f in gh.paged("/pulls/" + str(pr["number"]) + "/files")]
    blocked = outside_permit(files, intent)
    print("Intent: " + str(intent.get("goal", "")))
    for f in files:
        print(("  BLOCKED  " if f in blocked else "  ok       ") + f)
    if blocked:
        print("::error title=Outside the permit::This PR touches " + ", ".join(blocked) +
              ", which its intent does not permit. Widen the permit (and get it approved) or move the change.")
        return 1
    return 0


# ---------------------------------------------------------------------------
# Episodic memory, part 2: learn from "/garuda dismiss <why>"
# ---------------------------------------------------------------------------

def cmd_learn(gh, event):
    comment, pr = event["comment"], event["pull_request"]
    reason = comment["body"].strip()[len("/garuda dismiss"):].strip() or "no reason given"
    reply_to = comment.get("in_reply_to_id")

    def reply(text):
        gh.call("POST", "/pulls/" + str(pr["number"]) + "/comments/" + str(reply_to or comment["id"]) + "/replies",
                {"body": text})

    if comment.get("author_association") not in TRUSTED:
        reply("Only repo collaborators can change my memory. Ignoring this one.")
        return 0
    parent = gh.call("GET", "/pulls/comments/" + str(reply_to)) if reply_to else None
    meta = finding_meta(parent["body"]) if parent else None
    if not meta:
        reply("Reply with `/garuda dismiss <why>` directly on one of my review comments, so I know which finding you mean.")
        return 0

    # Saved on the PR branch: the lesson merges with the code it came from, and can be reviewed like code
    branch, who = pr["head"]["ref"], comment["user"]["login"]
    entry = ("- " + meta["file"] + ': "' + meta["title"] + '" was dismissed on PR #' + str(pr["number"]) +
             " by @" + who + ". " + reason.rstrip(".") + ".")
    text, sha = gh.read_file(DISMISSED_PATH, branch)
    if entry in text:
        reply("I already have this one in memory.")
        return 0
    text = (text or "# Dismissed findings (Garuda memory)\n").rstrip("\n") + "\n" + entry + "\n"
    commit = gh.write_file(DISMISSED_PATH, branch, text, sha, "garuda: remember dismissed finding on PR #" + str(pr["number"]))

    # The same lesson as an episode, in the format garuda_memory.recall reads
    episodes, episodes_sha = gh.read_file(EPISODES_PATH, branch)
    episode = {"date": datetime.date.today().isoformat(), "pr": pr["number"], "file": meta["file"],
               "label": "dismissed", "what": 'Garuda said "' + meta["title"] + '"', "error": "",
               "fix": "Dismissed by @" + who + ": " + reason, "outcome": "Do not raise again",
               "comment": parent["html_url"]}
    gh.write_file(EPISODES_PATH, branch, episodes + json.dumps(episode) + "\n", episodes_sha,
                  "garuda: episode for PR #" + str(pr["number"]))

    reply("Got it. Saved to `" + DISMISSED_PATH + "` in " + commit[:7] +
          ", so I won't raise this again on this repo. It merges with this PR, and you can revert it like any other line.")
    gh.call("POST", "/pulls/comments/" + str(comment["id"]) + "/reactions", {"content": "+1"})
    logger.info("Learned: %s", entry)
    return 0


def main():
    logging.basicConfig(level=logging.INFO, format="  %(levelname)-7s %(message)s")
    mode = sys.argv[1] if len(sys.argv) > 1 else "review"
    with open(os.environ["GITHUB_EVENT_PATH"]) as f:
        event = json.load(f)
    gh = GitHub(os.environ["GITHUB_TOKEN"], os.environ["GITHUB_REPOSITORY"])
    if mode == "review":
        cmd_review(gh, event)
        return 0
    if mode == "permit":
        return cmd_permit(gh, event)
    if mode == "learn":
        return cmd_learn(gh, event)
    print("Unknown mode: " + mode)
    return 2


if __name__ == "__main__":
    sys.exit(main())
