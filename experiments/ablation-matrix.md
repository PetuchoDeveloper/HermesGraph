# V0.2 Ablation Matrix

The first experiments are intentionally Luna-centric. Do not add more workers until we know whether cheap verification improves one capable worker.

| ID | Worker | Deterministic checks | Primary verifier | Independent verifier | Intervention | Purpose |
|---|---|---|---|---|---|---|
| E00 | Luna | no | none | none | none | Raw Luna baseline. |
| E01 | Luna | yes | none | none | hard-check repair only | Value of objective checks. |
| E02 | Luna | yes | discrete GLM judge | none | none | Conventional judge discrimination. |
| E03 | Luna | yes | GLM logprob LAV | none | **shadow only** | Calibrate without risk. |
| E04 | Luna | yes | GLM LAV | none | one targeted Luna reinspection | Core weak-verifier experiment. |
| E05 | Luna | yes | GLM LAV | OpenRouter free on uncertainty | one targeted Luna reinspection | Proposed free graph. |
| E06 | Luna | yes | GLM LAV | OpenRouter free always | one targeted Luna reinspection | Cost of always-on strong verification. |
| E07 | Luna | yes | GLM LAV | OpenRouter free + Cloudflare Gemma tie | one repair | Diversity benefit. |
| E08 | Luna | yes | GLM LAV | none | repair prompt obeys verifier | Measure anchoring harm. |
| E09 | Luna | yes | GLM LAV | none | verifier-resistant repair prompt | Anti-regression prompt value. |
| E10 | Luna | yes | GLM LAV | OpenRouter free | repair, no rollback guard | Measure regression-guard value. |
| E11 | Luna | yes | GLM LAV | OpenRouter free | repair + rollback guard | Full V0.2 graph. |
| E12 | Hermes MoA / N=3 | yes | aggregator | n/a | normal | Multi-agent cost/accuracy control. |
| E13 | Luna | yes | optional Ornith | none | shadow | Local verifier comparison. |

## Minimum run record

```text
run_id
task_id
system_id
seed
worker_model
initial_candidate_hash
final_candidate_hash
initial_objective_outcome
final_objective_outcome
hard_checks_before
hard_checks_after
verifier_model
verifier_prompt_version
score_token_set_version
criterion_scores
criterion_entropy
criterion_margin
intervention_reason
intervention_count
outcome_class: HELPED | HARMED | WASTED | MISSED | NONE
luna_input_tokens
luna_output_tokens
verifier_input_tokens
verifier_output_tokens
provider_quota_usage
latency_by_node
provider_errors
rollback_used
```

## First threshold sweep

Do not sweep on the held-out test set.

Candidate calibration dimensions:
- intervention pass/fail expected-score threshold,
- entropy threshold,
- top-1/top-2 probability margin,
- minimum evidence sufficiency score,
- primary-to-strong escalation threshold,
- risk-class multiplier.

Start with K=1. Only evaluate K=3 on an uncertainty subset.

## Promotion gates

### Shadow -> repair

Require verifier discrimination strong enough that high-confidence failure flags have acceptable precision.

### Repair -> strong escalation

Require positive net verifier lift with bounded HARMED rate.

### Strong escalation -> diversity/fanout

Require evidence that remaining failures are verifier uncertainty/correlation problems rather than worker capability limits.
