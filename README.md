# Garuda

A Salesforce PR review agent, built one episode at a time in the *Tales of AI* series on agentic engineering.

## Version 1: two ways to find SOQL injection

| File | Approach | Shape |
|---|---|---|
| `classic.py` | Plain code with a regex rule | Input → Business logic → Output |
| `agent.py` | An LLM reasons about the diff | Perception → Reasoning → Action |
| `sample.diff` | A tiny Apex change with two SOQL injections (lines 12 and 13) | |

## Run it

```bash
pip install -r requirements.txt

# Classic version (no API key needed)
python -c "import classic; print(classic.review_diff(open('sample.diff').read()))"

# Agentic version
export ANTHROPIC_API_KEY=...
python -c "import agent; print(agent.review_diff(open('sample.diff').read()))"
```
