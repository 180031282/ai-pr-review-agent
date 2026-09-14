from __future__ import annotations

import pytest

from pr_review_agent.diff_parser import parse_diff
from pr_review_agent.llm import generate_executive_summary, template_summary
from pr_review_agent.orchestrator import ReviewOrchestrator
from tests.conftest import load_fixture


@pytest.fixture(autouse=True)
def _no_openai_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def test_generate_executive_summary_uses_template_without_api_key():
    file_diffs = parse_diff(load_fixture("vulnerable.diff"))
    result = ReviewOrchestrator(parallel=False).review(file_diffs)

    summary = generate_executive_summary(result, pr_title="Ship feature X")
    assert summary == template_summary(result, pr_title="Ship feature X")
    assert "Ship feature X" in summary
    assert "Request Changes" in summary


def test_template_summary_clean_diff():
    file_diffs = parse_diff(load_fixture("clean.diff"))
    result = ReviewOrchestrator(parallel=False).review(file_diffs)

    summary = template_summary(result)
    assert "came back clean" in summary
    assert "Approve" in summary


def test_template_summary_mentions_severity_counts():
    file_diffs = parse_diff(load_fixture("vulnerable.diff"))
    result = ReviewOrchestrator(parallel=False).review(file_diffs)

    summary = template_summary(result)
    assert "critical" in summary
    assert str(len(result.findings)) in summary
