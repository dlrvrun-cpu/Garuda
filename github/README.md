# Garuda on GitHub

The context engine from `context/`, wired to real pull requests as a GitHub Action.

| Mode | Runs on | What it does |
|---|---|---|
| `review` | `pull_request` | Lays the PR out for the context engine (diff, description, earlier rounds, the checked-out repo), runs `review_agent.review_pr`, and posts one review with inline comments |
| `permit` | `pull_request` | Reads the ```intent block in the PR description and fails if the PR touches files outside `permit.paths` |
| `learn` | `pull_request_review_comment` | On a reply `/garuda dismiss <why>` to one of Garuda's comments, commits the lesson to `.garuda/memory/dismissed-findings.md` and `.garuda/memory/episodes.jsonl` on the PR branch |

Use it from any Salesforce repo: copy [`examples/garuda.yml`](../examples/garuda.yml) to `.github/workflows/` and add an `ANTHROPIC_API_KEY` secret.

## How memory works

- **Working memory:** the context window for one review. Built fresh each run.
- **Episodic memory:** earlier Garuda rounds on the same PR are turned into `review-history.txt`, so semantic compaction keeps the results and decisions. Past failures, fixes and dismissals live in `episodes.jsonl`, and `memory/garuda_memory.py` recalls the ones that match the PR by file and by failure label.
- **Semantic memory:** `repo-conventions.md`, written by people.
- **Intent:** the ```intent block (schema `soi/v0`: goal, must_hold, permit). The review is checked against it, and `permit` enforces it.

Memory is plain files in the repo, saved on the PR branch. A lesson merges with the code it came from, and it can be reviewed and reverted like any other line. Only collaborators can change it.

## Tests

    pip install anthropic pyyaml
    cd github && python -m unittest test_garuda_github.py

A fake GitHub and a fake Claude, with the real context engine and the sample PR.
