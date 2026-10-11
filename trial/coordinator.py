"""The trial's coordinator.

Run it with:  python -m trial.coordinator

It drives coding -> cicd -> monitoring -> improvement, routing each agent's REAL
output to the next, and writes two review docs at the repo root:
  - Hello-World-out.md : the full agent<->coordinator conversation
  - Hello-World.md     : a human-readable overview of the project

The site is deployed to Kubernetes. The CI/CD agent owns the deploy (build +
apply + rollout). To let the monitoring agent reach the in-cluster Service over
HTTP, the coordinator opens a `kubectl port-forward` for the lifetime of the
health check.
"""

import os
import re
import signal
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from trial.agents import cicd, coding, improvement, monitoring

ROOT = Path(__file__).resolve().parents[1]          # repo root
HW_DIR = ROOT / "trial" / "helloworld"              # where the site is built
PORT = 8081                                         # local port for the port-forward
IMAGE = "helloworld-nginx"
APP = "helloworld"
NAMESPACE = "helloworld"


def brief() -> dict:
    """The task handed to the team, plus the concrete params the coordinator
    decides and passes to each agent (that coordination is the job here)."""
    return {
        "goal": ("Build the simplest possible Hello World website, deployed on "
                 "Kubernetes in an nginx container."),
        "port": PORT,
        "image": IMAGE,
        "app": APP,
        "namespace": NAMESPACE,
    }


