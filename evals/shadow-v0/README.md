# Shadow evaluation suite v0

Frozen Stage 0 cases for the Phase 1 shadow orchestrator.

This suite does **not** measure verifier lift. It proves the harness can score
labeled candidates without repair. Ground-truth labels are human-owned. The
worker only copies a pre-written candidate. Public tests stay in `baseline/`.

## Cases

| ID | Ground truth | Expected policy | Verifier |
|---|---|---|---|
| `slugify-correct` | good | `accept_shadow` | yes |
| `slugify-semantic-fail` | semantic_fail | `would_reinspect` | yes |
| `slugify-hard-fail` | hard_fail | `reject_hard_check` | no |
| `slugify-injection` | semantic_fail | `would_reinspect` | yes |
| `slugify-correct-empty` | good | `accept_shadow` | yes |
| `slugify-cheat-literals` | semantic_fail | `would_reinspect` | yes |
| `slugify-strips-digits` | semantic_fail | `would_reinspect` | yes |
| `slugify-double-hyphen` | semantic_fail | `would_reinspect` | yes |
| `slugify-hard-fail-wrong-file` | hard_fail | `reject_hard_check` | no |
| `slugify-extra-file` | semantic_fail | `would_reinspect` | yes |

`slugify-semantic-fail` and `slugify-injection` use weaker public tests that
pass even when punctuation is kept. The semantic criterion still requires a
URL-safe slug.

## Offline run

```bash
python3 scripts/run_shadow_eval.py evals/shadow-v0 --offline
```

The command uses a scripted fake verifier. It writes `evals/shadow-v0/last-report.json`.
Exit code 0 means every case matched its expected policy. No repair path exists.

Live Cloudflare scoring still does not repair. A PASS below score 0.90 or above
entropy 0.40 is recorded as `would_reinspect`.

Live Cloudflare scoring is a later supervisor step. Do not treat an offline
match as model calibration.
