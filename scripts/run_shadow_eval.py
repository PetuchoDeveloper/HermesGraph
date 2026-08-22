#!/usr/bin/env python3
"""Run the frozen HermesGraph Stage 0 shadow evaluation suite."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Mapping

from shadow_orchestrator import run_manifest


GROUND_TRUTH_LABELS = {"good", "semantic_fail", "hard_fail"}
EXPECTED_POLICIES = {"accept_shadow", "would_reinspect", "reject_hard_check"}


class SuiteError(ValueError):
    """Raised when a frozen shadow suite is malformed or unsafe."""


def _reject_dotenv_path(path: Path, label: str) -> None:
    if ".env" in path.parts:
        raise SuiteError(f"{label} must not name or reside inside a .env path: {path}")


def _read_json(path: Path, label: str) -> Any:
    _reject_dotenv_path(path, label)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SuiteError(f"{label} does not exist: {path}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SuiteError(f"could not read {label}: {path}: {exc}") from exc


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise SuiteError(f"{label} must be a non-empty string")
    return value


def _load_case(case_path: Path) -> dict[str, Any]:
    raw = _read_json(case_path, "case")
    if not isinstance(raw, dict):
        raise SuiteError(f"case must be a JSON object: {case_path}")
    for field in ("id", "family", "ground_truth", "expected_policy", "verifier_should_run"):
        if field not in raw:
            raise SuiteError(f"case missing required field {field}: {case_path}")
    case = dict(raw)
    case_id = _require_string(case["id"], "case.id")
    _require_string(case["family"], "case.family")
    ground_truth = case["ground_truth"]
    if ground_truth not in GROUND_TRUTH_LABELS:
        raise SuiteError(f"case {case_id} has unknown ground_truth: {ground_truth!r}")
    if case["expected_policy"] not in EXPECTED_POLICIES:
        raise SuiteError(f"case {case_id} has unknown expected_policy: {case['expected_policy']!r}")
    if not isinstance(case["verifier_should_run"], bool):
        raise SuiteError(f"case {case_id}.verifier_should_run must be boolean")
    case["case_path"] = case_path
    case["case_dir"] = case_path.parent
    return case



def materialize_case(case: Mapping[str, Any], destination: str | os.PathLike[str]) -> Path:
    """Create a clean throwaway Git repository from a case's frozen baseline."""
    case_dir = Path(case["case_dir"]).resolve()
    _reject_dotenv_path(case_dir, "case")
    baseline_dir = case_dir / "baseline"
    if not baseline_dir.is_dir():
        raise SuiteError(f"case baseline does not exist: {baseline_dir}")

    worktree = Path(destination).resolve()
    _reject_dotenv_path(worktree, "worktree")
    if worktree.exists():
        if not worktree.is_dir() or any(worktree.iterdir()):
            raise SuiteError(f"worktree must be absent or empty: {worktree}")
    else:
        worktree.mkdir(parents=True)

    shutil.copytree(baseline_dir, worktree, dirs_exist_ok=True, symlinks=False)
    environment = dict(os.environ)
    for name in ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "OPENROUTER_API_KEY"):
        environment.pop(name, None)
    environment.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0"})
    commands = (
        ["git", "init", "-q"],
        ["git", "config", "user.email", "shadow-eval@example.invalid"],
        ["git", "config", "user.name", "HermesGraph Shadow Eval"],
        ["git", "add", "--", "."],
        ["git", "commit", "-qm", "frozen baseline"],
    )
    for command in commands:
        subprocess.run(command, cwd=worktree, env=environment, check=True)
    return worktree


def load_suite(path: str | Path) -> dict[str, Any]:
    """Load and validate a frozen suite and all of its case metadata."""
    suite_path = Path(path).resolve()
    raw = _read_json(suite_path, "suite")
    if not isinstance(raw, dict):
        raise SuiteError("suite must be a JSON object")
    suite_id = _require_string(raw.get("suite_id"), "suite.suite_id")
    case_refs = raw.get("cases")
    if not isinstance(case_refs, list) or not case_refs:
        raise SuiteError("suite.cases must be a non-empty array")

    cases: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, case_ref in enumerate(case_refs):
        if not isinstance(case_ref, str) or not case_ref:
            raise SuiteError(f"suite.cases[{index}] must be a non-empty path")
        case_path = Path(case_ref)
        if not case_path.is_absolute():
            case_path = suite_path.parent / case_path
        case_path = case_path.resolve()
        case = _load_case(case_path)
        if case["id"] in seen_ids:
            raise SuiteError(f"duplicate case id: {case['id']}")
        seen_ids.add(case["id"])
        cases.append(case)

    return {
        "suite_id": suite_id,
        "version": raw.get("version", 1),
        "suite_path": suite_path,
        "suite_dir": suite_path.parent,
        "cases": cases,
    }




