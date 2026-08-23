#!/usr/bin/env python3
"""Author the shadow-v1 evaluation pack: 3 new local families + deepswe-mini.

Human-authored cases (this script is a file-writing aid, not a generator):
ground truth labels, candidates, probes, and expected policies are fixed here
by hand and frozen into evals/. The DeepSWE slice references upstream tasks by
path; its hard checks call the upstream hand-written grader verbatim.
"""
