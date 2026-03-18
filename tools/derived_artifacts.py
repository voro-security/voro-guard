#!/usr/bin/env python3
"""Reference runner for the fleet derived-artifact contract."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

import yaml


RUNNER_VERSION = 1
MODES = {"pre-commit": "pre_commit", "pre-push": "pre_push", "ci": "ci"}


class RunnerError(RuntimeError):
    """Raised when runner execution must fail."""


def load_manifest(path: Path) -> dict:
    if not path.exists():
        raise RunnerError(f"manifest not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise RunnerError(f"manifest must be a mapping: {path}")
    if data.get("version") != 1:
        raise RunnerError(f"unsupported manifest version: {data.get('version')!r}")
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise RunnerError("manifest must declare a non-empty artifacts list")
    return data


def repo_root_from(manifest_path: Path) -> Path:
    return manifest_path.resolve().parent.parent


def git_paths(repo_root: Path, args: list[str]) -> set[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def changed_files(repo_root: Path) -> set[str]:
    tracked = git_paths(repo_root, ["diff", "--name-only"])
    staged = git_paths(repo_root, ["diff", "--cached", "--name-only"])
    untracked = git_paths(repo_root, ["ls-files", "--others", "--exclude-standard"])
    return tracked | staged | untracked


def run_cmd(cmd: list[str], cwd: Path, timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
    )


def handle_failure(enforcement: str, message: str) -> None:
    if enforcement == "warn":
        print(f"WARN: {message}")
        return
    raise RunnerError(message)


def topo_sort(artifacts: list[dict]) -> list[dict]:
    by_id = {}
    for artifact in artifacts:
        artifact_id = artifact.get("id")
        if not artifact_id:
            raise RunnerError("artifact missing id")
        if artifact_id in by_id:
            raise RunnerError(f"duplicate artifact id: {artifact_id}")
        by_id[artifact_id] = artifact

    ordered: list[dict] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(artifact_id: str) -> None:
        if artifact_id in visited:
            return
        if artifact_id in visiting:
            raise RunnerError(f"artifact dependency cycle detected at: {artifact_id}")
        artifact = by_id.get(artifact_id)
        if artifact is None:
            raise RunnerError(f"unknown artifact dependency: {artifact_id}")
        visiting.add(artifact_id)
        for dep in artifact.get("depends_on", []) or []:
            visit(dep)
        visiting.remove(artifact_id)
        visited.add(artifact_id)
        ordered.append(artifact)

    for artifact_id in by_id:
        visit(artifact_id)
    return ordered


def resolve_outputs(outputs: list[str], repo_root: Path) -> list[str]:
    resolved = []
    for output in outputs:
        output_path = (repo_root / output).resolve()
        try:
            resolved.append(str(output_path.relative_to(repo_root)))
        except ValueError as exc:
            raise RunnerError(f"output escapes repo root: {output}") from exc
    return resolved


def stage_outputs(repo_root: Path, outputs: list[str]) -> None:
    subprocess.run(["git", "add", "--", *outputs], cwd=repo_root, check=True)


def file_digest(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def execute_artifact(artifact: dict, repo_root: Path, mode: str) -> None:
    enforcement_key = MODES[mode]
    enforcement = (artifact.get("enforcement") or {}).get(enforcement_key)
    if enforcement not in {"autofix", "block", "warn"}:
        raise RunnerError(f"artifact {artifact.get('id')} has invalid enforcement for {mode}")

    for command in (artifact.get("requires") or {}).get("commands", []) or []:
        if shutil.which(command) is None:
            hint = artifact.get("setup_hint")
            message = f"{artifact['id']}: missing required command {command!r}"
            if hint:
                message = f"{message}. {hint}"
            handle_failure(enforcement, message)
            return

    outputs = resolve_outputs(artifact.get("outputs") or [], repo_root)
    timeout_seconds = int(artifact.get("timeout_seconds", 60))
    workdir = repo_root / artifact.get("workdir", ".")
    before = changed_files(repo_root)
    output_digests_before = {output: file_digest(repo_root / output) for output in outputs}

    result = run_cmd(list(artifact["generator"]), workdir, timeout_seconds)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.returncode != 0:
        handle_failure(enforcement, f"{artifact['id']}: generator failed with exit code {result.returncode}")
        return

    validate_cmd = artifact.get("validate")
    if validate_cmd:
        validate_result = run_cmd(list(validate_cmd), workdir, timeout_seconds)
        if validate_result.stdout:
            print(validate_result.stdout, end="")
        if validate_result.stderr:
            print(validate_result.stderr, end="", file=sys.stderr)
        if validate_result.returncode != 0:
            handle_failure(enforcement, f"{artifact['id']}: validate failed with exit code {validate_result.returncode}")
            return

    after = changed_files(repo_root)
    new_changes = after - before
    unsafe_writes = sorted(path for path in new_changes if path not in outputs)
    if unsafe_writes:
        handle_failure(
            enforcement,
            f"{artifact['id']}: wrote undeclared files: {', '.join(unsafe_writes)}",
        )
        return

    changed_outputs = sorted(
        output
        for output in outputs
        if file_digest(repo_root / output) != output_digests_before[output]
    )
    if not changed_outputs:
        print(f"OK: {artifact['id']}")
        return

    if enforcement == "autofix" and artifact.get("auto_stage") is True:
        stage_outputs(repo_root, changed_outputs)
        print(f"UPDATED: {artifact['id']} -> {', '.join(changed_outputs)}")
        return

    message = f"{artifact['id']}: derived artifacts changed: {', '.join(changed_outputs)}"
    handle_failure(enforcement, message)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run derived artifact contract checks")
    parser.add_argument("--mode", choices=sorted(MODES.keys()), required=True)
    parser.add_argument(
        "--manifest",
        default=".voro/derived-artifacts.yaml",
        help="Path to manifest file relative to repo root",
    )
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    manifest = load_manifest(manifest_path)
    repo_root = repo_root_from(manifest_path)

    manifest_runner_version = manifest.get("runner_version")
    if manifest_runner_version != RUNNER_VERSION:
        print(
            f"WARN: manifest runner_version={manifest_runner_version!r} does not match runner version {RUNNER_VERSION}",
            file=sys.stderr,
        )

    try:
        artifacts = topo_sort(manifest["artifacts"])
        for artifact in artifacts:
            execute_artifact(artifact, repo_root, args.mode)
    except RunnerError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
