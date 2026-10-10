"""CI/CD agent: builds and runs the nginx container with real Docker commands."""

import subprocess
from pathlib import Path

from langchain.agents import create_agent
from langchain_core.tools import tool

from app.llm import get_llm

ROOT = Path(__file__).resolve().parents[2]  # repo root, so context_dir is stable

SYSTEM = (
    "You are the CI/CD agent. You build and run containers with the build_and_run "
    "tool (real Docker commands). After running, report the build result and the "
    "URL where the site is now listening. Do not claim success unless the tool "
    "reported the container started."
)


def _sh(cmd) -> tuple[bool, str]:
    p = subprocess.run(list(cmd), capture_output=True, text=True,
                       cwd=str(ROOT), timeout=300)
    ok = p.returncode == 0
    return ok, (p.stdout + p.stderr) or "(no output)"


@tool
def build_and_run(host_port: int = 8081,
                  image_name: str = "helloworld-nginx",
                  container_name: str = "helloworld-web",
                  context_dir: str = "trial/helloworld") -> str:
    """Build a Docker image from context_dir and run it detached, mapping
    host_port -> container 80 (nginx). Idempotent: removes a prior container of
    the same name first. Returns a real summary of the build and run."""
    _sh(["docker", "rm", "-f", container_name])  # idempotency; ignore errors
    ok_b, out_b = _sh(["docker", "build", "-t", image_name, context_dir])
    if not ok_b:
        return f"BUILD FAILED (context {context_dir}):\n{out_b[-1500:]}"
    ok_r, out_r = _sh(["docker", "run", "-d", "--name", container_name,
                      "-p", f"{host_port}:80", image_name])
    if not ok_r:
        return f"RUN FAILED:\n{out_r[-1500:]}"
    container_id = out_r.strip().splitlines()[-1][:12]
    return (f"BUILD OK ({image_name} from {context_dir})\n"
            f"RUN OK -> container {container_name} {container_id} "
            f"listening on http://127.0.0.1:{host_port}/\n"
            f"run details:\n{out_r.strip()}")


AGENT = create_agent(model=get_llm(), tools=[build_and_run], system_prompt=SYSTEM)


def run(task: str):
    res = AGENT.invoke(
        {"messages": [{"role": "user", "content": task}]},
        config={"recursion_limit": 40},
    )
    msgs = res["messages"]
    return {"messages": list(msgs), "report": msgs[-1].content}
