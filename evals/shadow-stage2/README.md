# Shadow Stage 2 evaluation pack

Frozen one-repair cases. Labels are human-owned. Default `evals/shadow-v0`
does **not** enable repair.

## Cases

| ID | Expected policy | Intervention |
|---|---|---|
| `stage2-helped` | `accept_shadow` | HELPED |
| `stage2-harmed` | `would_reinspect` | HARMED |
| `stage2-wasted-noop` | `would_reinspect` | WASTED |
| `stage2-wasted-still-wrong` | `would_reinspect` | WASTED |
| `stage2-skip-good` | `accept_shadow` | NONE |

`repair/` is copied by the same trusted applier as `candidate/`. A harmful
repair that fails the public tests is rolled back. `stage2-skip-good` has a
repair directory, but the first policy is `accept_shadow`, so repair does
not run.

## Offline run

```bash
python3 scripts/run_shadow_eval.py evals/shadow-stage2 --offline
```
