"""CI/CD agent: builds the nginx image and deploys it to Kubernetes.

A realistic CI/CD job — build the artifact, apply the manifest, wait for the
rollout to reach Ready. The Deployment + Service are left running so the
platform (and the user) can inspect them. Idempotent: safe to run repeatedly.
"""

import subprocess
from pathlib import Path

from langchain.agents import create_agent
from langchain_core.tools import tool

from app.llm import get_llm

ROOT = Path(__file__).resolve().parents[2]  # repo root, so context_dir is stable
NAMESPACE = "helloworld"
LIVE_CHECK_PORT = 8081  # matches the coordinator's port-forward local port


def _sh(cmd, timeout=300) -> tuple[bool, str]:
    p = subprocess.run(list(cmd), capture_output=True, text=True,
                       cwd=str(ROOT), timeout=timeout)
    ok = p.returncode == 0
    return ok, (p.stdout + p.stderr) or "(no output)"


def _manifest(app: str, namespace: str, image: str) -> str:
    """Deterministic Deployment + Service manifest (generated, not LLM-written)."""
    return f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: {app}
  namespace: {namespace}
  labels:
    app: {app}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: {app}
  template:
    metadata:
      labels:
        app: {app}
    spec:
      containers:
      - name: web
        image: {image}
        imagePullPolicy: IfNotPresent
        ports:
        - containerPort: 80
        # --- improvement #3: k8s probes + resource limits (from monitor agent) ---
        livenessProbe:
          httpGet:
            path: /
            port: 80
          initialDelaySeconds: 10
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /
            port: 80
          initialDelaySeconds: 5
          periodSeconds: 10
        resources:
          requests:
            cpu: 50m
            memory: 32Mi
          limits:
            cpu: 100m
            memory: 256Mi
---
apiVersion: v1
kind: Service
metadata:
  name: {app}
  namespace: {namespace}
  labels:
    app: {app}
spec:
  selector:
    app: {app}
  ports:
  - port: 80
    targetPort: 80
"""


@tool
def deploy_to_k8s(image: str = "helloworld-nginx",
                  app: str = "helloworld",
                  namespace: str = NAMESPACE,
                  context_dir: str = "trial/helloworld") -> str:
    """Build `image` from context_dir, then deploy it to Kubernetes as a
    Deployment + Service named `app` in `namespace`. Writes the manifest to
    trial/helloworld/k8s.yaml and waits for the rollout to become Ready. Returns
    the live service info. Idempotent and safe to rerun."""
    # 1) build the artifact; the node uses the local store (OrbStack shares it,
    #    and imagePullPolicy:IfNotPresent finds the local build without a registry)
    ok_b, out_b = _sh(["docker", "build", "-t", image, context_dir])
    if not ok_b:
        return f"BUILD FAILED ({context_dir}):\n{out_b[-1500:]}"

    # 2) ensure the namespace exists (a no-op if it already does)
    _sh(["kubectl", "create", "namespace", namespace])

    # 3) render the manifest as an artifact and apply it
    manifest = _manifest(app, namespace, image)
    (ROOT / context_dir / "k8s.yaml").write_text(manifest)
    ok_a, out_a = _sh(["kubectl", "apply", "-f", f"{context_dir}/k8s.yaml"])
    if not ok_a:
        return f"APPLY FAILED:\n{out_a[-1500:]}"

    # 4) wait for the rollout — this is what "deploy" really means
    ok_r, out_r = _sh(["kubectl", "-n", namespace, "rollout", "status",
                       f"deployment/{app}", "--timeout=120s"])
    if not ok_r:
        return f"ROLLOUT DID NOT REACH READY:\n{out_r[-1500:]}"

    # 5) report the live service
    ok_s, out_s = _sh(["kubectl", "-n", namespace, "get", "svc", app, "-o", "wide"])
    ready = out_r.strip().splitlines()[-1] if out_r.strip() else "ready"
    return (
        f"DEPLOYED OK — image '{image}' is now running on Kubernetes:\n"
        f"  Deployment + Service '{app}' in namespace '{namespace}' -> {ready}\n"
        f"service:\n{out_s.strip()}\n"
        f"\nInspect:  kubectl -n {namespace} get all\n"
        f"Browse:   kubectl -n {namespace} port-forward svc/{app} {LIVE_CHECK_PORT}:80\n"
        f"          then open http://127.0.0.1:{LIVE_CHECK_PORT}/"
    )


SYSTEM = (
    "You are the CI/CD agent. You deploy with the deploy_to_k8s tool, which "
    "builds the image, applies a Deployment + Service to Kubernetes, and waits "
    "for the rollout to reach Ready. Report what it built and deployed and how "
    "to reach it. Do not claim the site is live unless the tool reported a "
    "Ready rollout."
)

AGENT = create_agent(model=get_llm(), tools=[deploy_to_k8s], system_prompt=SYSTEM)


def run(task: str):
    res = AGENT.invoke(
        {"messages": [{"role": "user", "content": task}]},
        config={"recursion_limit": 40},
    )
    msgs = res["messages"]
    return {"messages": list(msgs), "report": msgs[-1].content}
