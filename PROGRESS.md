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
- **All of the above is now committed and merged to `main`** (trial via PR #1;
  docs via PR #2; GHCR GitHub-Actions build via PR #3; `ideas.md` typo via
  PR #4). See §5 / §7 for history.
- **A full unit-test suite now exists on branch `unit-tests`** — stdlib
  `unittest`, no new deps, no live Ollama/kubectl/docker (all external calls
  mocked). **93 tests pass, 1 skipped** (the deprecated `agent.py` reference,
  which no longer imports). See §6.

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
7. **`docker.yaml` failed to parse on GitHub Actions.** After merging the
   GHCR-build workflow, the run reported **"Invalid workflow file — (Line: 52,
   Col: 13): A sequence was not expected"** even though **PyYAML parsed it fine**.
   Root cause (reproduced with `actionlint`): GitHub's expression-aware parser
   rejects a `tags:` **YAML sequence whose items are `${{ }}`-expressing strings**
   (`expected scalar node ... but found "!!seq"`), even though it's valid standard
   YAML. **Fix:** pass `tags` to `build-push-action` as a **newline-separated
   block scalar** instead of a sequence (the action accepts a comma/newline list).
   Verified clean with `actionlint` — only the benign `steps.tag.epoch` false
   positive remains (the `id: tag` step exports `epoch=` to `$GITHUB_OUTPUT`,
   which `actionlint` can't infer statically). [VERIFIED via actionlint]
 8. **GHCR build failed: "repository name must be lowercase."** After fix #7 the
    parse error was gone, but the **build** then failed: the tag
    `ghcr.io/${{ github.repository }}:latest` resolved to
    **`ghcr.io/sKr0d/ai-agent:latest`** — repo name `sKr0d` is mixed case and
    Docker/GHCR repo names **must be lowercase**. **Fix:** compute a lowercase repo
    in the `id: tag` step via
    `printf '%s' "$GITHUB_REPOSITORY" | tr '[:upper:]' '[:lower:]'` and reference
    `steps.tag.repo`. **Note:** the obvious `toLower()` shortcut is **NOT a built-in
    GitHub Actions expression function** (confirmed by `actionlint`'s available-function
    list and by existing marketplace "Change String Case" actions) — so it must be done
    in the shell. [VERIFIED via grammar check + `actionlint`]

---

## 4. Files modified / created

**New (this checkpoint, documentation only — no app code changed):**
- `AGENTS.md`, `TODO.md`, `PROGRESS.md` — new, untracked.

**Merged to `main` (previously uncommitted — now committed via PRs #1–#4):**
- `trial/agents/monitoring.py` — `kubectl_logs` (anomaly summary) +
  `query_metrics` (fixed PodList bug); narrowed matcher; PASS/DEGRADED/FAIL verdict.
- `trial/agents/cicd.py` — manifest now includes liveness/readiness probes +
  resource limits.
- `trial/coordinator.py` — monitoring task (3 signals + verdict); improvement task
  references log findings; overview monitor row updated.
- `trial/helloworld/k8s.yaml` — regenerated with probes + resource limits.
- `Hello-World.md`, `Hello-World-out.md` — regenerated (improved run).
- `.github/workflows/docker.yaml` — build + push to GHCR on merge to main (#3).
- `AGENTS.md`, `TODO.md`, `PROGRESS.md`, `ideas.md` — docs (#2 + typo fix #4).

**Untracked on branch `unit-tests` (this work — not yet committed):**
- `tests/` — the stdlib `unittest` suite (12 files, 93 tests). See §6.
- `PROGRESS.md` — updated in this pass to reflect the above. [this commit]

**Committed history (main, current tip `4ca4d8e`):**
- `4ca4d8e` Merge PR #3 (actions/GHCR) · `eca8be6` Merge PR #4 (ideas)
- earlier: K8s manifest, Hello-World trial, docs, agent scaffold.

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

## 6. Unit test suite (branch `unit-tests`)

A full, dependency-free `unittest` suite was added — **93 tests pass, 1
skipped** — covering every module in `app/` and `trial/`. No new dependencies
(uses only stdlib `unittest` + `unittest.mock`), so it runs in the pinned CI
environment as-is.

**Design constraints (the whole point):**
- **No live Ollama / kubectl / docker.** Every external call is mocked:
  `subprocess.run` (kubectl/docker), `urllib.request.urlopen` (HTTP probe /
  `/ready`), and the LLM is never invoked (we call the *tools* and *handlers*
  directly, not the agents).
- **`/ready` 503 invariant** and the **prod-deploy block / dry-run** safety
  invariants are locked as regression tests.
- The deprecated **`agent.py` reference is skipped, not ignored** — it no longer
  imports in langgraph 1.2.14 (`create_react_agent` removed its
  `state_modifier`/`prompt` kwargs, raising `TypeError`). The skip documents the
  reason rather than hiding it.

**Layout (`tests/`, one file per source module):**
| test file | covers |
|-----------|--------|
| `test_config.py` | env > yaml > code-default layering; cached singleton |
| `test_observability.py` | JSON formatter; ring-buffer cap (200); idempotent logging |
| `test_llm.py` | `get_llm()` cached `ChatOpenAI`, no network at construction |
| `test_agent_stubs.py` | all 4 stub-agent tools; prod-block + dry-run invariants |
| `test_orchestrator.py` | `detect_agent` routing; `SPECIALISTS`; graph builds |
| `test_server.py` | `/health`, `/root`, `/runs`; `/ready` 200+503; `/chat` happy+500 |
| `test_reference_agent.py` | deprecated `agent.py` — import smoke test (skipped) |
| `test_trial_coding.py` | `write_file` prefix-strip + path-escape refusal (sandboxed to a temp dir) |
| `test_trial_cicd.py` | `_manifest()` locks probes+limits; deploy pipeline (mocked subprocess) |
| `test_trial_monitoring.py` | `http_get`/`kubectl_logs`/`query_metrics` incl. PodList items[] fix |
| `test_trial_coordinator.py` | `truncate`/`one_line`/`render`/`brief` + port-forward lifecycle |
| `test_trial_improvement.py` | the no-tool agent is pure reasoning (structural smoke) |

**Run it:**
```bash
. .venv/bin/activate
python -m unittest discover -s tests -t . -v     # verbose
# OR: python -m unittest discover -s tests -t .   # quiet (for CI)
```

**Notable traps hit & fixed (in the tests, not the app):**
- `tempfile.mkdtemp()` on macOS returns a `/var/...` **symlink**; the
  `write_file` sandbox compares the *un*-resolved `BASE` against the *resolved*
  target, so the patched `BASE` must be `.resolve()`-d or the write is (correctly)
  refused as an "escape."
- `addCleanup(mock.patch.object, ...)` does **not** start the patch — it must be
  `start()`ed explicitly, or `tearDown` never reverts it.

---

## 7. How to run / verify (copy-paste)

```bash
# env
. .venv/bin/activate            # NO pip/uv on PATH; use the venv

# full trial (leaves helloworld namespace running)
python -m trial.coordinator

# run the unit-test suite (no Ollama/kubectl/docker needed)
python -m unittest discover -s tests -t . -v

# browse the in-cluster site
kubectl -n helloworld port-forward svc/helloworld 8081:80
# -> http://127.0.0.1:8081/

# read recent agent conversation / overview (repo root)
less Hello-World-out.md
less Hello-World.md
```

---

## 8. What to work on next (summary; detail in TODO.md)

- **P0 (done):** the improvement + monitoring work is **merged to `main`**
  (PRs #1–#4).
- **P0:** wire the `unit-tests` suite into the CI workflow so it **gates merges
  to `main`** (the test step must be green before merge). Then add
  Trivy scan + deploy-from-GHCR per `ideas.md`.
- **P1:** graduate to a per-agent k8s Service, state out of process
  (Redis/Postgres), secrets in a k8s Secret, real OTel/LangSmith observability.
- **P2 / OPEN:** confirm nginx memory usage vs the 256Mi limit; define a
  convergence/stop condition for the improvement loop; decide the 4xx alert
  policy; resolve GitHub agent credentials (PAT vs SSH); choose the reviewer
  notification mechanism.

---

## 9. At risk during compaction (things NOT captured on disk)

- **The `tests/` suite is untracked on branch `unit-tests`.** It is on disk, so
  it survives compaction — but it is **uncommitted**, so a `git` reset/clean or a
  new worktree could lose it. **Committing it (and opening the PR) is the single
  most important safety net for this checkpoint.**
- **Live cluster state** (namespace `helloworld` up) is external to the repo; if
  the cluster is reset, the trial must be re-run to recreate it. Not captured in
  git.
- **The `question` tool's required `question` key** and the "allow generous
  timeouts" rule are procedural knowledge held here in `PROGRESS.md`/`AGENTS.md`.
- **Why `qwen3.7:22b`/`qwen3.7:27b` remains in `agent.py`** (left as a reference,
  not a live path) — captured in §2 and `AGENTS.md`; easy to misread otherwise.
