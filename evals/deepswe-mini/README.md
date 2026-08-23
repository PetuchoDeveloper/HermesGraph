# deepswe-mini

Narrow slice of the DataCurve DeepSWE benchmark (Apache-2.0; upstream tasks
remain under their own licenses), carved for HermesGraph shadow experiments.

## Scope

- `ipython-session-bundle-replay` (601-line oracle patch, 17 fail-to-pass +
  29 pass-to-pass node ids) — smallest Python task by suite size.
- Candidate additions planned: psd-tools-blend-range-api, httpx-streaming-json-iteration.

## Why this benchmark fits

- Tasks are externally authored (no circular labeling of our own verifier).
- The upstream hand-written grader is deterministic authority A2: it applies
  the candidate, runs held-out suites in Docker, and emits reward.json from
  f2p/p2p whitelists. HermesGraph maps it directly onto its hard-check layer;
  the LAV verifier stays advisory on top.

## Flow

`scripts/deepswe_check.py` + supervisor driver `/home/opc/HermesGraph-runs/run_deepswe_mini.py`
(container named hg-ds-<task>, image built from the upstream environment Dockerfile).

## Baseline result (2026-08-23, GLM-4.7-flash single-shot, no repair)

- reward 0 — f2p 0/17, p2p 29/29 kept green, partial 0.63.
- Model produced one whole-file magic module; missed the required
  IPython.core.sessionbundle module entirely. Hard gate correctly rejected;
  no false accept. Cost: ~1.7k generation tokens.
