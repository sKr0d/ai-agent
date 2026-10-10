"""Coding agent: writes real project files using a real write_file tool."""

from langchain.agents import create_agent
from langchain_core.tools import tool
from pathlib import Path

from app.llm import get_llm

BASE = Path(__file__).resolve().parents[1] / "helloworld"
BASE.mkdir(parents=True, exist_ok=True)

SYSTEM = (
    "You are the CODING agent on a tiny trial project. You write real source "
    "files to disk using the write_file tool, which is scoped to the project "
    "directory. After writing, report exactly which files you created and their "
    "contents. Be precise; do not invent files you did not write."
)


@tool
def write_file(path: str, content: str) -> str:
    """Create or overwrite a project file. `path` is relative to the project
    root (e.g. "index.html" or "Dockerfile"). Returns the absolute path written
    and a character count. Any leading "helloworld/" is ignored, and attempts to
    escape the project directory are refused."""
    rel = path
    while rel.startswith("helloworld/"):
        rel = rel[len("helloworld/"):]
    target = (BASE / rel).resolve()
    if BASE not in target.parents and target != BASE:
        return f"ERROR: path '{path}' escapes the project directory; refused."
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return f"wrote {target} ({len(content)} chars)"


AGENT = create_agent(model=get_llm(), tools=[write_file], system_prompt=SYSTEM)


def run(task: str):
    res = AGENT.invoke(
        {"messages": [{"role": "user", "content": task}]},
        config={"recursion_limit": 40},
    )
    msgs = res["messages"]
    return {"messages": list(msgs), "report": msgs[-1].content}
