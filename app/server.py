"""HTTP surface for the multi-dev agent.

Endpoints:
  GET  /        -> service info
  GET  /health  -> liveness (process is up)     -> k8s livenessProbe
  GET  /ready   -> readiness (can we reach the LLM?) -> k8s readinessProbe
  POST /chat    -> run a request through the orchestrator
  GET  /runs    -> recent run log (who handled each request)

The orchestrator is created once at import (see app/orchestrator.py).
"""

import asyncio
import logging
import time
import urllib.request
import uuid

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.config import get_settings
from app.observability import recent_runs, record_run, setup_logging
from app.orchestrator import detect_agent, orchestrator

settings = get_settings()
setup_logging(settings.log_level)
log = logging.getLogger("agent.server")

app = FastAPI(title="Multi-Dev Agent", version="0.1.0")


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None  # pass one to continue a conversation


class ChatResponse(BaseModel):
    response: str
    agent: str
    steps: int
    thread_id: str
    run_id: str


@app.get("/")
def root():
    return {
        "service": "multi-dev-agent",
        "endpoints": ["/health", "/ready", "/chat", "/runs"],
    }


@app.get("/health")
def health():
    """Liveness: the process is up. No external dependencies."""
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    """Readiness: can we reach the LLM endpoint? Maps to a k8s readinessProbe.

    Returns 503 when the LLM is unreachable so the probe meaningfully gates
    traffic (and the error-monitoring agent can consume the 503s).
    """
    ok = await _llm_reachable()
    if not ok:
        raise HTTPException(status_code=503, detail="LLM endpoint unreachable")
    return {"status": "ok", "llm_reachable": True}


async def _llm_reachable() -> bool:
    """A short, non-blocking probe of the chat model's OpenAI-compatible /models."""
    s = get_settings()
    url = s.base_url.rstrip("/") + "/models"

    def _get() -> bool:
        with urllib.request.urlopen(url, timeout=3) as resp:
            return 200 <= getattr(resp, "status", 200) < 300

    try:
        return await asyncio.to_thread(_get)
    except Exception:
        return False


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    thread_id = req.thread_id or str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    start = time.perf_counter()
    log.info("chat start", extra={"thread_id": thread_id, "run_id": run_id})
    try:
        result = await orchestrator.ainvoke(
            {"messages": [{"role": "user", "content": req.message}]},
            config={"configurable": {"thread_id": thread_id}},
        )
        messages = result["messages"]
        agent = detect_agent(messages)
        latency_ms = int((time.perf_counter() - start) * 1000)
        record_run(thread_id, agent, "ok", latency_ms)
        return ChatResponse(
            response=messages[-1].content,
            agent=agent,
            steps=len(messages),
            thread_id=thread_id,
            run_id=run_id,
        )
    except Exception as exc:  # surface as HTTP 500 + structured log for monitoring
        record_run(thread_id, "unknown", f"error:{type(exc).__name__}", 0)
        log.exception("chat failed", extra={"thread_id": thread_id, "run_id": run_id})
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/runs")
def runs(n: int = 20):
    """Recent run log. (In k8s, back this with Redis/Postgres or query OTel.)"""
    return {"runs": recent_runs(n)}
