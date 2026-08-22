# Evaluation Plan

## Primary question

Can free, weaker LLM-as-a-Verifier nodes improve GPT-5.6 Luna's agentic task success without causing enough false-positive repairs to offset the gain?

## Baselines

All systems run the same tasks, repository snapshots, tool access, and Luna configuration.

| ID | System |
|---|---|
| B0 | Luna alone. |
| B1 | Luna + deterministic checks only. |
| B2 | Luna + deterministic checks + discrete cheap PASS/FAIL judge. |
| B3 | Luna + deterministic checks + Cloudflare GLM LAV, **no repair** (measurement-only). |
| B4 | Luna + GLM LAV + one targeted Luna reinspection/repair. |
| B5 | Luna + GLM primary + pinned OpenRouter free verifier on uncertainty. |
| B6 | Proposed free verifier graph + monotonic regression guard. |
| B7 | Luna + fixed N=3/self-MoA or Hermes MoA cost-tuned control. |
| B8 | Stronger/Fable-class baseline when accessible in the same harness. |

B3 is critical: first measure whether the verifier can discriminate Luna successes/failures **without letting it influence the worker**. Only enable repair after calibration is good enough.

## Evaluation stages

### Stage 0 - Verifier-only calibration

Freeze Luna outputs. Do not let verifiers trigger repairs.

For each candidate:
- determine ground-truth outcome,
- score criteria with GLM,
- score uncertain subset with the pinned OpenRouter free verifier,
- fit calibration thresholds,
- measure discrimination and abstention quality.

Promotion gate before intervention:
- positive ROC-AUC / ranking signal over naive confidence,
- acceptable false-negative rate,
- confidence thresholds with useful precision,
- no assumption that raw probabilities are calibrated across models.

Local Stage 0 harness: `evals/shadow-v0`. Run
`python3 scripts/run_shadow_eval.py evals/shadow-v0 --offline` to score ten
frozen slugify cases without repair. Offline matches prove the harness, not
Cloudflare calibration. A later live pass can reuse the same labels.

### Stage 1 - Shadow intervention

Generate the repair instruction Luna *would* have received but do not mutate the official candidate. Measure expected intervention frequency and cost.

### Stage 2 - Controlled repair

Allow one targeted Luna repair. Preserve both initial and repaired candidates so objective outcome can classify HELPED/HARMED/WASTED/MISSED.

### Stage 3 - Adaptive escalation

Enable the independent OpenRouter free verifier only for primary uncertainty/disagreement.

## Benchmark tiers

### Tier A - Fast objective tasks

Use for threshold tuning:
- small coding fixes with hidden tests,
- exact data transformations,
- schema-constrained outputs,
- repository edits with machine-checkable constraints.

### Tier B - Agentic coding

Candidate suites:
- SWE-Bench Verified subset,
- Terminal-Bench V2 subset,
- curated Hermes repository tasks.

### Tier C - Partially objective tasks

- research with source constraints,
- multi-file architecture changes,
- long-horizon shell workflows,
- reports where factual claims can be checked but quality is partly semantic.

### Tier D - Adversarial verifier tests

Test:
- plausible but incorrect Luna narrative,
- passing shallow tests while requirement is unmet,
- fabricated/stale evidence,
- verifier prompt injection inside artifact text,
- correct Luna artifact paired with misleading evidence,
- tasks where the weak verifier lacks enough context,
- correlated model-family mistakes.

## Core outcome taxonomy

For every verifier intervention, classify:

```text
HELPED: initial Luna candidate wrong, post-intervention candidate correct
HARMED: initial Luna candidate correct, post-intervention candidate wrong
WASTED: initial candidate correct, intervention occurs, final remains correct
MISSED: initial candidate wrong, verifier fails to cause a successful correction
```

## Primary metrics

### Worker improvement

- Luna baseline success rate,
- final graph success rate,
- **net verifier lift** = final success - B1 success,
- HELPED rate,
- HARMED rate,
- repair success rate,
- artifact preservation after false verifier flags.

### Verifier quality

- ROC-AUC / PR-AUC for failure detection,
- Brier score after model-specific calibration,
- expected calibration error,
- negative log loss where applicable,
- abstention precision,
- failure-detection recall at selected intervention precision,
- cross-model disagreement rate.

### Economics

- Luna input/output tokens,
- verifier input/output tokens,
- verifier tokens as % of total,
- free-quota consumption per solved task,
- tokens per HELPED case,
- cost per solved task,
- requests/day sustainable under current free quotas,
- latency added by verification.

### Anti-regression

- HARMED rate,
- newly failing deterministic checks after repair,
- broad-change rate after localized repair request,
- repair rollback rate,
- false-positive reinspection rate.

## Required ablations

1. Luna alone.
2. Luna + deterministic checks.
3. Discrete judge vs logprob verifier.
4. GLM verifier in shadow mode.
5. GLM verifier with repair enabled.
6. Repair prompt with vs without “verifier may be wrong”.
7. Full context vs criterion evidence packet.
8. Raw probability threshold vs calibrated threshold.
9. K=1 vs adaptive repeated verification.
10. GLM alone vs GLM -> pinned OpenRouter free escalation.
11. Same-family vs cross-family verifier where possible.
12. Independent verifier always-on vs uncertainty-only.
13. Monotonic regression guard on vs off.
14. Fixed multi-agent fanout vs verifier-gated Luna.
15. Optional local Ornith verifier vs hosted free verifiers.

## Statistical method

Use paired task-level comparisons.

Report:
- bootstrap 95% confidence intervals,
- McNemar tests for paired binary success,
- bootstrap confidence interval for net verifier lift,
- separate confidence interval for HARMED rate,
- cost/token distributions, not only means.

For stochastic runs, use 3-5 seeds during calibration, then freeze prompts/thresholds before the held-out evaluation.

## V0.2 success gate

Do not proceed to more complex fanout unless:

- `net_verifier_lift > 0` on held-out tasks,
- HARMED <= 1% on objective tasks,
- verifier calls <= 5% of total task tokens,
- OpenRouter uncertainty escalation improves outcome enough to justify its scarce request quota,
- B6 dominates or meaningfully extends B1/B7 on the accuracy-token Pareto frontier.