class ScriptedVerifier:
    """Offline verifier whose verdict is frozen in the case metadata."""

    def __init__(self, verdict: str):
        if verdict not in {"PASS", "FAIL"}:
            raise SuiteError(f"offline verifier verdict must be PASS or FAIL: {verdict!r}")
        self.verdict = verdict
        self.calls: list[dict[str, Any]] = []

    def score(self, packet: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(packet)
        score = 1.0 if self.verdict == "PASS" else 0.0
        return {
            "verdict": self.verdict,
            "normalized_score": score,
            "entropy": 0.0,
            "margin": 1.0,
            "raw_logprobs": {},
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "provider": "offline-fake",
            "model": "frozen-scripted-verifier",
        }


def _candidate_paths(candidate_dir: Path) -> list[str]:
    paths: list[str] = []
    for path in candidate_dir.rglob("*"):
        if path.is_symlink():
            raise SuiteError(f"candidate contains a symlink: {path}")
        if path.is_file():
            relative = path.relative_to(candidate_dir).as_posix()
            if ".env" in Path(relative).parts:
                raise SuiteError(f"candidate contains a .env path: {relative}")
            paths.append(relative)
    if not paths:
        raise SuiteError(f"candidate directory is empty: {candidate_dir}")
    return sorted(paths)


def _verifier_tokens(verifier_result: Mapping[str, Any] | None) -> int:
    if not verifier_result:
        return 0
    usage = verifier_result.get("usage")
    if not isinstance(usage, Mapping):
        return 0
    total = usage.get("total_tokens")
    if isinstance(total, int) and not isinstance(total, bool) and total >= 0:
        return total
    prompt = usage.get("prompt_tokens", 0)
    completion = usage.get("completion_tokens", 0)
    if all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in (prompt, completion)):
        return prompt + completion
    return 0


