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


def test_missing_field_fails():
    body = "## What this does\nA\n"
    with pytest.raises(ValueError):
        parse_pr_body.parse_pr_body(body)
