from __future__ import annotations

import subprocess
import sys

import pytest
from click.testing import CliRunner

from pr_review_agent.cli import cli
from tests.conftest import FIXTURES_DIR


@pytest.fixture(autouse=True)
def _no_openai_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)


def test_cli_review_diff_file_exits_zero_and_prints_markdown():
    runner = CliRunner()
    diff_path = str(FIXTURES_DIR / "vulnerable.diff")
    result = runner.invoke(cli, ["review", "--diff-file", diff_path, "--output", "-"])

    assert result.exit_code == 0, result.output
    assert "AI PR Review" in result.output
    assert "Request Changes" in result.output
    assert "app/config.py" in result.output
    assert "verdict=request_changes" in result.output


def test_cli_review_clean_diff_is_approve():
    runner = CliRunner()
    diff_path = str(FIXTURES_DIR / "clean.diff")
    result = runner.invoke(cli, ["review", "--diff-file", diff_path, "--output", "-"])

    assert result.exit_code == 0, result.output
    assert "Verdict: **Approve**" in result.output


def test_cli_review_writes_to_output_file(tmp_path):
    runner = CliRunner()
    diff_path = str(FIXTURES_DIR / "secret_leak.diff")
    out_path = tmp_path / "review.md"
    result = runner.invoke(
        cli, ["review", "--diff-file", diff_path, "--output", str(out_path)]
    )

    assert result.exit_code == 0, result.output
    assert out_path.exists()
    content = out_path.read_text()
    assert "AI PR Review" in content


def test_cli_review_requires_repo_and_pr_or_diff_file():
    runner = CliRunner()
    result = runner.invoke(cli, ["review"])

    assert result.exit_code != 0
    assert "diff-file" in result.output or "repo" in result.output


def test_cli_review_post_with_diff_file_is_rejected():
    runner = CliRunner()
    diff_path = str(FIXTURES_DIR / "clean.diff")
    result = runner.invoke(cli, ["review", "--diff-file", diff_path, "--post"])

    assert result.exit_code != 0
    assert "--post" in result.output


def test_cli_review_unknown_analyzer_errors():
    runner = CliRunner()
    diff_path = str(FIXTURES_DIR / "clean.diff")
    result = runner.invoke(
        cli, ["review", "--diff-file", diff_path, "--analyzers", "not_real"]
    )

    assert result.exit_code != 0
    assert "Unknown analyzer" in result.output


def test_cli_review_fail_on_request_changes_flag():
    runner = CliRunner()
    diff_path = str(FIXTURES_DIR / "vulnerable.diff")
    result = runner.invoke(
        cli,
        ["review", "--diff-file", diff_path, "--output", "-", "--fail-on-request-changes"],
    )
    assert result.exit_code == 1


def test_cli_list_analyzers():
    runner = CliRunner()
    result = runner.invoke(cli, ["list-analyzers"])

    assert result.exit_code == 0
    assert "secrets:" in result.output
    assert "sql_injection:" in result.output


def test_cli_as_subprocess_entrypoint():
    """Exercises the actual installed console-script entry point (main())
    as a real subprocess, complementing the in-process CliRunner tests."""
    diff_path = str(FIXTURES_DIR / "clean.diff")
    proc = subprocess.run(
        [sys.executable, "-m", "pr_review_agent.cli", "review", "--diff-file", diff_path],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert "AI PR Review" in proc.stdout
