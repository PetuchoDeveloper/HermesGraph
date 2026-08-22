# Quick start

HermesGraph is currently a **research scaffold**, not a Hermes patch. The fastest useful first step is to prove that your hosted verifier endpoint returns stable token logprobs, then run it in shadow mode against frozen Luna outputs before allowing any verifier-triggered repair.

## 1. Clone

```bash
git clone https://github.com/PetuchoDeveloper/HermesGraph.git
cd HermesGraph
```

Python 3.10+ is enough for the included probe; it uses only the standard library.

## 2. Configure one verifier provider

Inject only the provider credentials required for the run into the process environment with your secret manager. Do not pass a `.env` file to the runner; `.env` paths are rejected before loading.

### Cloudflare Workers AI

Create a Workers AI API token and copy your Account ID. The token needs Workers AI read/edit permissions. Set:

```bash
CLOUDFLARE_ACCOUNT_ID=...
CLOUDFLARE_API_TOKEN=...
CLOUDFLARE_MODEL=@cf/zai-org/glm-4.7-flash
```

### OpenRouter

Create an API key and set:

```bash
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=openai/gpt-oss-20b:free
```

Free model availability changes. Keep the model pinned during an experiment; do not use the random free router for calibration runs.

## 3. Probe logprobs

Cloudflare:

```bash
python3 scripts/probe_verifier.py --provider cloudflare
```

OpenRouter:

```bash
python3 scripts/probe_verifier.py --provider openrouter
```

A usable result should show a short `PASS`/`FAIL` completion **and a non-empty `logprobs` object**. If the provider accepts the request but omits logprobs, treat that provider/model pair as unsupported.

## 4. Run the automatic Phase 1 shadow orchestrator

The orchestrator is a local, standard-library-only CLI. It consumes a JSON manifest and TaskSpec, requires a clean Git baseline by default, executes worker and hard-check commands as argv arrays, captures the HEAD-to-worktree diff within the optional literal `candidate_paths` scope, and scores one compact packet per semantic criterion. The artifact directory must be absent or empty.

The checked-in example is self-contained relative to the repository. Create a
disposable candidate repository and commit its baseline:

```bash
mkdir -p candidate-worktree
cd candidate-worktree
git init -q
git config user.email shadow@example.invalid
git config user.name shadow
printf 'baseline\n' > README.txt
git add README.txt && git commit -qm baseline
cd ..
python3 scripts/shadow_orchestrator.py examples/shadow-manifest.example.json
```

Cloudflare credentials must already be present in the process environment. The runner rejects `.env` input paths and never loads `.env` itself. It uses only the fixed `https://api.cloudflare.com` account endpoint; manifests cannot override the endpoint or request headers.

Worker, hard-check, and internal Git subprocesses do not receive Cloudflare credentials. Timed-out commands and descendants are terminated as one process group. Candidate capture rejects active Git clean filters before content inspection. Artifacts redact configured credential values and authorization fields.

For a low/medium-risk task, an unavailable or unusable provider records `accept_deterministic_fallback` and exits zero. A high-risk provider failure records `manual_escalation` and exits one. A semantic `FAIL` records `would_reinspect`; it never starts a repair command.

Artifacts are written outside the candidate worktree, for example:

- `run-record.json` — truthful outcome, hashes, policy action, and errors;
- `candidate.diff` / `candidate.json` — the complete, read-only layered snapshot of staged, unstaged, and untracked candidate state;
- `evidence-packets.json` — compact packets without worker stdout/transcripts;
- `verifier-results.json` and `provider-response-*.json` — normalized scores,
  usage, and response JSON with headers removed.

The manifest contract is documented in
[`schemas/shadow-manifest.schema.json`](schemas/shadow-manifest.schema.json),
and the example is [`examples/shadow-manifest.example.json`](examples/shadow-manifest.example.json).

## 5. Run the frozen Stage 0 evaluation suite

```bash
python3 scripts/run_shadow_eval.py evals/shadow-v0 --offline
```

The suite scores four labeled slugify cases with a scripted verifier. It does
not call Cloudflare and does not repair candidates. A zero exit means the
harness matched every expected policy. See [`evals/shadow-v0/README.md`](evals/shadow-v0/README.md).

## 6. Read the graph rules before enabling intervention

Start with:

1. `docs/architecture.md`
2. `docs/authority-model.md`
3. `configs/baseline.yaml`
4. `experiments/ablation-matrix.md`

The important V0 rule is: **the verifier never rewrites the artifact**. Luna owns all repairs. Verifier output can only flag a criterion and request Luna reinspection when the policy gate permits it.

## 6. First experiment: shadow mode

Do not enable repair initially.

1. Collect a frozen set of Luna task outputs.
2. Grade them with objective tests or human ground truth.
3. Build compact evidence packets per criterion.
4. Ask the free verifier for score-token probabilities.
5. Measure detection rate, false-positive rate, calibration, and tokens consumed.
6. Choose an intervention threshold only after seeing the ROC/precision-recall tradeoff.

The baseline config intentionally keeps verifier intervention disabled until this phase passes its gates.

## 7. Suggested first implementation target

Once the probe works, implement the smallest Hermes integration in `docs/integration-path.md`:

```text
Luna candidate
  -> deterministic checks
  -> evidence packet
  -> verifier score/logprobs
  -> shadow run record
```

Do **not** begin with MoA, multiple workers, or verifier-driven rewrites. Those are ablations after the single-worker/single-verifier hypothesis is measured.

## Useful files

- `README.md` — project hypothesis and topology.
- `ROADMAP.md` — research milestones.
- `docs/provider-strategy.md` — free provider routing and capability checks.
- `docs/evaluation.md` — HELPED/HARMED/WASTED/MISSED metrics.
- `schemas/` — stable contracts for task, manifest, verifier, and run records.
- `examples/` — minimal task, manifest, and evidence packet examples.
- `scripts/probe_verifier.py` — zero-dependency capability probe.
- `scripts/shadow_orchestrator.py` — automatic Phase 1 shadow CLI and core.
