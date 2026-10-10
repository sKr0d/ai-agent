"""Multi-dev agent package.

Topology (orchestrator / "subagents" pattern):

    orchestrator (create_agent + MemorySaver)
        ├── ask_coding      -> coding sub-agent     (write code / run tests)
        ├── ask_cicd        -> cicd sub-agent       (pipelines / deploys)
        ├── ask_monitoring  -> monitoring sub-agent (metrics / logs / health)
        └── ask_improvement -> improvement sub-agent (findings -> changes)

Each sub-agent is itself a `create_agent` graph running its own tool loop,
exposed to the orchestrator as a tool. Adding a 5th agent = add a tool.
"""
