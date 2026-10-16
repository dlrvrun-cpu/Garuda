# Garuda

A Salesforce PR review agent, built one episode at a time in the *Tales of AI* series on agentic engineering.

## Version 1: find SOQL injection, two ways

| File | Approach | Shape |
|---|---|---|
| `classic.py` | Plain code with a regex rule (no AI) | Input → Business logic → Output |
| `agent.py` | Agent with the **Anthropic SDK** | Perception → Reasoning → Action |
| `agent_openai.py` | Same agent with the **OpenAI Agents SDK** | Perception → Reasoning → Action |
| `agent_langgraph.py` | Same agent with **LangGraph** (each step is a graph node) | perceive → reason → act |
| `prompt.py` | The prompt and output schema the framework versions share | |
| `sample.diff` | A tiny Apex change with two SOQL injections (lines 12 and 13) | |

Every version exposes the same function, `review_diff(diff) -> dict`, and returns the same shape:
`{"summary": ..., "comments": [{"file", "line", "severity", "message", "code"}]}`
(the classic version has no `code` field).

## Run it

```bash
pip install -r requirements.txt
DIFF="open('sample.diff').read()"

# Classic (no API key needed)
python -c "import classic; print(classic.review_diff($DIFF))"

# Anthropic SDK
export ANTHROPIC_API_KEY=...
python -c "import agent; print(agent.review_diff($DIFF))"

# OpenAI Agents SDK (uses the SDK's default OpenAI model)
export OPENAI_API_KEY=...
python -c "import agent_openai; print(agent_openai.review_diff($DIFF))"

# LangGraph (uses Claude through langchain-anthropic)
export ANTHROPIC_API_KEY=...
python -c "import agent_langgraph; print(agent_langgraph.review_diff($DIFF))"
```

The classic version catches line 12 and misses line 13, because `q` was built a line earlier. Try the agents and compare.

## Version 2: perception, deciding what the reviewer sees

v1 passed the raw diff to the model. A real Salesforce PR is mostly XML noise around a few
lines of Apex, so v2 adds a **perception** layer that builds the context window on purpose:
tiered budgets (P0–P3), compression instead of dropping, a reserve for reasoning, a NEVER
tier for secrets, and a trace of every decision. Details: [`perception/README.md`](perception/README.md).

| File | What it is |
|---|---|
| `perception/` | Gather → triage → render → trace (standard library only) |
| `perceive.py` | CLI: build and inspect the context window for a PR |
| `examples/pr482/` | A small SFDX repo + PR diff with five planted problems |
| `tests/test_perception.py` | Asserts every planted problem stays visible, and the key never does |

```bash
python perceive.py                                   # trace report for PR #482
python perceive.py --show                            # exactly what the model would read
python perceive.py --shares 0.10,0.02,0.01 --window 20000   # squeeze it
python perceive.py --review                          # send it to Claude (ANTHROPIC_API_KEY)
python perceive.py --diff my.diff --repo ../my-sfdx-repo     # your own PR
python -m unittest -v                                # 24 tests, no API key needed
```

PR #482 in numbers: naive load **33,148 tokens**, triaged load **2,273 tokens**, and every
planted bug is still visible to the model.
