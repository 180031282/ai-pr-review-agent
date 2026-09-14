from __future__ import annotations

from pr_review_agent.analyzers.base import Analyzer, Finding, Severity
from pr_review_agent.diff_parser import parse_diff
from pr_review_agent.orchestrator import ReviewOrchestrator, Verdict, decide_verdict
from tests.conftest import load_fixture


def _finding(severity: Severity) -> Finding:
    return Finding(analyzer="test", severity=severity, file="f.py", line=1, message="x")


class TestDecideVerdict:
    def test_no_findings_is_approve(self):
        assert decide_verdict([]) == Verdict.APPROVE

    def test_only_low_and_info_is_approve(self):
        findings = [_finding(Severity.LOW), _finding(Severity.INFO)]
        assert decide_verdict(findings) == Verdict.APPROVE

    def test_single_medium_is_comment(self):
        findings = [_finding(Severity.MEDIUM)]
        assert decide_verdict(findings) == Verdict.COMMENT

    def test_single_high_is_comment(self):
        findings = [_finding(Severity.HIGH)]
        assert decide_verdict(findings) == Verdict.COMMENT

    def test_three_high_is_request_changes(self):
        findings = [_finding(Severity.HIGH) for _ in range(3)]
        assert decide_verdict(findings) == Verdict.REQUEST_CHANGES

    def test_single_critical_is_request_changes(self):
        findings = [_finding(Severity.LOW), _finding(Severity.CRITICAL)]
        assert decide_verdict(findings) == Verdict.REQUEST_CHANGES


class _AlwaysFindsOne(Analyzer):
    name = "always_one"
    description = "test analyzer that always returns exactly one finding"

    def analyze(self, file_diff):
        return [
            Finding(
                analyzer=self.name,
                severity=Severity.LOW,
                file=file_diff.path,
                line=1,
                message="found something",
            )
        ]


class TestReviewOrchestrator:
    def test_runs_all_default_analyzers_over_vulnerable_fixture(self):
        file_diffs = parse_diff(load_fixture("vulnerable.diff"))
        orchestrator = ReviewOrchestrator(parallel=False)
        result = orchestrator.review(file_diffs)

        assert result.files_reviewed == 5
        assert len(result.analyzers_run) == 6
        assert result.verdict == Verdict.REQUEST_CHANGES
        assert any(f.severity == Severity.CRITICAL for f in result.findings)

    def test_clean_fixture_yields_approve_and_no_findings(self):
        file_diffs = parse_diff(load_fixture("clean.diff"))
        orchestrator = ReviewOrchestrator(parallel=False)
        result = orchestrator.review(file_diffs)

        assert result.findings == []
        assert result.verdict == Verdict.APPROVE

    def test_custom_analyzer_list_via_names(self):
        file_diffs = parse_diff(load_fixture("secret_leak.diff"))
        orchestrator = ReviewOrchestrator(analyzer_names=["secrets"], parallel=False)
        result = orchestrator.review(file_diffs)

        assert result.analyzers_run == ["secrets"]
        assert len(result.findings) == 2

    def test_unknown_analyzer_name_raises(self):
        import pytest

        with pytest.raises(ValueError):
            ReviewOrchestrator(analyzer_names=["not_a_real_analyzer"])

    def test_parallel_and_sequential_produce_same_findings(self):
        file_diffs = parse_diff(load_fixture("vulnerable.diff"))
        sequential = ReviewOrchestrator(parallel=False).review(file_diffs)
        parallel = ReviewOrchestrator(parallel=True).review(file_diffs)

        def key(f):
            return (f.analyzer, f.file, f.line, f.message)

        assert sorted(sequential.findings, key=key) == sorted(parallel.findings, key=key)

    def test_injected_analyzer_is_used(self):
        file_diffs = parse_diff(load_fixture("clean.diff"))
        orchestrator = ReviewOrchestrator(analyzers=[_AlwaysFindsOne()], parallel=False)
        result = orchestrator.review(file_diffs)

        assert len(result.findings) == 1
        assert result.analyzers_run == ["always_one"]

    def test_binary_files_are_skipped(self):
        diff_text = """\
diff --git a/image.png b/image.png
new file mode 100644
index 0000000..abc1234
Binary files /dev/null and b/image.png differ
"""
        file_diffs = parse_diff(diff_text)
        result = ReviewOrchestrator(parallel=False).review(file_diffs)
        assert result.files_reviewed == 0
        assert result.findings == []
