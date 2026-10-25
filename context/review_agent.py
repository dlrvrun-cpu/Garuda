# Garuda with eyes: the review agent on top of the context engine.
# Run:  export ANTHROPIC_API_KEY=...
#       python review_agent.py
#  or:  python review_agent.py sample_pr 10000
#
# Perception: ContextSession builds the prompt (discovery, triage, compaction).
# Reasoning:  Claude reviews, and calls read_context / search_context when it needs more.
# Action:     a JSON review, plus the context trace that explains what Garuda saw.

import sys
import json
import logging
import anthropic

from context_engine import ContextSession, TOOLS

MAX_TOOL_ROUNDS = 6
OUTPUT_FORMAT = """
Respond with JSON only: {"summary": "...", "comments": [
  {"file": "...", "line": ..., "severity": "high|medium|low", "message": "...", "fix": "..."}
]}"""


def review_pr(pr_dir, window=10000, client=None):
    client = client or anthropic.Anthropic()
    session = ContextSession(pr_dir, window)
    msgs = session.messages()
    messages = [{"role": "user", "content": msgs["user"]}]

    for _ in range(MAX_TOOL_ROUNDS + 1):
        response = client.messages.create(
            model="claude-sonnet-5-5",
            max_tokens=4096,
            system=msgs["system"] + "\n" + OUTPUT_FORMAT,
            tools=TOOLS,
            messages=messages,
        )
        if response.stop_reason != "tool_use":
            break
        # The model raised its hand: answer every tool call, then let it continue
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for block in response.content:
            if block.type == "tool_use":
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": session.handle_tool_call(block.name, block.input)})
        messages.append({"role": "user", "content": results})

    text = "".join(b.text for b in response.content if b.type == "text")
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    return json.loads(text), session.trace


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="  %(levelname)-7s %(message)s")
    pr_dir = sys.argv[1] if len(sys.argv) > 1 else "sample_pr"
    window = int(sys.argv[2]) if len(sys.argv) > 2 else 10000
    review, trace = review_pr(pr_dir, window)
    print(json.dumps(review, indent=2))
    print("")
    print("Context: ~" + format(trace.tokens_loaded, ",") + " tokens up front, ~" +
          format(trace.tokens_fetched, ",") + " fetched in " + str(trace.fetches) +
          " calls, re-read ratio " + str(round(trace.re_read_ratio * 100)) + "%")
