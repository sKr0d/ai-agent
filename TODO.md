# TODO.md

Outstanding work, tracked with Markdown checkboxes. **Verified** items are labelled
as such; **OPEN/ASSUMED** items need confirmation. Priorities:
**P0** = on the critical path to the north star; **P1** = valuable; **P2** = polish.

The canonical source for user-owned intent is `ideas.md` (untracked) — keep it and
this file in sync. `ideas.md` is the user's notes and must not be overwritten.

---

## Milestones — COMPLETED

- [x] **M1 — Multi-agent scaffold validated end-to-end** (`app/`).
  Orchestrator + 4 specialist sub-agents; FastAPI `/health`, `/ready`
  (**503 when LLM unreachable**), `/chat`, `/runs`.
- [x] **M2 — Migrate to LangChain v1 API.** `create_react_agent` →
  `create_agent`; `state_modifier` → `system_prompt`. (Pins in `requirements.txt`.)
- [x] **M3 — K8s smoke-test of the agent service** on OrbStack via
  `deploy/agent.yaml` (pod + Service + `/ready` 200).
- [x] **M4 — Hello-World trial, first on Docker `docker run`.** PASSED after fixing
  two assistant bugs (see `PROGRESS.md`).
- [x] **M5 — Rework the trial to deploy to Kubernetes** (`trial/coordinator.py` +
  `trial/agents/*`); monitoring verified **in-cluster via port-forward** (HTTP 200,
  "Hello World"); independent `kubectl` + `curl` confirmed. Docs regenerated.
- [x] **M6 — Real error monitoring in the monitoring agent.** Added
  `kubectl_logs` (with anomaly summary) + `query_metrics` (pod health, no metrics
  server), correlated with `http_get` into a **PASS/DEGRADED/FAIL** verdict.
- [x] **M7 — Apply an improvement (closed the loop).** Added **liveness/readiness
  probes + resource limits** to `trial/helloworld/k8s.yaml` (via the CI/CD
  manifest) and **narrowed the monitoring anomaly matcher** to real faults;
  redeployed (pod hash changed `54f66f64bc` → `5dc9d4dcc`, 0 restarts) and
  re-verified healthy/PASS.

---

## IN PROGRESS / PENDING COMMIT (P0)

- [ ] **Commit the current uncommitted work** (user-directed; not yet done as of the
  last context checkpoint). Uncommitted tracked files:
  - `trial/agents/monitoring.py` (logs+metrics+HTTP + narrowed matcher)
  - `trial/agents/cicd.py` (probes + resource limits)
  - `trial/coordinator.py` (monitoring/improvement tasks + overview row)
  - `trial/helloworld/k8s.yaml` (generated, improved)
  - `Hello-World.md`, `Hello-World-out.md` (generated, improved run)
  - Untracked: `ideas.md`
  - **Note:** `AGENTS.md`, `TODO.md`, `PROGRESS.md` are new and untracked too.
- [ ] **Push to origin** when the branch/PR flow is ready (P0). `git rev-list`
  reported `origin/main` == `HEAD` (`588cc0f`) at one point — **verify** current
  ahead/behind before pushing. **Do not push/merge to `main`** until the code-owner
  + PR flow from `ideas.md` exists.

## P0 — GitHub repo hygiene & agent workflow (from `ideas.md`, mostly unstarted)

- [ ] Create **CODEOWNERS**; `sKr0d` is the code owner.
- [ ] Add **branch-protection rules**: code-owner review **required before merge to
      main**.
- [ ] Wire the agent to **use branches + pull requests** (short descriptive names:
      ticket # or 2–3 words).
- [ ] **OPEN:** agent GitHub **credentials** — PAT vs SSH key. Decide and document
      the mechanism; ensure the token/secret is never baked into images (`.env`
      pattern already established).

## P1 — Reviewer agent + on-merge Actions (from `ideas.md`)

- [ ] Build a **pull-request reviewer agent** that reviews findings and reports
      required fixes to the coordinator (decide: self-fix vs human review).
- [ ] **OPEN design question:** notification/trigger mechanism for the reviewer —
      GitHub webhook/subscription, `gh` CLI, or **poll every minute**.
- [ ] **Actions on merge to main** (in order):
  - [ ] run unit tests
  - [ ] build the Dockerfile, **tag by unix epoch**
  - [ ] **Trivy** vulnerability scan
  - [ ] push image to **GHCR** (`ghcr.io/...`)
  - [ ] update the **deployment agent to pull from GHCR** (then remove
        `imagePullPolicy: IfNotPresent` from manifests, which currently relies on
        OrbStack's shared image store)

## P1 — Road to Kubernetes north star (from `README.md`)

- [ ] **State out of the process:** swap `MemorySaver` → `RedisSaver`/`PostgresSaver`
      (one shared checkpointer keyed on `thread_id`).
- [ ] **Each sub-agent → its own Service:** split `app/agents/*` into deployables
      exposing HTTP/gRPC; the orchestrator wraps them with a network call.
- [ ] **Probes:** point k8s `livenessProbe`→`/health`, `readinessProbe`→`/ready`
      (already done for `deploy/agent.yaml` and the helloworld trial).
- [ ] **Secrets:** move `LLM_API_KEY` etc. from env → k8s `Secret`.
- [ ] **Observability:** enable LangSmith/OTel tracing (`.env.example`) and have the
      monitoring agent consume real traces/metrics instead of `kubectl`.

## P2 — Open questions / assumptions to resolve

- [ ] **Improvement loop stationarity:** after M7, the re-run improvement agent's
      top suggestion was "add resource limits" — which is **already present** in the
      manifest. Decide whether to (a) detect already-applied proposals and pick the
      next unapplied one, or (b) treat a PASS as a loop-exit condition.
- [ ] **nginx memory headroom (ASSUMED, unverified):** the 256Mi limit was chosen
      for headroom because nginx spawns many workers on this host (observed ~40s of
      workers); **exact memory usage was not measured.** Verify `kubectl top pods -n
      helloworld` or set a limit from observed usage.
- [ ] **Benign-404 suppression is a deliberate alert-tuning**; confirm this is the
      policy the user wants, vs alerting on 4xx too.

## Known blockers

- (none blocking) — `git` origin ahead/behind and the pending commit are the main
  loose ends; the cluster + Ollama are healthy and the trial passes.
