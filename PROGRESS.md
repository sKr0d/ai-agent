# PROGRESS.md — current development state

> Snapshot of where the project is, why key decisions were made, the bugs we hit
> and how we fixed them, what changed, and what to work on next. Distills
> `AGENTS.md` (permanent intent) and `TODO.md` (next work). **Distinguish
> [VERIFIED] facts from [ASSUMED]/[OPEN] ones below.** Last updated for the
> "preserve knowledge before compaction" checkpoint.

---

## 1. Where we are

- The multi-agent **scaffold** (`app/`) is built and **verified end-to-end**.
- The **Hello-World trial** (`trial/`) runs **coding → cicd → monitoring →
  improvement** against real Docker + Kubernetes on OrbStack, and **passes**.
- The deployment target moved from `docker run` to **Kubernetes** (per user's
  request); monitoring gained **real log + metrics error-monitoring**; an
  improvement was **applied and re-verified** (probes + resource limits + narrowed
  anomaly matcher).
- **The trial is currently UNCOMMITTED.** The improvement + monitoring work is on
  disk and verified but has **not been committed or pushed** (user directs
  commits). See §5.

---

## 2. Architecture & key decisions (with rationale)

- **Multi-agent = "subagents as tools."** Orchestrator is a
  `create_agent` graph; each specialist is its own `create_agent` graph wrapped as
  a tool (`ask_<name>`). Rationale: adding an agent = one file + one tool + one
  dict entry; each specialist is small/testable; maps to k8s later (agent →
  Service). [VERIFIED]
- **Two layers: `app/` (stubs) vs `trial/` (real).** `app/` proves the pattern
  with canned-return stubs; `trial/` is the "wired-up" version with real tools
  against the cluster. Rationale: keep the learning scaffold clean and safe while
  proving real behavior in an isolated area. [VERIFIED]
- **LangChain v1 API: `create_agent` (not `create_react_agent`);
  `system_prompt=` (not `state_modifier=`).** [VERIFIED] The old
  `agent.py` deliberately still uses the deprecated API as a reference artifact.
- **Talk to Ollama via OpenAI-compatible endpoint** (`ChatOpenAI` + `base_url`,
  model `qwen3.8:27b`). Rationale: the same code works against any
  OpenAI-compatible provider by changing 3 env vars. [VERIFIED]
- **`/ready` returns HTTP 503 when the LLM is unreachable.** So k8s
  readiness gates traffic and the monitoring agent can consume the 503.
  **Do not revert to 200-always.** [VERIFIED, intentional]
- **CI/CD deploys to Kubernetes** via the `deploy_to_k8s` tool:
  `docker build -t helloworld-nginx trial/helloworld` → ensure namespace →
  write deterministic manifest `trial/helloworld/k8s.yaml` (Deployment + Service,
  **not** LLM-written) → `kubectl apply` → `kubectl rollout status
  --timeout=120s` → `kubectl get svc`. `imagePullPolicy: IfNotPresent` because
  OrbStack shares its Docker store with k8s. [VERIFIED]
- **Monitoring agent owns 3 real signals** (`http_get` + `kubectl_logs` +
  `query_metrics`) and correlates into **PASS/DEGRADED/FAIL**. Rationale: matches
  the "error monitoring" north star; each signal is dependency-free (no
  Prometheus needed). [VERIFIED]
- **Port-forward is platform-owned.** The coordinator starts/stops the
  `kubectl port-forward` (local 8081 → svc 80) in a `try/finally`, killing stale
  forwards first. Keeps the agent's tool surface HTTP-shaped. [VERIFIED]
- **`query_metrics` derives health from `kubectl get pods -o json`** (phase,
  restarts, readiness) — no metrics server. [VERIFIED]
- **Improvements so far, applied:** (1) **narrowed anomaly matcher** to real
  faults (5xx + real `[error]`), suppressing benign 4xx/"no such file" noise —
  implemented per the improvement agent's own #1 recommendation; (3) added
  **liveness/readiness probes + resource limits** (req 50m/32Mi →
  lim 100m/256Mi) to the manifest. [VERIFIED applied + redeployed]
- **Improvement #2 (silence 404 at the nginx source)** was deliberately
  **skipped** to keep scope tight (would need an nginx config mount). [OPEN]

---

## 3. Bugs encountered & fixes

1. **Assistant: `build_and_run` ignored `context_dir` + coding agent double-nested the
   path** (first Docker-`run` trial). Symptom: the build ran in the wrong
   directory / a `helloworld/helloworld/` nesting.
   **Fix:** the coding agent's `write_file` tool now strips any leading
   `helloworld/` prefix and refuses path-escapes; the CICD tool takes an explicit
   `context_dir` defaulting to `trial/helloworld`. [VERIFIED — trial passed]
2. **Model name typo `qwen3.7:27b`** in the original config. **Fix:** corrected
   to `qwen3.8:27b` in `config/settings.yaml`, `.env.example`, `docker-compose.yml`,
   `deploy/agent.yaml`, and `requirements.txt`-adjacent code. **The deprecated
   `agent.py` still defaults to `qwen3.7:22b`/`qwen3.7:27b` and is left as-is
   (reference only).** [VERIFIED]
3. **`/ready` returned 200 even when the LLM was down** (useless gate). **Fix:**
   `app/server.py` now raises **HTTP 503** when `/models` is unreachable.
   [VERIFIED]
