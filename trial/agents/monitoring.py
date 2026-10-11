"""MONITORING agent — the "error monitoring" agent of the platform.

It watches a running deployment three ways:
  1. http_get      — a live HTTP liveness/health probe against the Service.
  2. kubectl_logs  — reads the pod's recent stdout/stderr logs and flags
                     anomalies (HTTP 4xx/5xx responses and [error]/[warn] lines).
  3. query_metrics — reads real Kubernetes operational health (pod phase,
                     restart count, readiness) WITHOUT a metrics server, by
                     reading pod state directly with kubectl.

In a production system these come from a probe, an OTel/Prometheus collector,
and a scrape of /metrics; here they are derived directly from the cluster so the
capability is real but dependency-free. The agent correlates all three into one
verdict (PASS / DEGRADED / FAIL) for the coordinator and improvement agent.
"""

import json
import re
import subprocess
import time
import urllib.error
import urllib.request

from langchain.agents import create_agent
from langchain_core.tools import tool

from app.llm import get_llm

NS = "helloworld"
APP = "helloworld"


def _kubectl(*args, timeout=60) -> tuple[bool, str]:
    p = subprocess.run(["kubectl", *args], capture_output=True, text=True,
                       timeout=timeout)
    return p.returncode == 0, p.stdout + p.stderr


@tool
def http_get(url: str = "http://127.0.0.1:8081/", retries: int = 5) -> str:
    """HTTP GET a URL and return 'HTTP <status>' plus the body. Retries a few
    times so a still-starting server does not cause a false negative."""
    last = "unknown error"
    for _ in range(retries):
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


@tool
def kubectl_logs(namespace: str = NS, app: str = APP, tail: int = 100) -> str:
    """Read the recent stdout/stderr LOGS of every pod matching app=<app> in
    `namespace` (last `tail` lines). Also returns an ANOMALY SUMMARY that flags
    real faults — HTTP 5xx and [error]/[crit]/[alert] lines — while suppressing
    benign 4xx / "no such file" noise. This is the error-monitoring signal; in
    production it would stream from an OTel/Loki collector."""
    ok, out = _kubectl("logs", "-n", namespace, "-l", f"app={app}",
                       f"--tail={tail}")
    if not ok:
        return f"LOG READ FAILED: {out.strip()[-800:]}"
    lines = [l for l in out.splitlines() if l.strip()]
    # Improvement #1 (from the improvement agent): alert on REAL faults only.
    #   severity = HTTP 5xx, or [error]/[crit]/[alert] log lines.
    #   benign   = 4xx responses + "no such file" 404 noise, which would flip a
    #              static hello-world to DEGRADED for no real reason.
    severity_re = re.compile(r" 5\d\d |\[(error|crit|alert)\]")
    benign_re = re.compile(r"No such file or directory| 4\d\d ")
    anomalies = [l for l in lines if severity_re.search(l) and not benign_re.search(l)]
    suppressed = [l for l in lines if severity_re.search(l) and benign_re.search(l)]
    head = "\n".join(lines) if lines else "(no log output)"
    summary = "\n".join(anomalies[:15]) if anomalies else "none"
    return (f"LOGS for {namespace}/{app} (last {len(lines)} of ~{tail} lines):\n"
            f"{head}\n\n--- ANOMALY SUMMARY (5xx / real [error]; benign 404s excluded) ---\n"
            f"{len(anomalies)} real-fault line(s), {len(suppressed)} benign 404 line(s) suppressed:\n"
            f"{summary}")


@tool
def query_metrics(namespace: str = NS, app: str = APP) -> str:
    """Query real Kubernetes operational metrics for app=<app> in `namespace`:
    pod phase, restart count, and readiness. Derived from `kubectl get pods -o
    json` so it needs NO metrics server. In production these come from
    Prometheus/OTel; here we read pod state directly."""
    ok, out = _kubectl("get", "pods", "-n", namespace, "-l", f"app={app}",
                       "-o", "json")
    if not ok:
        return f"METRICS QUERY FAILED: {out.strip()[-800:]}"
    try:
        data = json.loads(out or "{}")
        pods = data.get("items", []) if isinstance(data, dict) else []
    except Exception:
        return "METRICS PARSE FAILED: could not parse pod JSON"
    detail, total_restarts = [], 0
    for po in pods:
        name = po.get("metadata", {}).get("name", "?")
        phase = po.get("status", {}).get("phase", "?")
        ready = any(cs.get("ready") for cs in
                    po.get("status", {}).get("containerStatuses", []))
        restarts = sum(cs.get("restartCount", 0) for cs in
                       po.get("status", {}).get("containerStatuses", []))
        total_restarts += restarts
        detail.append(f"  {name}: phase={phase} restarts={restarts} ready={ready}")
    health = "healthy" if total_restarts == 0 else "RESTARTS DETECTED"
    return (f"METRICS for {namespace}/{app}:\n"
            + ("\n".join(detail) if detail else "  (no matching pods)") +
            f"\n\nTotal restarts: {total_restarts} -> {health}")


SYSTEM = (
    "You are the MONITORING / error-monitoring agent. You watch a running "
    "deployment three ways and correlate them:\n"
    "  1. http_get(url)                 — live HTTP health probe "
    "(expect 200 + 'Hello World' in the body).\n"
    "  2. kubectl_logs(namespace, app, tail) — read pod logs; include its "
    "ANOMALY SUMMARY (4xx/5xx or [error]/[warn] lines).\n"
    "  3. query_metrics(namespace, app) — pod phase, restart count, readiness.\n\n"
    "The default namespace/app are pre-set to the target deployment. Run all "
    "three, then produce ONE verdict: PASS, DEGRADED (HTTP is 200 but you found "
    "log anomalies or restarts), or FAIL (HTTP not 200 or no pods). Cite the "
    "specific evidence (status code, restarts, and any 4xx/5xx or [error] lines). "
    "Ground every claim in the tool output; do not guess."
)

AGENT = create_agent(model=get_llm(), tools=[http_get, kubectl_logs, query_metrics],
                    system_prompt=SYSTEM)


def run(task: str):
    res = AGENT.invoke(
        {"messages": [{"role": "user", "content": task}]},
        config={"recursion_limit": 50},
    )
    msgs = res["messages"]
    return {"messages": list(msgs), "report": msgs[-1].content}
