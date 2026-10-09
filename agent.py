# garuda/agent.py — Garuda v1, the agentic way
import anthropic
import json


def review_diff(diff: str, context: str = "") -> dict:
    """Perception -> Reasoning -> Action.

    Perception: the diff text (+ optional context)
    Reasoning:  Claude reads the diff and looks for SOQL injection
    Action:     structured review output
    """
    client = anthropic.Anthropic()

    # --- PERCEPTION: assemble what the agent sees ---
    system = """You are Garuda, an expert Salesforce code reviewer.
Your only job right now: find SOQL injection in Apex code.
SOQL injection = user-controlled input reaching a dynamic query
(Database.query, Database.countQuery, Search.query) without binding
or String.escapeSingleQuotes.
Respond with JSON only: {"summary": "...", "comments": [
  {"file": "...", "line": ..., "severity": "...", "message": "...", "code": "..."}
]}"""

    user_msg = f"## Diff:\n```diff\n{diff}\n```"
    if context:
        user_msg += f"\n\n## Context:\n{context}"

    # --- REASONING: Claude analyzes ---
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )

    # --- ACTION: parse structured output ---
    text = response.content[0].text
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    return json.loads(text)
