"""Factory for specialist sub-agents.

`build_worker` wraps the current `langchain.agents.create_agent` API. Every
specialist is created the same way: a model + its own tools + a system prompt.
That uniformity is the point of the multi-agent pattern — it is what lets a new
agent be added by writing one more file and appending one tool.
"""

from langchain.agents import create_agent

from app.llm import get_llm


def build_worker(prompt: str, tools: list):
    """Return a compiled sub-agent graph.

    The returned object is a LangGraph Pregel graph; call it with
    `agent.invoke({"messages": [...]})` / `agent.ainvoke(...)`.
    """
    return create_agent(
        model=get_llm(),
        tools=tools,
        system_prompt=prompt,
    )
