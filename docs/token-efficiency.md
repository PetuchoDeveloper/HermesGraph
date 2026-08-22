# Token and Free-Quota Efficiency

## Principle

The verifier should spend a small number of tokens to redirect a much more valuable Luna reasoning turn.

## 1. Luna gets one real attempt first

Do not add verification chatter before the worker has produced a candidate.

Default:
- one Luna worker,
- no fixed challenger,
- no always-on advisor fanout.

## 2. Deterministic checks precede LLM verification

Every criterion solved by a test/schema/exact oracle saves verifier context and reduces false positives.

Only unresolved semantic criteria reach the LAV node.

## 3. One criterion per verifier call

Avoid a long general critique.

Preferred packet:

```text
criterion + exact constraints + evidence excerpt + candidate excerpt
```

Target 500-2500 input tokens, one scoring token, optional tiny evidence selector.

## 4. Keep generated verifier output near zero

LAV value is in token probabilities, not prose.

Use:
- `max_completion_tokens: 1` for pure score mode when provider behavior supports it,
- `logprobs: true`,
- maximum useful `top_logprobs` within provider support.

If an evidence citation is needed, make it a separate compact structured field/call only when experiments show the benefit exceeds the tokens.

## 5. Adaptive verification, not fixed K

Start K=1.

Escalate only when:
- score lies near intervention boundary,
- entropy is high,
- margin between likely labels is small,
- Luna disputes a concern,
- task risk is high.

Do not run K=5 by default.

## 6. Independent verifier only on uncertainty

Cloudflare GLM handles routine criteria.

A pinned OpenRouter `:free` verifier is reserved for:
- uncertain GLM scores,
- high-value criteria,
- cross-provider disagreement research.

On a strict free OpenRouter account, the small daily request allowance makes this naturally sparse. This creates an intelligence ladder without paying/fanning out on every criterion.

## 7. Keep quota pools distinct

Cloudflare GLM and Cloudflare Gemma consume the same Workers AI allocation. OpenRouter has a separate request quota.

Reserve Cloudflare quota by policy:

```text
80% routine primary verification
20% uncertainty/tie-break reserve
```

Tune after telemetry.

## 8. Provider fail-soft

If a free verifier is unavailable, do not waste Luna turns repeatedly retrying it.

Classify provider error once, update provider state, and route around it.

## 9. Targeted Luna reinspection

A verifier-triggered Luna turn receives only:
- failed criterion,
- exact evidence,
- relevant artifact spans,
- current hard-check status.

No worker transcript replay.

## 10. Delta verification after repair

Re-run only:
- changed hard checks,
- checks with dependency on changed files,
- affected semantic criteria.

Preserve cached scores for unaffected criteria.

## 11. Cache verifier scores by immutable hashes

Key:

```text
(task_spec_hash,
 criterion_id,
 artifact_hash,
 evidence_hash,
 verifier_model,
 verifier_prompt_version,
 score_token_set_version)
```

Never reuse across different verifier models/calibration profiles.

## 12. Score-token capability probe

Avoid wasting quota on invalid experiments.

At startup verify:
- score labels tokenize as intended,
- requested top-k is honored,
- returned logprobs contain usable alternatives.

## 13. Preserve stable prompt prefixes

Keep verifier system/rubric content byte-stable where provider caching can benefit. Put variable artifact evidence at the tail.

## 14. Bound repair scope

A weak verifier flag should not trigger a repo-wide rewrite.

Prompt Luna to make the smallest change only after independently confirming the concern.

## 15. Quota-aware scheduler

Track expected quota cost before dispatch.

Example priority:

```text
P0 hard-risk uncertainty
P1 failed semantic criterion on expensive Luna task
P2 routine verification
P3 diversity/tie-break experiment
P4 repeated samples / research-only probes
```

Drop lower-priority verifier calls before consuming reserved quota.

## 16. No verifier-generated final artifact

This is both an accuracy and token optimization: the verifier does not spend output tokens re-expressing Luna's work.

## 17. Optional Ornith opportunism

If the home PC is online, it may absorb research verification traffic. The scheduler should treat it as zero-guarantee capacity and never wait on it.
