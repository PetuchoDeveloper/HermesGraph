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

Run normal Hermes/Luna tasks unchanged.

After each candidate:
1. collect objective evidence,
2. build criterion packets,
3. score them with the primary verifier,
4. record what action the gate *would* take,
5. do not alter Luna's result.

This establishes verifier calibration without risking worker degradation.

## Phase 2 - One safe repair loop

Enable a single targeted Luna reinspection when calibrated policy allows it.

Use Hermes native execution/delegation boundaries where useful, but preserve Luna as the worker/repair owner.

Repair flow:

```text
Luna candidate
 -> deterministic evidence
 -> free verifier flag
 -> Luna independently reinspects
 -> deterministic regression guard
 -> affected-criteria re-score
 -> accept or rollback
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
