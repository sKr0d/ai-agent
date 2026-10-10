"""Improvement agent: turns the monitoring verdict into concrete next steps.

Pure-reasoning (no external tool) — the 'improvement' job is a judgment call, so
this agent reasons over the facts and returns prioritized suggestions. A real
system would gate these behind a PR + human approval before applying any.
"""

from langchain.agents import create_agent

from app.llm import get_llm

SYSTEM = (
    "You are the IMPROVEMENT agent. You turn what the other agents reported into "
    "concrete, prioritized improvements. Be specific and safe: never suggest "
    "production changes without a test and human approval. Return a short, "
    "numbered list, most important first."
)

# Deliberately no tools: the improvement output is a reasoned list.
AGENT = create_agent(model=get_llm(), tools=[], system_prompt=SYSTEM)


def run(task: str):
    res = AGENT.invoke(
        {"messages": [{"role": "user", "content": task}]},
        config={"recursion_limit": 40},
    )
    msgs = res["messages"]
    return {"messages": list(msgs), "report": msgs[-1].content}
