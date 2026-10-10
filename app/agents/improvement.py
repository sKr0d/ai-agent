from langchain_core.tools import tool

from app.agents.base import build_worker

IMPROVER_PROMPT = (
    "You are the IMPROVEMENT sub-agent in a multi-agent dev platform. "
    "Turn monitoring findings into concrete, testable changes by calling your "
    "tools. Never merge anything automatically; propose changes and gate them "
    "behind a pull request and human approval."
)


@tool
def propose_improvement(area: str) -> str:
    """Propose a concrete, testable improvement for AREA based on monitoring findings.
    STUB: generate a patch/PR instead of applying it."""
    return f"[improver-stub] proposed improvement for {area}: add retry + alert on failures"


@tool
def apply_improvement(change: str) -> str:
    """Apply CHANGE. STUB: gate behind a pull request + human approval; never auto-merge."""
    return f"[improver-stub] {change} staged (dry-run: not merged)"


def build_improver_agent():
    """The improvement sub-agent: findings -> safe, reviewed changes."""
    return build_worker(prompt=IMPROVER_PROMPT, tools=[propose_improvement, apply_improvement])
