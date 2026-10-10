"""The trial's coordinator.

Run it with:  python -m trial.coordinator

It drives coding -> cicd -> monitoring -> improvement, routes each agent's real
output to the next, and writes two review docs at the repo root:
  - Hello-World-out.md : the full agent<->coordinator conversation
  - Hello-World.md     : a human-readable overview of the project
"""

import re
from pathlib import Path

from trial.agents import cicd, coding, improvement, monitoring

ROOT = Path(__file__).resolve().parents[1]          # repo root
HW_DIR = ROOT / "trial" / "helloworld"              # where the site is built
PORT = 8081
IMAGE = "helloworld-nginx"
CONTAINER = "helloworld-web"


def brief() -> dict:
    """The task handed to the team, and the concrete params the coordinator
    decides and passes to each agent (that coordination is the job here)."""
    return {
        "goal": "Build the simplest possible Hello World website served by an nginx container.",
        "port": PORT,
        "image": IMAGE,
        "container": CONTAINER,
    }


def truncate(text: str, limit: int = 1500) -> str:
    text = _as_text(text).strip()
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated {len(text) - limit} chars]"


def _as_text(obj) -> str:
    """Coerce a message's .content to text (it may be a str or content blocks)."""
    if isinstance(obj, str):
        return obj
    return str(obj)


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
        name = tc.get("name", "?")
        args = tc.get("args", {})
        return f"{name}({args})"
    return str(tc)


def _tool(m) -> str:
    return f"**Tool `{getattr(m, 'name', 'tool')}` returned:**\n\n```\n" + \
        truncate(m.content) + "\n```\n"


def _ai_final(m) -> str:
    return f"**Report to coordinator:**\n\n{_as_text(m.content).strip()}\n"


def run() -> tuple[str, dict]:
    """Run all four agents in sequence and return (transcript, facts)."""
    b = brief()
    facts = {"goal": b["goal"], "port": b["port"], "image": b["image"],
             "container": b["container"], "steps": []}

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

    # 2) CI/CD — coding handed the real artifacts; cicd builds+runs them -------
    task_cicd = (
        f"CI/CD task: build a Docker image named '{IMAGE}' and run it as a "
        f"detached container named '{CONTAINER}' mapping host port {b['port']} to "
        "container port 80 (nginx). Use build_and_run with its DEFAULT context "
        f"(trial/helloworld) and host_port={b['port']}; do not pass a custom "
        "context_dir. Then report the build result and the URL where the site is "
        "now running."
    )
    r_cicd = cicd.run(task_cicd)
    facts["cicd"] = r_cicd

    # 3) MONITORING — cicd handed the live URL; monitoring checks it -----------
    task_monitor = (
        f"Monitoring task: check the running site at http://127.0.0.1:{b['port']}/ "
        f"using http_get. Confirm the HTTP status is 200 and that the response body "
        "contains 'Hello World'. Report a one-word health verdict (PASS or FAIL) plus "
        "the observed status code and a body snippet."
    )
    r_monitor = monitoring.run(task_monitor)
    facts["monitor"] = r_monitor

    # 4) IMPROVEMENT — monitoring handed its verdict; improver reacts ----------
    task_improve = (
        "Improvement task: here is what happened — the coding agent wrote index.html "
        "and Dockerfile; the CI/CD agent built and ran the image on a host port; "
        f"the monitoring agent's verdict was: {r_monitor['report'].strip()}\n\n"
        "Propose exactly 3 concrete, prioritized improvements for this Hello World "
        "nginx service (safety, ops, or reliability). One line each, most important "
        "first."
    )
    r_improve = improvement.run(task_improve)
    facts["improve"] = r_improve

    # normalize reports to text for the synthesis and overview below
    for r in (r_coding, r_cicd, r_monitor, r_improve):
        r["report"] = _as_text(r["report"])

    # Coordinator synthesis ----------------------------------------------------
    transcript = "Hello-World Trial — agent conversation\n=====================================\n\n"
    transcript += (f"Coordinator goal: {b['goal']}\n"
                   f"Coordinator fixed params: port={b['port']}, "
                   f"image='{IMAGE}', container='{CONTAINER}'\n\n")
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
    html = (HW_DIR / "index.html")
    dockerfile = HW_DIR / "Dockerfile"
    html_txt = html.read_text() if html.exists() else "(missing)"
    docker_txt = dockerfile.read_text() if dockerfile.exists() else "(missing)"
    monitor = facts.get("monitor", {})
    improve = facts.get("improve", {})
    files = [f.name for f in sorted(HW_DIR.glob("*")) if f.suffix not in (".gitkeep",)]

    overview = f"""# Hello-World — project overview

A trial run of the multi-agent coding environment, building the simplest
possible **Hello World** website on an **nginx** container.

## What was built

- **File(s):** {", ".join(files)}
  - `index.html` — a minimal page showing "Hello World"
  - `Dockerfile` — an nginx image that serves `index.html`
- **Image:** `{facts['image']}` (served by `nginx:latest`)
- **Container:** `{facts['container']}` — running on host port **{facts['port']}**
- **Live URL:** http://127.0.0.1:{facts['port']}/

## The team (each reported back to the coordinator)

| Agent        | Job                                        | Outcome (one line)                       |
|--------------|--------------------------------------------|------------------------------------------|
| Coding       | write `index.html` + `Dockerfile`          | {one_line(facts['coding']['report'])}    |
| CI/CD        | `docker build` + `docker run` the image    | {one_line(facts['cicd']['report'])}      |
| Monitoring   | check the live site for "Hello World"      | {one_line(monitor['report'])}            |
| Improvement  | propose fixes from the monitoring verdict  | {one_line(improve['report'])}            |

## Artifacts on disk

### index.html

```html
{html_txt}
```

### Dockerfile

```dockerfile
{docker_txt}
```

## How to reproduce

```bash
# 4a. build and run the container yourself
docker build -t {facts['image']} ./trial/helloworld
docker run -d --name {facts['container']} -p {facts['port']}:80 {facts['image']}

# 4b. browse it
open http://127.0.0.1:{facts['port']}/
curl -s http://127.0.0.1:{facts['port']}/

# 4c. run the whole trial again (all four agents)
python -m trial.coordinator
```

## Currently running?

The CI/CD agent left a running container named **`{facts['container']}`**.
Stop it with: `docker stop {facts['container']}` (image can be removed with
`docker rmi {facts['image']}`). The full agent conversation is in
`Hello-World-out.md`.
"""
    (ROOT / "Hello-World.md").write_text(overview.strip() + "\n")


if __name__ == "__main__":
    print("Running Hello-World trial through the multi-agent team...\n")
    transcript, facts = run()
    (ROOT / "Hello-World-out.md").write_text(transcript + "\n")
    write_overview(facts)
    print(transcript)
    print(f"\nWrote {ROOT/'Hello-World-out.md'} and {ROOT/'Hello-World.md'}")
    print(f"Container '{facts['container']}' is still running -> "
          f"http://127.0.0.1:{facts['port']}/ "
          f"(stop with: docker stop {facts['container']})")