def run_case(
    case: Mapping[str, Any],
    output_dir: str | os.PathLike[str],
    *,
    verifier: object | None = None,
    offline: bool = True,
) -> dict[str, Any]:
    """Materialize, score, and summarize one frozen case."""
    case_id = _require_string(case.get("id"), "case.id")
    case_dir = Path(case["case_dir"]).resolve()
    task_path = case_dir / "task-spec.json"
    candidate_dir = case_dir / "candidate"
    if not task_path.is_file():
        raise SuiteError(f"case TaskSpec does not exist: {task_path}")
    if not candidate_dir.is_dir():
        raise SuiteError(f"case candidate does not exist: {candidate_dir}")
    candidate_paths = _candidate_paths(candidate_dir)

    artifacts = Path(output_dir).resolve()
    _reject_dotenv_path(artifacts, "output_dir")
    if artifacts.exists():
        if not artifacts.is_dir() or any(artifacts.iterdir()):
            raise SuiteError(f"case output_dir must be absent or empty: {artifacts}")
    else:
        artifacts.mkdir(parents=True)

    if offline and verifier is None:
        verifier = ScriptedVerifier(str(case.get("fake_verdict", "PASS")))

    worker_script = Path(__file__).resolve().with_name("apply_eval_candidate.py")
    with tempfile.TemporaryDirectory(prefix=f"hermesgraph-shadow-{case_id}-") as temp_dir:
        temporary_root = Path(temp_dir)
        worktree = materialize_case(case, temporary_root / "worktree")
        manifest_path = temporary_root / "manifest.json"
        manifest = {
            "run_id": f"shadow-v0-{case_id}",
            "task_spec": str(task_path),
            "worktree": str(worktree),
            "worker": {
                "command": [sys.executable, str(worker_script), str(candidate_dir)],
                "timeout_seconds": 30,
            },
            "hard_checks": [
                {
                    "id": "public-unittest",
                    "command": [sys.executable, "-m", "unittest", "-v"],
                    "timeout_seconds": 30,
                }
            ],
            "candidate_paths": candidate_paths,
            "output_dir": str(artifacts),
            "provider": {"name": "cloudflare-workers-ai"},
        }
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        result = run_manifest(manifest_path, verifier=verifier)

    verifier_results = result.record.get("verifier_results", [])
    first_verifier = verifier_results[0] if verifier_results else None
    summary = {
        "id": case_id,
        "ground_truth": case["ground_truth"],
        "expected_policy": case["expected_policy"],
        "actual_policy": result.policy_action,
        "match": result.policy_action == case["expected_policy"],
        "verifier_called": bool(verifier_results),
        "verdict": first_verifier.get("verdict") if isinstance(first_verifier, dict) else None,
        "normalized_score": first_verifier.get("normalized_score") if isinstance(first_verifier, dict) else None,
        "entropy": first_verifier.get("entropy") if isinstance(first_verifier, dict) else None,
        "margin": first_verifier.get("margin") if isinstance(first_verifier, dict) else None,
        "verifier_tokens": _verifier_tokens(first_verifier if isinstance(first_verifier, dict) else None),
        "repair_invoked": bool(result.record.get("repair_invoked", False)),
        "initial_hash": result.record.get("initial_candidate_hash", ""),
        "final_hash": result.record.get("final_candidate_hash", ""),
        "exit_code": result.exit_code,
        "artifact_dir": str(artifacts),
    }
    (artifacts / "case-summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def _resolve_suite_path(path: str | os.PathLike[str]) -> Path:
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / "suite.json"
    return candidate.resolve()


def build_report(suite: Mapping[str, Any], summaries: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate case summaries into a Stage 0 calibration report."""
    confusion = {"tp": 0, "tn": 0, "fp": 0, "fn": 0}
    hard_fail_short_circuits = 0
    hashes_changed = 0
    repair_invoked = 0
    for summary in summaries:
        if summary.get("repair_invoked"):
            repair_invoked += 1
        if (
            summary.get("initial_hash")
            and summary.get("final_hash")
            and summary["initial_hash"] != summary["final_hash"]
            and summary.get("actual_policy") in {"accept_shadow", "would_reinspect"}
        ):
            hashes_changed += 1
        if summary.get("ground_truth") == "hard_fail" and not summary.get("verifier_called"):
            hard_fail_short_circuits += 1
        if not summary.get("verifier_called"):
            continue
        truth = summary.get("ground_truth")
        policy = summary.get("actual_policy")
        if truth == "semantic_fail" and policy == "would_reinspect":
            confusion["tp"] += 1
        elif truth == "good" and policy == "accept_shadow":
            confusion["tn"] += 1
        elif truth == "good" and policy == "would_reinspect":
            confusion["fp"] += 1
        elif truth == "semantic_fail" and policy == "accept_shadow":
            confusion["fn"] += 1
    matched = sum(1 for summary in summaries if summary.get("match"))
    return {
        "suite_id": suite["suite_id"],
        "mode": "offline",
        "total": len(summaries),
        "matched": matched,
        "all_matched": matched == len(summaries) and bool(summaries),
        "cases": summaries,
        "confusion": confusion,
        "hard_fail_short_circuits": hard_fail_short_circuits,
        "repair_invoked_any": repair_invoked > 0,
        "hashes_changed_any": hashes_changed > 0,
    }


def run_suite(
    suite_path: str | os.PathLike[str],
    *,
    output_root: str | os.PathLike[str],
    report_path: str | os.PathLike[str],
    offline: bool = True,
) -> dict[str, Any]:
    """Run every frozen case and persist a suite report."""
    if not offline:
        raise SuiteError("live Cloudflare scoring is supervisor-only; use --offline")
    suite = load_suite(_resolve_suite_path(suite_path))
    root = Path(output_root).resolve()
    _reject_dotenv_path(root, "output_root")
    report_file = Path(report_path).resolve()
    _reject_dotenv_path(report_file, "report_path")
    root.mkdir(parents=True, exist_ok=True)
    summaries: list[dict[str, Any]] = []
    for case in suite["cases"]:
        case_output = root / str(case["id"])
        summaries.append(run_case(case, case_output, offline=True))
    report = build_report(suite, summaries)
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run the frozen HermesGraph shadow evaluation suite")
    parser.add_argument("suite", help="suite directory or suite.json path")
    parser.add_argument("--offline", action="store_true", default=True, help="use scripted fake verifier")
    parser.add_argument("--live", action="store_true", help="reserved; rejected in this Stage 0 release")
    parser.add_argument("--output", default="evals/shadow-v0/last-report.json", help="report JSON path")
    parser.add_argument("--runs", default="evals/shadow-v0/runs", help="per-case artifact root")
    args = parser.parse_args(argv)
    try:
        if args.live:
            raise SuiteError("live Cloudflare scoring is supervisor-only; use --offline")
        report = run_suite(args.suite, output_root=args.runs, report_path=args.output, offline=True)
    except SuiteError as exc:
        print(f"suite error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"suite_id": report["suite_id"], "matched": report["matched"], "total": report["total"], "all_matched": report["all_matched"]}, indent=2))
    return 0 if report["all_matched"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

