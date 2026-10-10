from langchain_core.tools import tool

from app.agents.base import build_worker

CODING_PROMPT = (
    "You are the CODING sub-agent in a multi-agent dev platform. "
    "Draft code and run tests by calling your tools, and ground your answer in "
    "what the tools return. Always run_tests before claiming a change works."
)


@tool
def write_code(language: str, description: str) -> str:
    """Draft code in LANGUAGE that addresses DESCRIPTION.
    STUB: wire to a sandboxed code-execution service (e.g. an ephemeral build pod)."""
    return f"[coding-stub] drafted {language} for: {description}"


@tool
def run_tests(target: str) -> str:
    """Run the test suite for TARGET and return a pass/fail summary.
    STUB: wire to your CI test runner or a build pod."""
    return f"[coding-stub] tests for {target}: 12 passed, 0 failed"


def build_coding_agent():
    """The coding sub-agent: reasons and uses coding tools in a loop."""
    return build_worker(prompt=CODING_PROMPT, tools=[write_code, run_tests])