# ---------- port-forward lifecycle (platform responsibility) ------------------
def _kill_stale_portforward() -> None:
    """Best-effort: clear a port-forward from a previous trial run on this port."""
    subprocess.run(["pkill", "-f", f"port-forward -n {NAMESPACE}"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)


def _start_portforward(namespace: str, app: str, local_port: int) -> subprocess.Popen:
    return subprocess.Popen(
        ["kubectl", "port-forward", "-n", namespace, f"svc/{app}", f"{local_port}:80"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _stop_proc(p: subprocess.Popen | None) -> None:
    if p is None:
        return
    try:
        os.killpg(os.getpgid(p.pid), signal.SIGTERM)
    except Exception:
        pass


def _wait_reachable(url: str, attempts: int = 20, delay: float = 1.0) -> bool:
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                if 200 <= getattr(r, "status", 200) < 300:
                    return True
        except Exception:
            time.sleep(delay)
    return False


# ---------- transcript rendering ---------------------------------------------
def truncate(text: str, limit: int = 1500) -> str:
    text = _as_text(text).strip()
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated {len(text) - limit} chars]"


def _as_text(obj) -> str:
    """Coerce a message's .content to text (it may be a str or content blocks)."""
    return obj if isinstance(obj, str) else str(obj)


def one_line(text: str, limit: int = 100) -> str:
    """Collapse a multi-line agent report to a single table cell for the
    overview. Full detail lives in Hello-World-out.md."""
    for ln in _as_text(text).splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        s = s.lstrip("0123456789.-*_").replace("*", "").strip()
        s = re.sub(r"\s+", " ", s)
        return s if len(s) <= limit else s[:limit] + "…"
    return "(no summary)"


def render(messages, role: str) -> str:
    """Render one agent's message list into a readable transcript block."""
    lines = [f"## {role} agent", ""]
    for m in messages:
        t = getattr(m, "type", "unknown")
        if t == "human":
            lines.append(_human(m))
        elif t == "ai" and getattr(m, "tool_calls", None):
            lines.append(_ai_plan(m))
        elif t == "tool":
            lines.append(_tool(m))
        elif t == "ai":
            lines.append(_ai_final(m))
    lines.append("")
    return "\n".join(lines)


def _human(m) -> str:
    return "**Task from coordinator:**\n\n```\n" + _as_text(m.content).strip() + "\n```\n"


def _ai_plan(m) -> str:
    calls = ", ".join(_tool_summary(tc) for tc in m.tool_calls)
    return f"**Agent plans to call:** `{calls}`\n"


def _tool_summary(tc) -> str:
    if isinstance(tc, dict):
        return f"{tc.get('name', '?')}({tc.get('args', {})})"
    return str(tc)


def _tool(m) -> str:
    return f"**Tool `{getattr(m, 'name', 'tool')}` returned:**\n\n```\n" + \
        truncate(m.content) + "\n```\n"


def _ai_final(m) -> str:
    return f"**Report to coordinator:**\n\n{_as_text(m.content).strip()}\n"


# ---------- the run ----------------------------------------------------------
def run() -> tuple[str, dict]:
    """Run all four agents in sequence and return (transcript, facts)."""
    b = brief()
    facts = {"goal": b["goal"], "port": b["port"], "image": b["image"],
             "app": b["app"], "namespace": b["namespace"]}

    # 1) CODING ---------------------------------------------------------------
    task_coding = (
        "Coding task: write exactly two project files using write_file, using "
        "these exact paths (no 'helloworld/' prefix):\n"
        "  1) write_file(path='index.html', ...) — a minimal HTML page whose "
        "visible text contains 'Hello World'.\n"
        "  2) write_file(path='Dockerfile', ...) — EXACTLY these two lines:\n"
        "       FROM nginx:latest\n"
        "       COPY index.html /usr/share/nginx/html/index.html\n"
        "Then report the two file names and their contents."
    )
    r_coding = coding.run(task_coding)
    facts["coding"] = r_coding

    # 2) CI/CD — the coding artifacts are handed to the CI/CD job --------------
    task_cicd = (
        f"CI/CD task: deploy the hello-world site to Kubernetes with deploy_to_k8s "
        f"using its DEFAULT args. It builds the '{IMAGE}' image from "
        f"trial/helloworld, creates namespace '{NAMESPACE}', and deploys a "
        "Deployment + Service. Report what got deployed and how to reach it."
    )
    r_cicd = cicd.run(task_cicd)
    facts["cicd"] = r_cicd

    # 3) MONITORING — open a port-forward for the HTTP probe; the agent also
    #    reads the pod LOGS and queries k8s METRICS directly.
    task_monitor = (
        f"Monitoring task for the deployment '{APP}' in namespace '{NAMESPACE}'. "
        "Monitor it three ways and correlate them:\n"
        f"  1. http_get at http://127.0.0.1:{b['port']}/ (a platform port-forward) — "
        "expect 200 with 'Hello World' in the body.\n"
        f"  2. kubectl_logs for app='{APP}' in namespace '{NAMESPACE}' — read the recent "
        "logs and report its ANOMALY SUMMARY (any 4xx/5xx responses or [error] lines).\n"
        f"  3. query_metrics for app='{APP}' in namespace '{NAMESPACE}' — pod phase, "
        "restart count, and readiness.\n\n"
        "Report ONE verdict — PASS, DEGRADED (HTTP 200 but log anomalies / restarts "
        "present), or FAIL (HTTP not 200 or no pods) — plus the specific evidence. "
        "Ground every claim in the tool output."
    )
    pf = None
    try:
        _kill_stale_portforward()
        pf = _start_portforward(b["namespace"], b["app"], b["port"])
        _wait_reachable(f"http://127.0.0.1:{b['port']}/")  # preflight; http_get also retries
        r_monitor = monitoring.run(task_monitor)
    finally:
        _stop_proc(pf)
    facts["monitor"] = r_monitor

    # 4) IMPROVEMENT — the verdict is handed to the improver -------------------
    task_improve = (
        "Improvement task: here is what happened — the coding agent wrote "
        "index.html and Dockerfile; the CI/CD agent deployed them to Kubernetes "
        f"as a Deployment + Service in namespace '{NAMESPACE}'; and the "
        f"monitoring agent produced a health verdict and cited these findings: "
        f"{r_monitor['report'].strip()}\n\n"
        "Propose exactly 3 concrete, prioritized improvements for this Hello World "
        "nginx service on Kubernetes, addressing any anomaly the monitoring agent "
        "found (e.g. 4xx/5xx log lines or restarts) plus safety/ops hardening. "
        "One line each, most important first."
    )
    r_improve = improvement.run(task_improve)
    facts["improve"] = r_improve

    # normalize reports to text for the synthesis and overview below
    for r in (r_coding, r_cicd, r_monitor, r_improve):
        r["report"] = _as_text(r["report"])

    transcript = ("Hello-World Trial (on Kubernetes) — agent conversation\n"
                  "======================================================\n\n")
    transcript += (f"Coordinator goal: {b['goal']}\n"
                   f"Coordinator fixed params: image='{IMAGE}', app='{APP}', "
                   f"namespace='{NAMESPACE}', local port-forward={b['port']}\n\n")
    transcript += render(r_coding["messages"], "CODING")
    transcript += render(r_cicd["messages"], "CI/CD")
    transcript += render(r_monitor["messages"], "MONITORING")
    transcript += render(r_improve["messages"], "IMPROVEMENT")

    synthesis = (
        "## Coordinator synthesis\n\n"
        "The coordinator received reports from all four agents and closed the loop:\n"
        f"- **coding** reported: {r_coding['report'].strip()}\n"
        f"- **cicd** reported: {r_cicd['report'].strip()}\n"
        f"- **monitoring** reported: {r_monitor['report'].strip()}\n"
        f"- **improvement** reported: "
        f"{re.sub(r'\n+', '\n', r_improve['report'].strip())}\n"
    )
    transcript += "\n" + synthesis

    facts["transcript"] = transcript
    return transcript, facts


def write_overview(facts: dict) -> None:
    """Write the human-readable project overview from real facts on disk."""
    html_txt = (HW_DIR / "index.html").read_text() if (HW_DIR / "index.html").exists() else "(missing)"
    docker_txt = (HW_DIR / "Dockerfile").read_text() if (HW_DIR / "Dockerfile").exists() else "(missing)"
    k8s_txt = (HW_DIR / "k8s.yaml").read_text() if (HW_DIR / "k8s.yaml").exists() else "(missing)"
    monitor = facts.get("monitor", {})

    overview = f"""# Hello-World on Kubernetes — project overview

A trial of the multi-agent coding environment: build the simplest possible
**Hello World** website and **deploy it to Kubernetes** in an **nginx** container.

## What was built

- **Artifacts:** `trial/helloworld/index.html`, `Dockerfile`, `k8s.yaml`
  - `index.html` — a minimal page showing "Hello World"
  - `Dockerfile` — an nginx image that serves `index.html`
  - `k8s.yaml` — a `Deployment` + `Service`
- **Image:** `{facts['image']}` (served by `nginx:latest`)
- **Kubernetes:** `Deployment` + `Service` named **{facts['app']}** in namespace **{facts['namespace']}**
- **Browse:** `kubectl -n {facts['namespace']} port-forward svc/{facts['app']} {facts['port']}:80`,
  then open http://127.0.0.1:{facts['port']}/

## The team (each reported back to the coordinator)

| Agent        | Job                                            | Outcome (one line)                       |
|--------------|------------------------------------------------|------------------------------------------|
| Coding       | write `index.html` + `Dockerfile`              | {one_line(facts['coding']['report'])}    |
| CI/CD        | build image + deploy to Kubernetes             | {one_line(facts['cicd']['report'])}      |
| Monitoring   | monitor logs + metrics + HTTP (in-cluster)     | {one_line(monitor['report'])}            |
| Improvement  | propose k8s fixes from the monitoring verdict  | {one_line(facts['improve']['report'])}   |

## Artifacts on disk

### index.html
```html
{html_txt}
```

### Dockerfile
```dockerfile
{docker_txt}
```

### k8s.yaml
```yaml
{k8s_txt}
```

## How to reproduce

```bash
# run the whole trial again (all four agents, deploys to the cluster)
python -m trial.coordinator

# or deploy by hand:
kubectl apply -f trial/helloworld/k8s.yaml
kubectl -n {facts['namespace']} rollout status deployment/{facts['app']}
kubectl -n {facts['namespace']} port-forward svc/{facts['app']} {facts['port']}:80
curl -s http://127.0.0.1:{facts['port']}/
```

## Currently running?

The CI/CD agent left a **Kubernetes Deployment** in namespace **`{facts['namespace']}`**
(inspect with `kubectl -n {facts['namespace']} get all`).
Tear it down with `kubectl delete namespace {facts['namespace']}`.
The full agent conversation is in `Hello-World-out.md`.
"""
    (ROOT / "Hello-World.md").write_text(overview.strip() + "\n")


if __name__ == "__main__":
    print("Running Hello-World trial on Kubernetes through the multi-agent team...\n")
    transcript, facts = run()
    (ROOT / "Hello-World-out.md").write_text(transcript + "\n")
    write_overview(facts)
    print(transcript)
    print(f"\nWrote {ROOT/'Hello-World-out.md'} and {ROOT/'Hello-World.md'}")
    print(f"Deployment '{facts['app']}' is running in namespace "
          f"'{facts['namespace']}':  kubectl -n {facts['namespace']} get all  "
          f"(teardown: kubectl delete namespace {facts['namespace']})")
