"""Monitoring agent: checks the live site with a real HTTP GET.

This is the agent that will grow into the error-monitoring service. It performs
a real HTTP request with retries (nginx needs a moment to start) and reports a
PASS/FAIL verdict the coordinator and improvement agent can act on.
"""

import time
import urllib.error
import urllib.request

from langchain.agents import create_agent
from langchain_core.tools import tool

from app.llm import get_llm

SYSTEM = (
    "You are the MONITORING agent. You observe the running system by making real "
    "HTTP requests with the http_get tool. Report a one-word health verdict "
    "(PASS or FAIL), the observed HTTP status code, and a short body snippet. "
    "Ground every claim in the tool output; do not guess."
)


def http_get(url: str = "http://127.0.0.1:8081/", retries: int = 5) -> str:
    """HTTP GET a URL and return 'HTTP <status>' plus the body. Retries a few
    times so a still-starting server does not cause a false negative."""
    last = "unknown error"
    for i in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                body = r.read().decode("utf-8", "replace")
                return f"HTTP {getattr(r, 'status', 200)}\n{body}"
        except urllib.error.HTTPError as e:  # server responded, non-2xx
            return f"HTTP {e.code}\n{e.read().decode('utf-8', 'replace')}"
        except Exception as e:  # connection refused / not ready yet
            last = str(e)
            time.sleep(2)
    return f"UNREACHABLE after {retries} attempts: {last}"


AGENT = create_agent(model=get_llm(), tools=[http_get], system_prompt=SYSTEM)


def run(task: str):
    res = AGENT.invoke(
        {"messages": [{"role": "user", "content": task}]},
        config={"recursion_limit": 40},
    )
    msgs = res["messages"]
    return {"messages": list(msgs), "report": msgs[-1].content}
