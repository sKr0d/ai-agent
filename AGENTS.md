# AGENTS.md — Project guide for AI agents working in this repo

> This file preserves the project's intent, architecture, and permanent working
> conventions. **Do not silently overwrite it.** Append/refine; keep the invariants
> below even when refactoring. The user's own running notes live in `ideas.md`
> (untracked) — read it before any planning and do **not** delete or rewrite it.

---

## 1. Purpose (north star)

Build a **Docker → Kubernetes multi-agent coding environment** that eventually
runs four collaborating agents in Kubernetes:

1. **coding** — write source, run tests.
2. **CI/CD** — build artifacts, deploy release channels.
3. **monitoring** — observe runtime (metrics, logs, health) and detect errors.
4. **improvement** — turn monitoring findings into safe, reviewed changes.

The **agent layer is built first** because the local box had no Kubernetes. The
current environment is **OrbStack** (provides both Docker and a Kubernetes
cluster, context `orbstack`). Each part graduates to a pod later; "wrapped as a
tool" today becomes "a call over the network" tomorrow.

The immediate, repeatable deliverable is the **Hello-World trial**: build the
simplest possible Hello-World website and deploy it to Kubernetes in an nginx
container, with all four agents doing **real work** and reporting back to a
coordinator, writing a transcript (`Hello-World-out.md`) and an overview
(`Hello-World.md`) for the user to review.

---

## 2. Architecture

Two layers, deliberately kept separate:

- **`app/` — the primary scaffold.** An orchestrator + four specialist
  sub-agents whose **tools are stubs by design** (canned text that says it is a
  stub). This proves the *pattern* and the HTTP surface; wiring real
  infrastructure is the project.
- **`trial/` — the "wired-up" trial.** Mirror of the four agents but with
  **real tools** that do real work against Docker/Kubernetes in the helloworld
  namespace. This is where real end-to-end behavior is demonstrated.

### Multi-agent pattern: "subagents as tools"
- The **orchestrator** (`app/orchestrator.py`) is itself a `create_agent`
  graph. Each specialist is a `create_agent` graph exposed to it as a **tool**
  (`ask_coding`, `ask_cicd`, `ask_monitoring`, `ask_improvement`).
- The orchestrator reads the request, delegates to the ONE specialist whose name
  fits best, and answers from that specialist's result.
- Adding an agent = adding one file (`app/agents/<name>.py`) + one
  `ask_<name>` tool + one dict entry in `SPECIALISTS`. Nothing else changes.
- Sub-agents are **stateless per call** (per-invocation). The orchestrator holds
  conversation memory via a per-`thread_id` `MemorySaver` checkpointer.

### The API (LangChain v1) — IMPORTANT
- Use **`langchain.agents.create_agent`**, NOT the deprecated
  `langgraph.prebuilt.create_react_agent`.
- The modern signature is `create_agent(model=..., tools=...,
  system_prompt=..., checkpointer=...)`.
- In v1 the old `state_modifier=` argument is **gone** — use `system_prompt=`
  instead. (`agent.py` at the repo root is the deprecated starting point, kept
  for reference only; it still uses `create_react_agent` + `state_modifier` and
  is **not** the live app.)

### HTTP surface (`app/server.py`, FastAPI, uvicorn on :8000)
| Method | Path     | Purpose                                  | k8s analog         |
|--------|----------|------------------------------------------|--------------------|
| GET    | `/health`| Liveness — process is up                 | livenessProbe      |
| GET    | `/ready` | Readiness — can we reach the LLM? (**503 when LLM unreachable**) | readinessProbe |
| POST   | `/chat`  | Run a request through the orchestrator   | Service            |
| GET    | `/runs`  | Recent run log (agent, status, latency)  | (query OTel later) |

`/ready` returns **HTTP 503 when the LLM endpoint is unreachable** so k8s
readiness probes gate traffic and the monitoring agent can consume the 503s.
This was an intentional change — **do not revert it to 200-always**.

---

## 3. The trial (`trial/`) — how it works

