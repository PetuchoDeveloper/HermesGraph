# Quick start

HermesGraph is currently a **research scaffold**, not a Hermes patch. The fastest useful first step is to prove that your hosted verifier endpoint returns stable token logprobs, then run it in shadow mode against frozen Luna outputs before allowing any verifier-triggered repair.

## 1. Clone

```bash
git clone https://github.com/PetuchoDeveloper/HermesGraph.git
cd HermesGraph
```

Python 3.10+ is enough for the included probe; it uses only the standard library.

## 2. Configure one verifier provider

Copy the environment template and fill only the provider you want to test:

```bash
cp .env.example .env
set -a
. ./.env
set +a
```

Do not commit `.env`; it is ignored.

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

## 4. Read the graph rules before enabling intervention

Start with:

1. `docs/architecture.md`
2. `docs/authority-model.md`
3. `configs/baseline.yaml`
4. `experiments/ablation-matrix.md`

The important V0 rule is: **the verifier never rewrites the artifact**. Luna owns all repairs. Verifier output can only flag a criterion and request Luna reinspection when the policy gate permits it.

## 5. First experiment: shadow mode

Do not enable repair initially.

1. Collect a frozen set of Luna task outputs.
2. Grade them with objective tests or human ground truth.
3. Build compact evidence packets per criterion.
4. Ask the free verifier for score-token probabilities.
5. Measure detection rate, false-positive rate, calibration, and tokens consumed.
6. Choose an intervention threshold only after seeing the ROC/precision-recall tradeoff.

The baseline config intentionally keeps verifier intervention disabled until this phase passes its gates.

## 6. Suggested first implementation target

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
- `schemas/` — stable contracts for task, verifier, and run records.
- `examples/` — minimal task/evidence packets.
- `scripts/probe_verifier.py` — zero-dependency capability probe.
