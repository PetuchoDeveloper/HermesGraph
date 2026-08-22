# Roadmap

## R0 - Provider capability proof

- [ ] Implement Cloudflare capability probe for GLM-4.7-Flash.
- [ ] Confirm returned `logprobs` / `top_logprobs` shape with one-token score prompts.
- [ ] Test five-token score-label candidates and select stable label set.
- [ ] Implement Cloudflare quota/neuron ledger.
- [ ] Implement pinned OpenRouter `:free` adapter (initially GPT-OSS-20B) and capability probe.
- [ ] Implement Cerebras GPT-OSS-120B benchmark-only adapter (optional trial/PAYG).
- [ ] Implement optional Gemma diversity adapter.
- [ ] Record live provider/model capabilities in a generated report.

Exit: at least one recurring-free hosted verifier produces usable score-token probabilities from the research VPS.

## R1 - Luna shadow benchmark

- [ ] Build 50-task fast objective calibration suite.
- [ ] Run GPT-5.6 Luna baseline.
- [ ] Add deterministic evidence collection.
- [ ] Score frozen Luna candidates with GLM; no interventions.
- [ ] Measure ROC-AUC, PR-AUC, Brier/ECE, entropy, and margin.
- [ ] Fit initial intervention/abstention thresholds on calibration split.

Exit: verifier has useful failure discrimination before it is allowed to influence Luna.

## R2 - Safe intervention

- [ ] Implement authority gate.
- [ ] Implement verifier-resistant Luna reinspection prompt.
- [ ] Implement immutable candidate hashes and rollback.
- [ ] Add one targeted repair loop.
- [ ] Add delta deterministic checks.
- [ ] Classify HELPED/HARMED/WASTED/MISSED per run.

Exit: positive net verifier lift and HARMED <= 1% on held-out objective tasks.

## R3 - Independent free escalation

- [ ] Define uncertainty region from GLM calibration.
- [ ] Invoke the pinned OpenRouter free verifier only in that region.
- [ ] Compare always-on independent verification vs conditional escalation.
- [ ] Measure OpenRouter requests consumed per additional solved task.
- [ ] Test Luna-disputes-verifier branch.

Exit: escalation produces measurable lift per free-quota unit.

## R4 - Diversity and robustness

- [ ] Add Gemma tie-breaker experiment.
- [ ] Add verifier prompt-injection stress tests.
- [ ] Compare same-family/cross-family correlated errors.
- [ ] Add optional Ornith 35B verifier when available.
- [ ] Test provider outage and quota-exhaustion behavior.

## R5 - Hermes integration

- [ ] Package external policy as Hermes skill or wrapper.
- [ ] Add node-level token/quota traces.
- [ ] Compare against cost-tuned Hermes MoA.
- [ ] Compare against fixed N=3 fanout.
- [ ] Identify only the missing Hermes runtime primitives justified by data.

## R6 - Long-horizon evaluation

- [ ] SWE-Bench Verified subset.
- [ ] Terminal-Bench V2 subset.
- [ ] Hermes-native repository task suite.
- [ ] Stronger/Fable-class same-harness comparison when available.
- [ ] Report accuracy-token-cost Pareto frontier.

## R7 - Decide productization

Proceed only if:
- Luna + verifier graph consistently beats Luna + deterministic checks,
- weak-verifier harm remains bounded,
- free quota supports useful daily workload,
- complexity is justified versus simpler retry/self-review strategies.