Run it with `. .venv/bin/activate && python -m trial.coordinator` from the repo
root. It drives **coding → cicd → monitoring → improvement**, routing each
agent's real output to the next and writing two docs to the repo root.

- **coding** (`trial/agents/coding.py`): tool `write_file(path, content)` writes
  `trial/helloworld/index.html` and `trial/helloworld/Dockerfile` on disk. The
  tool strips any leading `helloworld/` prefix and refuses path-escape attempts
  (writes only under `trial/helloworld/`).
- **cicd** (`trial/agents/cicd.py`): tool `deploy_to_k8s(image, app, namespace,
  context_dir)`. Real flow: `docker build -t helloworld-nginx trial/helloworld`
  → ensure namespace → render a deterministic Deployment+Service manifest (NOT
  LLM-written) to `trial/helloworld/k8s.yaml` → `kubectl apply` →
  `kubectl rollout status --timeout=120s` → `kubectl get svc`. Idempotent.
- **monitoring** (`trial/agents/monitoring.py`): **three real signals**
  - `http_get(url)` — live HTTP probe of the in-cluster Service via a
    coordinator-managed `kubectl port-forward` (local **8081** → svc 80).
  - `kubectl_logs(namespace, app, tail)` — reads pod stdout/stderr via
    `kubectl logs -n <ns> -l app=<app> --tail=<n>` and returns an **ANOMALY
    SUMMARY**. It alerts only on **real faults** (HTTP 5xx, or
    `[error]/[crit]/[alert]` lines) and **suppresses benign 4xx / "no such file"
    404 noise** (an alert-tuning applied from the improvement agent's #1
    recommendation). It reports `N real-fault line(s), M benign line(s)
    suppressed`.
  - `query_metrics(namespace, app)` — real k8s health (pod phase, restart count,
    readiness) parsed from `kubectl get pods -o json` — **no metrics server
    needed**. Note: the JSON is a **PodList** (`dict` with an `items` array);
    parse `data["items"]`, not the top-level dict.
  - The agent correlates all three into **ONE verdict: PASS / DEGRADED / FAIL**.
    (DEGRADED = HTTP 200 but log anomalies or restarts; FAIL = HTTP not 200 or no
    pods.)
- **improvement** (`trial/agents/improvement.py`): **no tools** — pure
  reasoning that turns the monitoring verdict into 3 prioritized, concrete
  improvements. A real system gates these behind a PR + human approval.

**Port-forward ownership:** the coordinator, not the agent, owns the
`kubectl port-forward` lifecycle (start before monitoring, `finally`-stop after).
This keeps the agent's tool surface HTTP-shaped. Stale forwards from a prior run
are killed first with `pkill -f "port-forward -n helloworld"`.

---

## 4. Development conventions

- **Python:** use the project virtualenv. Create with
  `python3 -m venv .venv`. There is **no `pip`/`uv` on PATH** in this env —
  always `. .venv/bin/activate` (or call `.venv/bin/python`) so imports resolve.
- **LLM access:** talk to **Ollama** through its **OpenAI-compatible endpoint**
  with `ChatOpenAI` + `base_url` (in `app/llm.py`). Model is **`qwen3.8:27b`**
  (note: the original config had a typo `qwen3.7:27b` — corrected everywhere
  except the deprecated `agent.py`, which still defaults to `qwen3.7:27b`).
  The model is loaded on GPU/MLX and runs at `127.0.0.1:11434`.
- **Agent timing:** each sub-agent `invoke` is ~10–30 s of LLM time, so a full
  trial run (~1–2 min). **Allow generous timeouts** (use ≥ 300–480 s when
  invoking the trial or multi-call scripts).
- **Config layering** (`app/config.py`): priority is **env vars >
  `config/settings.yaml` > code defaults** — mirrors k8s env/Secret overriding
  baked-in defaults. Env names: `LLM_MODEL`, `LLM_BASE_URL`, `LLM_API_KEY`,
  `LLM_TEMPERATURE`, `LOG_LEVEL`.
