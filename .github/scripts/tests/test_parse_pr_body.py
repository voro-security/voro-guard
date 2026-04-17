from __future__ import annotations

import pytest

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import parse_pr_body


def test_happy_path():
    body = """## What this does
A

## Sprint this belongs to
sprint_1.md

## Task this completes
Task A

## What's next
Task B

## Breaking changes
NO
"""
    out = parse_pr_body.parse_pr_body(body)
    assert out["sprint"] == "sprint_1.md"
    assert out["task"] == "Task A"
    assert out["warnings"] == []


def test_missing_fields_fall_back_to_defaults():
    body = "## What this does\nA\n"
    out = parse_pr_body.parse_pr_body(body)
    assert out["what_this_does"] == "A"
    assert out["sprint"] == "NONE"
    assert out["task"] == "NONE"
    assert out["whats_next"] == "NONE"
    assert out["breaking_changes"] == "NONE"
    assert any("Missing PR template fields" in warning for warning in out["warnings"])


def test_missing_what_this_does_falls_back_to_pr_title():
    body = "## Sprint this belongs to\nNONE\n"
    out = parse_pr_body.parse_pr_body(body, pr_title="fix: keep update-status green")
    assert out["what_this_does"] == "fix: keep update-status green"
    assert any("Fell back to PR title" in warning for warning in out["warnings"])
