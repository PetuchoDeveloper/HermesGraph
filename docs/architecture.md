# Architecture

## Design objective

Optimize **verified task success per Luna token** while preventing a weaker verifier from becoming an accidental replacement worker.

Priority order:

1. GPT-5.6 Luna performs the task once.
2. deterministic evidence validates everything that can be checked mechanically,
3. a compact free LAV verifier inspects only the remaining semantic criteria,
4. Luna re-inspects only localized high-confidence concerns,
5. an independent stronger free verifier is used only for uncertainty/disagreement,
6. fixed fanout and paid escalation remain opt-in experiments.

## Shared graph state

Do not move a chat transcript through the graph.

```text
GraphState
  task_spec
  budget_state
  provider_state
  candidate
  prior_candidate_hashes[]
  evidence[]
  verifier_results[]
  intervention_log[]
  regression_checks[]
  final_artifact_ref
```

Artifacts and large outputs live by reference. Evidence packets contain only the exact spans required to judge one criterion.

## Node contracts

### 1. Task Contract

Input:
- user objective,
- artifacts/repository state,
- explicit constraints.

Output:
- objective,
- acceptance criteria,
- hard checks,
- semantic criteria,
- risk class,
- evidence requirements.

The task contract is immutable for a run unless the user changes the task.

### 2. Luna Worker

GPT-5.6 Luna owns the actual task.

Input:
- task contract,
- minimal working context,
- available tools,
- worker budget.

Output:

```text
status
artifact_refs
claim_summary
changed_paths
checks_requested
evidence_refs
known_uncertainties
```

Rules:
- do not ask Luna for a long self-critique after finishing,
- do not pass its hidden reasoning to verifiers,
- preserve the first candidate as an immutable baseline for regression analysis.

### 3. Deterministic Evidence Check

Run all available objective checks before any LLM verifier.

Examples:
- tests / hidden tests,
- compilation,
- lint and type checks,
- schema validation,
- exact calculations,
- diff constraints,
- dependency/security scanners,
- citation/source existence checks,
- endpoint or file assertions.

Authority:
- a failed hard check may directly reject the candidate,
- a passing deterministic oracle outranks a conflicting weak LLM opinion unless the LLM identifies a criterion the oracle does not cover.

### 4. Evidence Packet Builder

For each semantic criterion, produce a small independent packet:

```text
criterion_id
criterion_text
relevant_task_constraints
candidate_excerpt_or_artifact_ref
deterministic_evidence
worker_claim_if_relevant
```

Target size should usually be 500-2500 tokens. Do not send the full repository or worker transcript unless the criterion genuinely requires it.

### 5. Primary Free LAV Verifier

Default: Cloudflare GLM-4.7-Flash.

Job:
- evaluate **one criterion at a time**,
- return a score token distribution,
- identify the smallest evidence span supporting the judgment,
- abstain when the packet is insufficient.

It does not:
- write code,
- propose a replacement artifact,
- expand the scope of the task,
- overrule deterministic evidence,
- directly force an artifact mutation.

Suggested ordinal scale after tokenizer capability probing:

```text
0 = definitely fails
1 = probably fails
2 = uncertain / insufficient evidence
3 = probably satisfies
4 = strongly satisfies
```

Do not assume `0..4` are ideal score tokens for every tokenizer. The adapter must verify that the configured labels are represented as stable single-token outputs or choose an alternative token set.

Compute a continuous satisfaction score from returned token probabilities. Preserve entropy/margin as uncertainty features rather than reducing everything to PASS/FAIL.

### 6. Authority / Policy Gate

The gate is deterministic.

Example policy:

```text
if hard_check_failed:
    luna_repair(target=hard_failure)

elif all_semantic_criteria_confidently_pass:
    accept

elif primary_verifier_high_confidence_failure and failure_is_localized:
    luna_reinspect(target=failed_criterion)

elif primary_verifier_uncertain:
    strong_verifier_escalation

elif verifier_disagreement:
    diversity_verifier_or_preserve_worker

elif free_verifiers_unavailable:
    fallback_to_luna_plus_deterministic_policy
```

The gate uses calibrated thresholds from held-out data. Initial thresholds are placeholders only.

### 7. Luna Targeted Reinspection / Repair

The repair packet contains only:
- original criterion,
- relevant task constraint,
- failing deterministic evidence or verifier concern,
- exact artifact spans,
- verifier confidence and evidence reference.

Preferred instruction shape:

```text
Re-evaluate criterion C7 against the evidence below.
The verifier may be wrong. Preserve the current implementation unless you can
independently confirm a defect. If a defect exists, repair only what is needed.
```

This wording is intentional: Luna is not commanded to obey the weaker model.

### 8. Regression Guard

After Luna produces a repair:

1. hash/store the new candidate,
2. re-run changed hard checks,
3. re-run previously passing checks that could be affected,
4. re-score only affected semantic criteria,
5. compare objective outcome with the previous candidate.

A repaired candidate must not replace the previous candidate merely because the verifier likes it more.

### 9. Independent Free Verifier

Preferred baseline: a **pinned OpenRouter `:free` model with verified logprob support**, initially `openai/gpt-oss-20b:free`.

Use only when:
- the primary verifier has high entropy / low margin,
- Luna disputes a primary verifier concern,
- the criterion is high-impact,
- calibration data shows the second model adds useful independent signal.

Do not use `openrouter/free` for reported calibration because it may switch models between calls. Raw probabilities from different models are not interchangeable.

Authority:
- may trigger Luna reinspection only under its own calibrated threshold,
- may not generate the final repair.

OpenRouter free endpoints are volatile. The capability probe must disable the route when the pinned model loses `logprobs`/`top_logprobs` or leaves the free pool.

### 10. Diversity Verifier

Default experiment: Cloudflare Gemma 4 26B A4B.

Use sparingly because it shares the same Cloudflare daily free allocation as GLM. It is a diversity/tie-break experiment, not an independent quota pool.

### 11. Free-Quota / Provider Router

Provider state tracks:
- endpoint health,
- capability probe result,
- logprob support,
- top-logprob maximum,
- request/token/neuron usage,
- reset time,
- model availability,
- recent error rate.

Routing rules:
- never consume a scarce strong-verifier call for an obvious deterministic case,
- reserve a configurable portion of free quota for uncertain/high-value tasks,
- if Cloudflare free quota is exhausted, do not route Cloudflare Gemma as though it were independent,
- OpenRouter is a separate request quota and can be used as cross-provider overflow/escalation,
- if all free verifiers fail, use the configured fail-soft/fail-closed policy by risk class.

### 12. Finalizer

For code/file tasks, the accepted Luna artifact is already final.

Do not add another LLM call merely to rewrite it. User-facing synthesis can be performed by the parent when needed.

## Authority ordering

```text
user requirements
    > objective deterministic oracle
    > accepted artifact state
    > calibrated independent-verifier trigger
    > weak verifier flag
    > worker self-claim
```

The verifier is evidence about correctness, not correctness itself.

## Default failure semantics

### Low/medium risk

If verifier infrastructure is unavailable:

```text
Luna + deterministic checks -> return candidate with verifier_status=unavailable
```

### High risk

Require either:
- an objective oracle,
- calibrated independent-verifier consensus,
- or explicit manual/frontier escalation.

Do not silently treat verifier unavailability as a pass.

## Optional local Ornith node

The home Ornith 35B A3B endpoint is an opportunistic experiment only:

- health-probe before routing,
- zero dependency from the VPS graph,
- useful for local calibration / offline verifier experiments,
- never blocks a run when Tailscale or the home PC is unavailable.