- **Safety rule (keep it):** production/destructive changes are **blocked or gated
  behind human approval.** The `app/agents/cicd.py` `deploy_to_k8s` stub already
  blocks `prod`; the improvement agent proposes but never auto-applies. Preserve
  this invariant in any new agent.
- **Secrets:** `LLM_API_KEY` etc. live in `.env` (gitignored), never baked into
  the image (`.dockerignore` excludes `.env`). `.env` is gitignored.
- **Git:** the user directs when to commit; use **concise** commit messages.
  New work should use **branches + pull requests** (see `ideas.md` / §7) — do not
  push to `main` without that flow once it is set up.
- **Trial artifacts are regenerable:** `trial/helloworld/k8s.yaml`,
  `Hello-World.md`, `Hello-World-out.md` are produced by the trial run; re-running
  the trial overwrites them. `index.html`/`Dockerfile` are written by the coding
  agent. Don't hand-patch generated files.

---

## 5. Dependencies (pinned — validated in this environment)

`requirements.txt` is pinned for reproducible builds:

```
langchain==1.4.4
langchain-openai==1.7.0
langgraph==1.2.14
fastapi==0.143.0
uvicorn==0.54.0
pydantic==2.14.0
PyYAML==6.0.3
requests==2.34.2
```

`create_agent` lives in `langchain` (v1); pinning matters because
`create_react_agent` + `state_modifier` no longer exist there.

---

## 6. Operational constraints (this environment)

- **Platform:** macOS (Darwin). **OrbStack** provides Docker (**29.4.0**,
  overlayfs) and Kubernetes (**context `orbstack`**, cluster **v1.35.6**, node
  `orbstack`). `kubectl` and `docker` are available; **no `pip`/`uv` on PATH.**
- **Ollama** runs on the host at `127.0.0.1:11434`. From a **k8s pod**, the host
  is reachable at **both** `host.orb.internal:11434` and
  `host.docker.internal:11434` (both verified).
- **No registry push needed for local k8s:** OrbStack shares its Docker image
  store with its Kubernetes runtime, so `imagePullPolicy: IfNotPresent` finds the
  locally-built `helloworld-nginx` image. The manifest deliberately uses
  `IfNotPresent`; remove it only when a real registry is in use.
- **Run the trial:** `. .venv/bin/activate && python -m trial.coordinator`. It
  **leaves the `helloworld` namespace running** (Deployment `helloworld`,
  ClusterIP Service on `:80`). Browse via
  `kubectl -n helloworld port-forward svc/helloworld 8081:80` →
  `http://127.0.0.1:8081/`. Teardown: `kubectl delete namespace helloworld`.
- **Smoke-test workload** for the agent service itself is `deploy/agent.yaml`
  (image `ai-agent:smoketest`, ClusterIP `ai-agent:80`, probes at
  `/health`+`/ready`, resources 100m/128Mi→500m/512Mi). It was verified on-cluster
  (pod + Service + `/ready` 200).

---

## 7. Permanent instructions / user intent (from `ideas.md`)

Preserve these as durable, user-owned directives (the source is `ideas.md`; keep
it and its checkboxes as the canonical list — mirror them in `TODO.md`):

- **GitHub repo hygiene:**
  - Create **CODEOWNERS**; **`sKr0d`** is the code owner.
  - Add **branch-protection rules**: code-owner review is **required before merge
    to main**.
  - Tell the agent to **use branches and pull requests** (short, descriptive
    names — a ticket number or 2–3 words). Do **not** commit/merge to `main`
    through that flow yet.
  - Figure out **agent credentials for GitHub** — PAT vs SSH key (**OPEN,
    unresolved**).
- **A review agent:** create a **pull-request reviewer agent** that reviews
  findings and reports required fixes back to the coordinator (to decide whether
  the coding agent fixes it or a human must review). **OPEN design question:**
  notification mechanism — GitHub subscription/webhook, `gh` CLI, or **polling
  every minute**.
- **Actions on merge to main:** run unit tests; build the Dockerfile (tag by
  **unix epoch**); scan for vulnerabilities with **Trivy**; push the image to the
  **GitHub container registry (GHCR)**; then update the **deployment agent to
  pull from GHCR**.

