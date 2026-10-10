"""The orchestrator: a supervisor that routes work to specialist sub-agents.

Pattern: LangChain "subagents" — each specialist is a `create_agent` graph,
exposed to the orchestrator as a tool. The orchestrator reads the request,
delegates to the ONE agent whose name fits best, and answers from that agent's
result. Memory is per-thread via a `MemorySaver` checkpointer, so repeated calls
with the same `thread_id` keep a conversation (swap to Redis/Postgres for k8s).
"""

from langchain.agents import create_agent
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver

from app.agents.cicd import build_cicd_agent
from app.agents.coding import build_coding_agent
from app.agents.improvement import build_improver_agent
from app.agents.monitoring import build_monitor_agent
from app.llm import get_llm

ORCHESTRATOR_PROMPT = (
    "You orchestrate a small AI dev platform that resembles a Kubernetes "
    "multi-agent environment. Four specialist sub-agents are available as tools:\n"
    "  - ask_coding: write code and run tests.\n"
    "  - ask_cicd: run CI/CD pipelines and deploy release channels.\n"
    "  - ask_monitoring: query metrics, fetch logs, check service health.\n"
    "  - ask_improvement: turn monitoring findings into safe, testable changes.\n\n"
    "Read the request, delegate to the ONE specialist whose name best fits it by "
    "calling that tool, then answer using the specialist's returned result. Do "
    "not attempt the work yourself. Keep your answer concise."
)

# Each specialist is built once. They share the cached LLM (see app/llm.py) and
# stay stateless between calls (per-invocation), which is the recommended default
# for multi-agent systems where sub-agents handle independent requests.
_coding = build_coding_agent()
_cicd = build_cicd_agent()
_monitoring = build_monitor_agent()
_improver = build_improver_agent()


def _run(agent, task: str) -> str:
    """Invoke a sub-agent on a task and return its final text answer.

    Done synchronously: when the orchestrator runs via `ainvoke`, LangGraph
    executes this sync tool in a threadpool, so the async HTTP request in
    app/server.py is not blocked.
    """
    result = agent.invoke({"messages": [{"role": "user", "content": task}]})
    return result["messages"][-1].content


@tool
def ask_coding(task: str) -> str:
    """Delegate a coding or testing task: write code, run tests, review a diff."""
    return _run(_coding, task)


@tool
def ask_cicd(task: str) -> str:
    """Delegate a CI/CD task: trigger a pipeline, deploy a release, check a channel."""
    return _run(_cicd, task)


@tool
def ask_monitoring(task: str) -> str:
    """Delegate a monitoring task: query metrics, fetch logs, inspect service health."""
    return _run(_monitoring, task)


@tool
def ask_improvement(task: str) -> str:
    """Delegate an improvement task: propose changes from monitoring findings."""
    return _run(_improver, task)


# Special tool -> the sub-agent that handled it. Used to tag each run for
# observability and to show, in the response, which agent did the work.
SPECIALISTS = {
    "ask_coding": "coding",
    "ask_cicd": "cicd",
    "ask_monitoring": "monitoring",
    "ask_improvement": "improvement",
}


def detect_agent(messages) -> str:
    """Best-effort: which specialist (if any) ran on this turn."""
    for m in messages:
        for tc in getattr(m, "tool_calls", []) or []:
            name = tc.get("name") if isinstance(tc, dict) else None
            if name in SPECIALISTS:
                return SPECIALISTS[name]
    for m in messages:
        name = getattr(m, "name", None)
        if name in SPECIALISTS:
            return SPECIALISTS[name]
    return "orchestrator"


def build_orchestrator():
    return create_agent(
        model=get_llm(),
        tools=[ask_coding, ask_cicd, ask_monitoring, ask_improvement],
        system_prompt=ORCHESTRATOR_PROMPT,
        checkpointer=MemorySaver(),
    )


# Shared orchestrator instance. A single checkpointer + per-request thread_id is
# enough for concurrent conversations in one process.
orchestrator = build_orchestrator()
