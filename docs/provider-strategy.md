# Free Verifier Provider Strategy

## Goal

Use **recurring-free hosted inference** for verification so the Hermes research VPS does not depend on the home GPU or a paid verifier API.

Provider capabilities and quotas change. Every adapter must perform a startup capability probe and record the result. Documentation values are planning defaults, not hard-coded truth.

## Primary recurring-free pool: Cloudflare Workers AI

### GLM-4.7-Flash

Logical model:

```text
@cf/zai-org/glm-4.7-flash
```

Current useful properties:
- hosted on Workers AI,
- `logprobs` supported,
- `top_logprobs` supported up to 20,
- 131k context,
- low neuron cost relative to larger models,
- suitable as the default criterion verifier.

Cloudflare currently documents **10,000 Workers AI neurons/day at no charge**, resetting daily. This is the main recurring-free budget for V0.2.

### Gemma 4 26B A4B

Logical model:

```text
@cf/google/gemma-4-26b-a4b-it
```

Current API documentation also exposes `logprobs` and `top_logprobs` up to 20.

Use as:
- model-family diversity experiment,
- tie-breaker inside remaining Cloudflare quota,
- verifier calibration comparison.

Important: GLM and Gemma consume the **same Workers AI free allocation**. They are model diversity, not quota diversity.

### Cloudflare budget policy

- maintain an estimated neuron ledger,
- reserve 20% of the daily allocation for high-uncertainty/high-value criteria,
- avoid repeated sampling on routine criteria,
- stop optional calls before the provider hard limit,
- record observed usage and provider errors.

## Secondary recurring-free pool: OpenRouter pinned free models

OpenRouter currently exposes multiple `:free` models whose API pages advertise logprob support. V0.2 starts with:

```text
openai/gpt-oss-20b:free
```

Other capability-probed candidates may include:

```text
google/gemma-4-26b-a4b-it:free
liquid/lfm-2.5-2.6b:free
```

Use OpenRouter as:
- cross-provider confirmation,
- overflow after Cloudflare quota pressure,
- uncertainty escalation,
- verifier-family ablation.

### Important calibration rule

Do **not** use `openrouter/free` for reported LAV calibration. That router may select different free models. A probability such as `P(pass)=0.90` from model A is not automatically comparable with `0.90` from model B.

Pin the model slug and maintain calibration per:

```text
(model, provider route, verifier prompt version, score token set version)
```

### Current free request budget

OpenRouter currently advertises:
- 50 free-model requests/day on a free account,
- 20 requests/minute,
- a higher 1,000 free-model requests/day ceiling after a one-time $10+ credit purchase.

The **strict zero-spend baseline assumes only 50/day**. The $10 credit state is a separate optional experiment, not required architecture.

Because this is a request budget rather than a token-like pool, OpenRouter calls should normally be reserved for uncertain criteria rather than every criterion.

## Cerebras: benchmark only, not recurring free

Cerebras `gpt-oss-120b` has a useful logprob-capable completions endpoint, but current Cerebras documentation explicitly states there is **no permanently free tier**. The free trial is time/credit bounded ($5 credits expiring after 30 days after payment-method verification).

Therefore Cerebras is useful for:
- short benchmark comparisons,
- measuring whether a much stronger verifier improves the uncertainty branch,
- optional PAYG later.

It is **not** part of V0.2's recurring-free success path.

## Optional local pool: Ornith 35B A3B

The home endpoint is intentionally outside the required path.

Use it for:
- offline ablations,
- verifier strength comparisons,
- extra capacity when reachable over Tailscale.

Health policy:

```text
probe timeout -> mark unavailable -> continue hosted route
```

No retry storm and no blocking dependency.

## Capability probe

Each provider/model adapter must test:

```text
1. endpoint reachable
2. model available
3. endpoint is still free under expected account state
4. logprobs accepted
5. top_logprobs accepted
6. configured score labels appear as usable token alternatives
7. max_completion_tokens/max_tokens=1 works for score mode
8. usage fields are returned
9. rate-limit/quota errors are classified
```

Persist:

```text
provider
model
probe_timestamp
free_status
logprobs_supported
top_logprobs_max
score_token_set
usage_accounting_supported
quota_state
status
```

## Score token calibration

Do not assume numeric labels are identical across tokenizers.

At adapter initialization:
- test candidate labels (`0..4`, `A..E`, or dedicated words),
- prefer five stable single-token labels,
- ensure labels are observable in top-k under controlled prompts,
- version the score token set with the verifier prompt.

Model-specific calibration maps raw expected score + entropy/margin to empirical pass probability.

## Zero-spend failover policy

```text
Cloudflare GLM available + daily budget healthy
    -> primary verification

GLM uncertain or Cloudflare budget reserved/exhausted
    -> pinned OpenRouter :free verifier if request budget remains

Need model diversity while Cloudflare budget remains
    -> Cloudflare Gemma 4 (sparingly)

OpenRouter unavailable / request cap reached
    -> optional local Ornith if healthy

all free routes unavailable
    -> Luna + deterministic fallback for low/medium risk
    -> fail closed / manual policy for high risk
```

Never silently substitute a different verifier model under the same calibration profile.

## Current-source references

- Cloudflare pricing/free allocation: https://developers.cloudflare.com/workers-ai/platform/pricing/
- Cloudflare GLM-4.7-Flash: https://developers.cloudflare.com/workers-ai/models/glm-4.7-flash/
- Cloudflare Gemma 4 26B A4B: https://developers.cloudflare.com/ai/models/%40cf/google/gemma-4-26b-a4b-it/
- OpenRouter free router: https://openrouter.ai/openrouter/free
- OpenRouter GPT-OSS-20B free: https://openrouter.ai/openai/gpt-oss-20b%3Afree/api
- Cerebras rate limits/trial policy: https://inference-docs.cerebras.ai/support/rate-limits
