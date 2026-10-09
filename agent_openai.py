# garuda/agent_openai.py — Garuda v1 with the OpenAI Agents SDK
from agents import Agent, Runner

from prompt import SYSTEM_PROMPT, Review, build_user_msg


def review_diff(diff: str, context: str = "") -> dict:
    """Perception -> Reasoning -> Action.

    Perception: the diff text (+ optional context)
    Reasoning:  the Agent reads the diff and looks for SOQL injection
    Action:     structured review output (the SDK validates it as a Review)
    """

    # --- PERCEPTION: assemble what the agent sees ---
    user_msg = build_user_msg(diff, context)

    # --- REASONING: an Agent with instructions and a typed output ---
    garuda = Agent(
        name="Garuda",
        instructions=SYSTEM_PROMPT,
        output_type=Review,
        # model="...",  # uses the SDK's default OpenAI model unless you set one
    )
    result = Runner.run_sync(garuda, user_msg)

    # --- ACTION: structured output, no JSON parsing needed ---
    return result.final_output.model_dump()
