from langchain_core.tools import tool

from app.agents.base import build_worker

MONITOR_PROMPT = (
    "You are the MONITORING sub-agent in a multi-agent dev platform. "
    "Surface metrics, logs, and service health by calling your tools, then "
    "report a concise finding. You are the input the improvement agent consumes."
)


@tool
def query_metrics(metric: str) -> str:
    """Query a metric such as 'latency_p99' or 'error_rate' and return a recent value.
    STUB: wire to Prometheus / an OTel collector."""
    return f"[monitor-stub] {metric} ~= baseline (no regression)"


@tool
def fetch_logs(component: str, since: str = "15m") -> str:
    """Fetch recent logs for COMPONENT since SINCE. STUB: wire to Loki / OTel logs."""
    return f"[monitor-stub] no errors in last {since} for {component}"


@tool
def check_health() -> str:
    """Check health of platform services. STUB: wire to k8s /healthz probes."""
    return "[monitor-stub] services: agent=healthy"


def build_monitor_agent():
    """The monitoring sub-agent: metrics, logs, and health checks."""
    return build_worker(
        prompt=MONITOR_PROMPT,
        tools=[query_metrics, fetch_logs, check_health],
    )
