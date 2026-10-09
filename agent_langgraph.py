# garuda/agent_langgraph.py — Garuda v1 with LangGraph
from typing import TypedDict

from langchain_anthropic import ChatAnthropic
from langgraph.graph import END, START, StateGraph

from prompt import SYSTEM_PROMPT, Review, build_user_msg


class GarudaState(TypedDict, total=False):
    diff: str
    context: str
    user_msg: str
    review: Review
    output: dict


# --- PERCEPTION node: assemble what the agent sees ---
def perceive(state: GarudaState) -> GarudaState:
    return {"user_msg": build_user_msg(state["diff"], state.get("context", ""))}


# --- REASONING node: Claude analyzes, returns a typed Review ---
def reason(state: GarudaState) -> GarudaState:
    llm = ChatAnthropic(model="claude-sonnet-4-6", max_tokens=2048)
    review = llm.with_structured_output(Review).invoke(
        [("system", SYSTEM_PROMPT), ("user", state["user_msg"])]
    )
    return {"review": review}


# --- ACTION node: turn the review into the output ---
def act(state: GarudaState) -> GarudaState:
    return {"output": state["review"].model_dump()}


# The graph IS the control flow: perceive -> reason -> act
graph = StateGraph(GarudaState)
graph.add_node("perceive", perceive)
graph.add_node("reason", reason)
graph.add_node("act", act)
graph.add_edge(START, "perceive")
graph.add_edge("perceive", "reason")
graph.add_edge("reason", "act")
graph.add_edge("act", END)
garuda = graph.compile()


def review_diff(diff: str, context: str = "") -> dict:
    return garuda.invoke({"diff": diff, "context": context})["output"]
