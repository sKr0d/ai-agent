# Multi-Dev Agent

A learning scaffold for a **multi-agent coding environment** that you will
ultimately run in **Kubernetes**. It runs an orchestrator that routes work to
four specialist sub-agents — **coding**, **CI/CD**, **monitoring**, and
**improvement** — so you can develop the agent layer first (no local k8s
required) and graduate each part to a pod later.

Built on **LangChain v1 `create_agent`** (not the deprecated
`create_react_agent`) and **LangGraph**, talking to **Ollama** through its
OpenAI-compatible endpoint.

```
                 ┌─────────────────────────────┐
   user request   │        orchestrator          │
 ───────────────▶ │  create_agent + MemorySaver   │
 (POST /chat)      │  per-thread conversation      │
                 └──────────────┬─────────────┘
                                │ routes to ONE specialist tool
       ┌───────────────┬────────┴─────────┬────────────────┐
       ▼               ▼                  ▼                ▼
  ┌────────┐      ┌──────────┐      ┌──────────┐    ┌─────────────┐
  │ coding │      │  cicd    │      │monitoring│    │improvement  │
  │ write  │      │pipeline  │      │metrics   │    │findings ->   │
  │ code   │      │deploy    │      │logs/health│   │safe changes  │
  │ run    │      │(safe ch.)│      │          │    │(PR + human)  │
  │ tests  │      └──────────┘      └──────────┘    └─────────────┘
  └────────┘
  each box = its own `create_agent` graph with its own tools + prompt
```

## Design: the "subagents" pattern

The orchestrator is itself an agent. Each specialist is a `create_agent`
graph wrapped as a **tool** for the orchestrator (`ask_coding`, `ask_cicd`,
`ask_monitoring`, `ask_improvement`). The orchestrator picks the specialist
whose name fits the request and answers from that specialist's result.

Why this shape:
- **Adding an agent = adding one tool.** New `app/agents/<name>.py` + one
  `ask_<name>` function. Nothing else changes.
- Each specialist has its own tools, prompt, and reasoning loop — small and testable.
- The sub-agents are **stateless per call** (per-invocation), the recommended
  default for independent sub-agent work. The orchestrator holds the
  conversation via a per-`thread_id` `MemorySaver` checkpointer.
- It maps cleanly to Kubernetes later: each sub-agent becomes its own service,
  and "wrapped as a tool" becomes "a call over the network."

## Prerequisites

- **Ollama** running on the host with the model pulled:

  ```bash
  ollama pull qwen3.8:27b
  ```

- Python 3.10+ (a `.venv/` is provided locally; `.gitignore`d).
- To run the container path: **Docker Desktop** (needed so `host.docker.internal`
  can reach your host's Ollama).

## Quick start (local)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then adjust; LLM_BASE_URL should reach your Ollama
uvicorn app.server:app --reload --port 8000
```

Try it:

```bash
curl -s -X POST localhost:8000/chat \
  -H 'content-type: application/json' \
  -d '{"message":"Deploy the latest build to the staging channel","thread_id":"demo"}'

curl -s localhost:8000/runs    # who handled each request
```

The `thread_id` keeps a conversation; pass the same one to continue it.

## Quick start (container)

```bash
cp .env.example .env
docker compose up --build
```

The container reaches your host's Ollama via `host.docker.internal`
(`extra_hosts` makes this work on Linux too). In k8s you'd instead point
`LLM_BASE_URL` at an Ollama pod/Service, e.g. `http://ollama:11434/v1`.

## Endpoints

| Method | Path     | Purpose                                  | k8s analog         |
|--------|----------|------------------------------------------|--------------------|
| GET    | `/health`| Liveness — process is up                 | livenessProbe      |
| GET    | `/ready` | Readiness — can we reach the LLM?        | readinessProbe     |
| POST   | `/chat`  | Run a request through the orchestrator   | Service            |
| GET    | `/runs`  | Recent run log (agent, status, latency)  | (query OTel later) |

## How to run the whole flow yourself

```python
import asyncio
from app.orchestrator import orchestrator, detect_agent

async def main():
    out = await orchestrator.ainvoke(
        {"messages": [{"role": "user", "content": "Retry a flaky call and run its tests"}]},
        config={"configurable": {"thread_id": "demo"}},
    )
    msgs = out["messages"]
    print(detect_agent(msgs))          # which specialist ran
    print(msgs[-1].content)
asyncio.run(main())
```

## The tools are stubs on purpose

Each specialist's tools (`write_code`, `run_tests`, `trigger_pipeline`,
`deploy_to_k8s`, `query_metrics`, `fetch_logs`, `propose_improvement`, ...)
return canned text and say so. **Wiring them to real infrastructure is the
project.** Suggested targets:

| Stub tool          | Wire to                                   |
|--------------------|-------------------------------------------|
| `write_code`       | an ephemeral build/coding sandbox pod      |
| `run_tests`        | your CI test runner (Actions/Tekton)       |
| `trigger_pipeline` | GitHub Actions / Jenkins / Tekton API      |
| `deploy_to_k8s`    | `kubectl apply` (keep the prod gate!)      |
| `query_metrics`    | Prometheus / an OTel collector             |
| `fetch_logs`       | Loki / OTel logs                           |
| `propose/apply`    | generate a real patch + open a PR          |

The `deploy_to_k8s` and `apply_improvement` stubs already encode a safety rule:
production changes are blocked / gated behind human approval. Keep that.

## Road to Kubernetes (your north star)

1. **State out of the process.** Swap `MemorySaver` for a `RedisSaver` or
   `PostgresSaver`. One checkpointer, shared by every pod, keyed on `thread_id`.
2. **Each sub-agent → its own Service.** Split `app/agents/*` into separate
   deployables that expose an HTTP/gRPC endpoint; the orchestrator "wraps" them
   with a network call instead of an in-process tool.
3. **Probes.** Point k8s `livenessProbe` at `/health`, `readinessProbe` at
   `/ready`. The `HEALTHCHECK` in the Dockerfile already mirrors this.
4. **Secrets.** Move `LLM_API_KEY` etc. from env into a k8s `Secret`.
5. **Observability.** The "monitoring" sub-agent consumes what you emit: enable
   LangSmith/OTel tracing (see `.env.example`) and have it query those traces.
6. **Graduate the router.** The current orchestrator lets the LLM choose a
   tool. A more explicit version is a LangGraph **supervisor** that returns
   `Command(goto=...)` to a named subgraph node — a more observable routing
   decision. See docs: `langchain` *subagents* and *multi-agent supervisor*.

## Layout

```
app/
  config.py          env > yaml > defaults (k8s-style config layering)
  llm.py             cached chat model (Ollama via OpenAI-compatible API)
  observability.py   JSON logs + run log (swap deque -> Redis/OTel in k8s)
  agents/
    base.py          build_worker(): the create_agent factory
    coding.py        coding sub-agent + tools
    cicd.py          CI/CD sub-agent + tools
    monitoring.py    monitoring sub-agent + tools
    improvement.py   improvement sub-agent + tools
  orchestrator.py    the supervisor: wraps sub-agents as tools
  server.py          FastAPI: /health /ready /chat /runs
config/settings.yaml local LLM/logging defaults
requirements.txt     pinned to a validated environment
Dockerfile           non-root build with /health HEALTHCHECK
docker-compose.yml   one-service bridge to k8s
```

`agent.py` is the original single-agent starting point, kept for reference; the
live app is `app.server:app`.