4. **`query_metrics` iterated the `PodList` dict instead of its `items` array.**
   Symptom: `po` came back as a string (dict keys). Root cause:
   `kubectl get pods -o json` returns `{..., "items": [...]}`.
   **Fix:** `data = json.loads(out or "{}");
   pods = data.get("items", [])` in `trial/agents/monitoring.py`.
   [VERIFIED — tool then returned real restart/phase/ready]
5. **Potential OOMKill under a tight limit.** nginx spawns ~40s of workers on this
   host, so a 128Mi limit was judged risky. **Fix (precautionary):** set memory
   limit to **256Mi** with headroom. **Exact memory usage was not measured** —
   [ASSUMED] headroom; should be confirmed (see TODO P2).
6. **`question` tool usage:** repeatedly required a `question` key that was
   initially omitted (tool-arg shape). Procedural, not a code bug — noted so
   future tool calls include it. [PROCESS]

---

## 4. Files modified / created

**New (this checkpoint, documentation only — no app code changed):**
- `AGENTS.md`, `TODO.md`, `PROGRESS.md` — new, untracked.

**Uncommitted (trial improvement + monitoring, verified but NOT yet committed):**
- `trial/agents/monitoring.py` — added `kubectl_logs` (anomaly summary) +
  `query_metrics` (fixed PodList bug); narrowed matcher; PASS/DEGRADED/FAIL verdict.
- `trial/agents/cicd.py` — manifest now includes liveness/readiness probes +
  resource limits.
- `trial/coordinator.py` — monitoring task (3 signals + verdict); improvement task
  references log findings; overview monitor row updated.
- `trial/helloworld/k8s.yaml` — regenerated with probes + resource limits.
- `Hello-World.md`, `Hello-World-out.md` — regenerated (improved run).
- `ideas.md` — **user's own notes, untracked; do not modify.**

**Committed history (main):**
- `4b1a229` intial application
- `dea1fd8` Add K8s Deployment + Service manifest for the agent (smoke-tested on-cluster)
- `8e59418` Add Hello-World multi-agent trial (coding/cicd/monitoring/improvement)
- `588cc0f` Deploy the Hello-World trial to Kubernetes instead of docker run

---

## 5. Live cluster / runtime state at checkpoint

- **Namespace `helloworld` is UP** (Deployment `1/1`, 38m+ at checkpoint). The
  current pod is **`helloworld-5dc9d4dcc-xf7cn`**, `1/1 Running`, **0 restarts** —
  the **improved** replica set (hash changed from the pre-improvement
  `helloworld-54f66f64bc`, confirming probes+resources triggered a rolling
  update). [VERIFIED via `kubectl get deploy,pods -n helloworld`]
- Monitoring's last trial verdict: **PASS / "all three monitoring signals agree —
  the deployment is healthy."** [VERIFIED, from last trial run]
- A stale `helloworld-web` **Docker container is in Exited state** (from the first
  `docker run` trial) — harmless; can be removed with `docker rm helloworld-web`
  if desired. [VERIFIED at last check]
- **Open design question / loop stationarity:** after the improvement was applied,
  the re-run improvement agent's top suggestion was "add resource limits" — which
  is **already in the manifest**. So the loop is not yet convergent to a terminal
  state; decide a stop condition (see TODO P2). [OPEN]

**Tear down the namespace:** `kubectl delete namespace helloworld`.
**Tear down the agent deploy (if applied):** `kubectl delete -f deploy/agent.yaml`.

---

## 6. How to run / verify (copy-paste)

```bash
# env
. .venv/bin/activate            # NO pip/uv on PATH; use the venv

# full trial (leaves helloworld namespace running)
python -m trial.coordinator

# browse the in-cluster site
kubectl -n helloworld port-forward svc/helloworld 8081:80
# -> http://127.0.0.1:8081/

# read recent agent conversation / overview (repo root)
less Hello-World-out.md
less Hello-World.md
```

---

## 7. What to work on next (summary; detail in TODO.md)

- **P0:** commit the uncommitted improvement + monitoring work; then the branch/PR
  + code-owner + GHCR flow from `ideas.md`.
- **P1:** PR-reviewer agent + on-merge Actions (tests → build tag by epoch →
  Trivy → push GHCR → deploy from GHCR).
- **P1:** graduate to k8s per `README.md` (state out of process via
  Redis/Postgres; each sub-agent → its own Service; move secrets to a k8s Secret;
  real OTel/LangSmith observability).
- **P2 / OPEN:** confirm nginx memory usage vs the 256Mi limit; define a
  convergence/stop condition for the improvement loop; decide the 4xx alert
  policy; resolve GitHub agent credentials (PAT vs SSH); choose the reviewer
  notification mechanism.

---

## 8. At risk during compaction (things NOT captured on disk)

- **The uncommitted diff content itself** (monitoring tools, cicd manifest,
  coordinator tasks) is on disk in the working tree, so it survives compaction —
  but it is **uncommitted**, so a `git` reset/clean or a new worktree could lose
  it. **Committing it is the single most important safety net.**
- **Live cluster state** (namespace `helloworld` up, pod `5dc9d4dcc-xf7cn`) is
  external to the repo; if the cluster is reset, the trial must be re-run to
  recreate it. Not captured in git.
- **The `question` tool's required `question` key** and the "allow generous
  timeouts" rule are procedural knowledge held here in `PROGRESS.md`/`AGENTS.md`.
- **Why `qwen3.7:22b`/`qwen3.7:27b` remains in `agent.py`** (left as a reference,
  not a live path) — captured in §2 and `AGENTS.md`; easy to misread otherwise.
