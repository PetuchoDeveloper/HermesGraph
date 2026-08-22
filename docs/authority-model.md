# Verifier Authority and Anti-Regression Rules

## Problem

A weak verifier can improve a stronger worker only if false verifier judgments do not gain enough authority to damage otherwise correct work.

The graph therefore treats verification as **error localization**, not delegated solution ownership.

## Authority levels

### A0 - Advisory

Typical source: primary cheap verifier.

Allowed:
- score a criterion,
- flag suspicious evidence,
- request Luna reinspection through the policy gate.

Forbidden:
- rewrite artifact,
- introduce requirements,
- claim final correctness,
- force replacement of a passing candidate.

### A1 - Reinspection trigger

Typical source: calibrated independent verifier or repeated independent agreement.

Allowed:
- require Luna to independently re-check a criterion.

Still forbidden:
- perform the repair itself,
- bypass regression checks.

### A2 - Hard rejection

Typical source: deterministic oracle.

Examples:
- hidden test failure,
- compilation failure,
- schema violation,
- exact constraint mismatch.

A2 may reject immediately because the result is machine-observable.

### A3 - User / task contract

The immutable task contract outranks all verifier interpretations.

## Monotonic artifact rule

Keep every candidate immutable by hash.

A new candidate may replace the current best only if it passes an acceptance comparison appropriate to the task:

```text
no newly failing hard checks
AND targeted defect is resolved or independently rejected as false positive
AND no protected acceptance criterion regresses
AND policy gate accepts the evidence
```

If the repair cannot prove improvement, preserve the previous candidate.

## Verifier-resistant repair prompt

Repairs should say:

```text
A verifier flagged criterion <ID> with confidence <p>.
The verifier may be wrong.
Independently inspect the cited evidence and the task contract.
If the current artifact already satisfies the criterion, preserve it and explain
which evidence invalidates the concern. Otherwise make the smallest repair that
satisfies the criterion without regressing previously passing requirements.
```

This reduces anchoring to a weaker critic.

## False-positive containment

A primary verifier false positive should normally cause one of:

1. a short Luna reinspection that preserves the candidate,
2. strong-verifier escalation,
3. abstention / no action.

It should not cause:
- weaker-model rewriting,
- broad refactors,
- repeated repair loops,
- unbounded debate.

## Intervention cap

Default V0:
- max weak-verifier-triggered Luna reinspections: 1 per criterion,
- max strong-verifier escalation: 1 per criterion,
- max verifier-only loop depth: 0,
- max artifact repair generations: 1 unless a hard check still fails.

## Measuring whether the verifier drags Luna down

Track four separate outcomes:

```text
HELPED:
  Luna initial wrong -> verifier flags -> Luna repair correct

HARMED:
  Luna initial correct -> verifier flags -> Luna repair wrong

WASTED:
  Luna initial correct -> verifier flags -> Luna preserves correct artifact

MISSED:
  Luna initial wrong -> verifier accepts / abstains -> remains wrong
```

Primary metric:

```text
net_verifier_lift = P(HELPED) - P(HARMED)
```

Secondary metrics:
- intervention precision = HELPED / all interventions on initially wrong candidates,
- artifact preservation rate after false flags,
- tokens per HELPED case,
- HARMED rate,
- unnecessary reinspection rate.

The project should not ship the verifier policy if `net_verifier_lift <= 0` on the held-out suite.
