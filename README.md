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

## Episode 2.1: context prioritization and semantic compaction

Two plain Python scripts in [`context/`](context/), with no libraries needed.

```bash
cd context
python context_prioritization.py    # reads context_items.txt, prints the triage and what the model receives
python semantic_compaction.py       # reads conversation.txt, prints the conversation before and after compaction
```

Pass your own text file to either script to try your own PR. See [`context/README.md`](context/README.md) for the input formats.
