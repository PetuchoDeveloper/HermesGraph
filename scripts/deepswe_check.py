#!/usr/bin/env python3
"""DeepSWE-mini hard check driver (runs OUTSIDE the orchestrator sandbox).

Usage: deepswe_check.py <task_id>

Assumes a running container named hg-ds-<task_id> built from the upstream
task's environment Dockerfile with the upstream test.patch already applied.
Runs grader prepare + test.sh, prints reward.json to stdout.

Exit code 0 iff reward == 1. Any other outcome exits nonzero so the
orchestrator records a hard-check failure (authority A2).
"""
from __future__ import annotations

import json
import subprocess
import sys

CONTAINER_PREFIX = "hg-ds-"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: deepswe_check.py <task_id>", file=sys.stderr)
        return 2
    task_id = argv[1]
    container = CONTAINER_PREFIX + task_id

    def run(args: list[str], timeout: int) -> tuple[int, str]:
        proc = subprocess.run(
            ["sudo", "-n", "docker", "exec", container, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout + proc.stderr

    rc, out = run(
        [
            "bash",
            "-lc",
            "rm -f /logs/verifier/reward.json /logs/verifier/reward.txt; "
            "cd /app && TESTS_DIR=/tests VERIFIER_DIR=/logs/verifier "
            "python3 /tests/grader.py prepare </dev/null && "
            "TESTS_DIR=/tests VERIFIER_DIR=/logs/verifier bash /tests/test.sh",
        ],
        timeout=1500,
    )
    if rc != 0:
        print(f"deepswe_check: verifier exited {rc}\n{out[-2000:]}", file=sys.stderr)
        return 1

    rc, reward_out = run(["cat", "/logs/verifier/reward.json"], timeout=30)
    try:
        reward = json.loads(reward_out.strip())
    except json.JSONDecodeError:
        print(f"deepswe_check: unreadable reward.json: {reward_out!r}", file=sys.stderr)
        return 1

    passed = int(reward.get("reward", -1)) == 1 and int(reward.get("f2p_total", 0)) > 0
    print(json.dumps(reward))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
