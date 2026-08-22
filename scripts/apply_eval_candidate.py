#!/usr/bin/env python3
"""Copy a frozen evaluation candidate into the current worktree."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import sys
from collections.abc import Sequence


class CandidateError(ValueError):
    """Raised when a candidate source or relative path is unsafe."""


def _validate_repo_relative_path(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise CandidateError(f"{label} must be a non-empty repository-relative path")
    slash_path = value.replace("\\", "/")
    if os.path.isabs(value) or slash_path.startswith("/"):
        raise CandidateError(f"{label} must not be absolute")
    if any(part == ".." for part in slash_path.split("/")):
        raise CandidateError(f"{label} must not contain '..' traversal")
    if any(character in slash_path for character in (":", "*", "?", "[", "]")):
        raise CandidateError(f"{label} must be a literal repository path")
    normalized = os.path.normpath(slash_path).replace("\\", "/")
    if normalized in {"", ".", ".."} or normalized.startswith("../"):
        raise CandidateError(f"{label} must name a repository path")
    if ".env" in Path(normalized).parts:
        raise CandidateError(f"{label} must not name or reside inside a .env path")
    return normalized


def _reject_dotenv_path(path: Path, label: str) -> None:
    if ".env" in path.parts:
        raise CandidateError(f"{label} must not name or reside inside a .env path: {path}")


def _candidate_files(candidate_root: Path, relative_paths: Sequence[str] | None) -> list[tuple[str, Path]]:
    if relative_paths is not None:
        entries: list[tuple[str, Path]] = []
        for index, raw_path in enumerate(relative_paths):
            relative = _validate_repo_relative_path(raw_path, f"relative_paths[{index}]")
            source = candidate_root / relative
            if not source.is_file() or source.is_symlink():
                raise CandidateError(f"candidate file does not exist or is a symlink: {relative}")
            entries.append((relative, source))
        return sorted(entries)

    entries = []
    for current, directory_names, file_names in os.walk(candidate_root, topdown=True, followlinks=False):
        current_path = Path(current)
        safe_directories: list[str] = []
        for directory_name in directory_names:
            relative_directory = _validate_repo_relative_path(
                str((current_path / directory_name).relative_to(candidate_root)),
                "candidate directory",
            )
            directory_path = current_path / directory_name
            if directory_path.is_symlink():
                raise CandidateError(f"candidate directory is a symlink: {relative_directory}")
            safe_directories.append(directory_name)
        directory_names[:] = safe_directories
        for file_name in file_names:
            source = current_path / file_name
            relative = _validate_repo_relative_path(
                str(source.relative_to(candidate_root)),
                "candidate file",
            )
            if source.is_symlink() or not source.is_file():
                raise CandidateError(f"candidate file is not a regular file: {relative}")
            entries.append((relative, source))
    return sorted(entries)


def apply_candidate(
    candidate_dir: str | os.PathLike[str],
    destination: str | os.PathLike[str] = ".",
    *,
    relative_paths: Sequence[str] | None = None,
) -> list[str]:
    """Copy candidate files into ``destination`` without following escapes."""
    raw_candidate = Path(candidate_dir)
    _reject_dotenv_path(raw_candidate, "candidate_dir")
    candidate_root = raw_candidate.resolve()
    _reject_dotenv_path(candidate_root, "candidate_dir")
    if not candidate_root.is_dir():
        raise CandidateError(f"candidate_dir does not exist or is not a directory: {candidate_dir}")

    raw_destination = Path(destination)
    _reject_dotenv_path(raw_destination, "destination")
    destination_root = raw_destination.resolve()
    _reject_dotenv_path(destination_root, "destination")
    if not destination_root.is_dir():
        raise CandidateError(f"destination does not exist or is not a directory: {destination}")

    copied: list[str] = []
    for relative, source in _candidate_files(candidate_root, relative_paths):
        target = destination_root / relative
        try:
            target.resolve(strict=False).relative_to(destination_root)
        except ValueError as exc:
            raise CandidateError(f"destination path escapes worktree: {relative}") from exc
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink():
            raise CandidateError(f"destination path is a symlink: {relative}")
        shutil.copyfile(source, target)
        copied.append(relative)
    return copied


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply a frozen evaluation candidate")
    parser.add_argument("candidate_dir", help="candidate directory to copy")
    args = parser.parse_args(argv)
    try:
        copied = apply_candidate(args.candidate_dir, Path.cwd())
    except CandidateError as exc:
        print(f"candidate error: {exc}", file=sys.stderr)
        return 2
    print(f"copied {len(copied)} candidate file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
