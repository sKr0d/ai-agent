"""Trial agents: real work, real tools (the "wired up" version of app/agents).

Each module builds a `create_agent` sub-agent with a real tool and exposes
`run(task) -> {"messages", "report"}` for the coordinator.
"""

from trial.agents import cicd, coding, improvement, monitoring

__all__ = ["cicd", "coding", "improvement", "monitoring"]
