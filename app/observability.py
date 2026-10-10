"""Lightweight observability scaffold.

Two things a monitoring agent needs to consume:
  1. structured (JSON) logs
  2. a per-request run log (who handled it, status, latency)

The in-memory ring buffer here is fine for one process. In Kubernetes, swap the
deque for Redis/Postgres (durable, shared across pods) and ship logs + metrics to
an OTel collector / Grafana stack. That is the concrete bridge from "run" to
"monitor".
"""

import datetime
import json
import logging
import sys
import threading
from collections import deque

_lock = threading.Lock()
_runs: deque = deque(maxlen=200)


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def setup_logging(level: str = "info") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(getattr(logging, str(level).upper(), logging.INFO))


def record_run(thread_id: str, agent: str, status: str, latency_ms: int) -> None:
    """Append a run record. TODO(k8s): push to Redis/OTel instead of the deque."""
    entry = {
        "thread_id": thread_id,
        "agent": agent,
        "status": status,
        "latency_ms": latency_ms,
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    with _lock:
        _runs.append(entry)
    logging.getLogger("agent.observability").info(
        "run recorded",
        extra={"thread_id": thread_id, "agent": agent, "status": status,
               "latency_ms": latency_ms},
    )


def recent_runs(n: int = 20) -> list:
    with _lock:
        return list(_runs)[-n:]