These are aspirational roadmap items, **not yet implemented**.

---

## 8. Layout

```
agent.py                  deprecated single-agent start (create_react_agent) — reference only
app/
  config.py               env > yaml > defaults layering
  llm.py                  cached ChatOpenAI (Ollama via OpenAI-compatible API)
  observability.py        JSON logs + in-memory run log (deque; swap for Redis/OTel in k8s)
  orchestrator.py         the supervisor (create_agent + subagents-as-tools + MemorySaver)
  server.py               FastAPI: /health /ready(503 on LLM down) /chat /runs
  agents/
    base.py               build_worker(): the uniform create_agent factory
    coding.py             coding stub (write_code, run_tests)            [STUB]
    cicd.py               cicd stub (trigger_pipeline, deploy_to_k8s[prod-gated])  [STUB]
    monitoring.py         monitor stub (query_metrics, fetch_logs, check_health) [STUB]
    improvement.py        improver stub (propose_improvement, apply_improvement) [STUB]
trial/
  coordinator.py          runs the 4 real agents; owns the port-forward; writes the 2 MDs
  agents/
    coding.py             write_file  -> trial/helloworld/index.html + Dockerfile
    cicd.py               deploy_to_k8s -> build + apply manifest + rollout
    monitoring.py         http_get + kubectl_logs + query_metrics -> PASS/DEGRADED/FAIL
    improvement.py        no tools -> 3 prioritized improvements
  helloworld/
    index.html            the page ("<h1>Hello World</h1>")   [generated]
    Dockerfile            FROM nginx:latest; COPY index.html ... [generated]
    k8s.yaml              Deployment + Service, probes + resource limits [generated]
config/settings.yaml      local LLM/logging defaults (env overrides)
requirements.txt          pinned to the validated environment
deploy/agent.yaml         on-cluster smoke-test for the agent service
docker-compose.yml        one Service that runs the agent with host Ollama
Dockerfile                non-root build, /health HEALTHCHECK, uvicorn :8000
README.md                 human-facing overview (the scaffold's north-star roadmap)
Hello-World.md            overview of a trial run            [generated]
Hello-World-out.md        full agent<->coordinator transcript [generated]
ideas.md                  USER'S OWN running notes (do not overwrite/modify)
.env.example              copy to .env; secrets live here, not baked in
```

# OpenCode Agent Instructions

## Git Workflow

You are an autonomous coding agent working in a GitHub repository.

### Branch Management

- NEVER commit directly to main or master.
- Before starting a new task, check the current Git status.
- Create a new branch from the latest main.
- Use descriptive branch names:
  - feature/<description>
  - fix/<description>
  - refactor/<description>
  - docs/<description>
- Do not overwrite or discard uncommitted changes.
- Do not force-push.

### Development

- Work autonomously on the assigned task.
- Make small, logical commits.
- Use descriptive commit messages.
- Run relevant tests before submitting changes.
- Document any tests that could not be run.
- Update project documentation when appropriate.

### Pull Requests

When a task is complete:

1. Commit all relevant changes.
2. Push the feature branch to origin.
3. Create a GitHub pull request using `gh pr create`.
4. Include in the PR description:
   - Summary of changes
   - Implementation details
   - Tests performed
   - Known limitations
   - Any decisions requiring human review
5. Return the PR URL to the user.

### Review and Merge Policy

- NEVER merge a pull request automatically.
- NEVER approve your own pull request.
- NEVER push directly to main or master.
- Wait for explicit human approval before merging.
- If review feedback is received, make changes
  on the existing feature branch and update the PR.

### Safety

- Do not delete remote branches without permission.
- Do not rewrite published Git history.
- Do not modify GitHub branch protection settings.
- Do not bypass required checks or reviews.
- Do not include secrets or credentials in commits.

## Task Completion

A task is considered complete when:

- Implementation is finished.
- Relevant tests have been run.
- Changes are committed.
- A pull request has been created.
- The PR URL has been reported to the user.

The human reviewer is responsible for merging.


