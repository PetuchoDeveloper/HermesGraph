# Hermes Integration Path

## Goal

Build the Luna + free-verifier policy outside Hermes core first, then move only evidence-backed primitives into Hermes.

## Phase 0 - Provider/capability harness

Implement adapters for:
- Cloudflare Workers AI GLM-4.7-Flash,
- Cloudflare Gemma 4 26B A4B,
- pinned OpenRouter free verifier (initially GPT-OSS-20B),
- optional Cerebras GPT-OSS-120B benchmark adapter,
- optional pinned OpenRouter/free verifier,
- optional local Ornith endpoint.

Each adapter must expose:

```text
probe()
score(criterion_packet)
usage()
quota_state()
```

Normalize returned logprobs into a common `VerifierResult` schema while retaining raw provider data for audits.

## Phase 1 - Luna shadow-verification harness

Run normal Hermes/Luna tasks unchanged. The checked-in
`scripts/shadow_orchestrator.py` is the external, automatic Phase 1 harness:

1. Parse a manifest and TaskSpec before starting the worker.
2. Prove the candidate path is a Git root and reject a dirty baseline unless `allow_dirty_baseline` is explicitly enabled.
3. Reject `.env` manifest, TaskSpec, worktree, output, and candidate paths before content loading.
4. Run the worker and sequential A2 hard checks as argv arrays with bounded output. A timeout terminates the command and its descendants as one process group.
5. Remove Cloudflare credentials from worker, hard-check, and internal Git environments.
6. Capture a deterministic, read-only layered snapshot: staged `HEAD -> index`, unstaged `index -> worktree`, and per-path untracked diffs. Literal `candidate_paths` can limit the scope. Capture does not change the real index, worktree status, or Git object database. Active Git clean filters are rejected before content inspection.
7. Persist the scoped `candidate.diff` and SHA-256 hash. Only a bounded excerpt enters each compact semantic evidence packet; worker stdout and transcripts do not enter packets.
8. Score each packet with Cloudflare GLM at the fixed `https://api.cloudflare.com` account endpoint. Manifest endpoint and header overrides are rejected, account identifiers cannot alter the URL path, and redirects are not followed. Credentials come only from the process environment. Requests use `enable_thinking: false`, exact PASS/FAIL, bounded response bodies, and both score alternatives in the first output-position top-logprobs.
9. Normalize PASS probability, binary entropy, and margin, then persist a raw provider response with authorization fields and configured credential values removed.
10. Record the shadow action without invoking repair: `accept_shadow` for high-confidence semantic PASS (score at least 0.90 and entropy at most 0.40), `would_reinspect` for any confirmed semantic FAIL or low-confidence PASS, deterministic fallback for low/medium provider failure, and manual escalation for high-risk provider failure.

Each run requires a new or empty artifact directory. Failed workers and hard checks receive a best-effort candidate snapshot for audit. Phase 1 never repairs or replaces candidate content.

A local invocation is:

```bash
python3 scripts/shadow_orchestrator.py examples/shadow-manifest.example.json
```

The manifest schema is `schemas/shadow-manifest.schema.json`. Artifacts are
written outside the candidate worktree and include `run-record.json`,
`candidate.diff`, `candidate.json`, `evidence-packets.json`,
`verifier-results.json`, and redacted `provider-response-*.json` files.

This establishes verifier calibration without risking worker degradation.

## Phase 1.5 - Frozen shadow evaluation suite

`evals/shadow-v0` is the local Stage 0 harness. Cases are labeled in advance.
The worker only copies a frozen candidate. Offline mode uses a scripted
verifier. This measures harness behavior and later live discrimination. It
does not enable repair.

```bash
python3 scripts/run_shadow_eval.py evals/shadow-v0 --offline
```

## Phase 1.6 - Shadow intervention instruction

When policy is `would_reinspect`, the runner writes
`reinspect-instruction.md` in the artifact directory. The candidate is not
changed. `repair_invoked` stays false. This measures how often a later
Stage 2 repair would fire and how large the instruction would be.

## Phase 2 - One safe repair loop

Enable a single targeted repair when the manifest sets
`stage2.allow_one_repair` and a `repair.command`. Default manifests do not
repair.

Repair flow:

```text
candidate
 -> deterministic evidence
 -> verifier flag
 -> one repair command
 -> hard-check guard (rollback on fail)
 -> affected-criteria re-score
 -> HELPED / HARMED / WASTED
```

## Phase 3 - Uncertainty escalation

Add the pinned OpenRouter free model as the independent verifier.

Only invoke when the primary verifier's score/entropy/margin lands in a calibrated uncertainty region or Luna disputes the concern. Keep Cerebras as a benchmark-only adapter because its current free access is trial-bounded.

## Phase 4 - Hermes skill

Package the protocol as a reusable Hermes skill once the external harness demonstrates positive net verifier lift.

The skill should enforce:
- artifact-first state,
- criterion packet generation,
- non-authoritative weak verifier behavior,
- one targeted Luna repair,
- quota-aware provider routing,
- regression guard.

## Phase 5 - Native runtime only if justified

Potential Hermes core primitives:
- typed subagent/artifact returns,
- provider-specific verifier slot,
- raw logprob capture,
- quota/token budget sidecar,
- deterministic policy state machine,
- artifact rollback by hash,
- hard per-node token/request caps.

Do not patch core delegation just to reproduce behavior that an external harness or skill can test.

## Hermes primitives to reuse

### `delegate_task`

Useful for isolated challenger/future ablations and for tasks where the parent/worker split is needed. The V0.2 baseline does not require fixed multi-agent fanout.

### `execute_code`

Preferred for:
- deterministic evidence collection,
- test aggregation,
- diff extraction,
- log reduction,
- capability probes,
- benchmark orchestration.

### MoA

Keep as a control condition, not the default graph. Compare Luna + verifier gating against cost-tuned Hermes MoA.

## Configuration boundary

The baseline config uses logical provider/model names. Runtime integration should map these onto whichever Hermes/OpenAI-compatible provider configuration is available without baking credentials into the repository.

Secrets must be supplied through environment/secret management only.
