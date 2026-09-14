"""The "agent": runs analyzer tools over every changed file, aggregates
their findings, and decides an overall review verdict.

This is deliberately a small, explicit agent loop rather than something
LLM-driven: each analyzer is a "tool" with a fixed contract
(``FileDiff -> list[Finding]``), the orchestrator decides which tools run
against which files (skipping binary files, or e.g. skipping the
Python-only complexity analyzer for a ``.js`` file), executes them
(optionally in parallel), and folds the results into one structured
:class:`ReviewResult`. Swapping this loop for an LLM-planned one later
would not require changing any analyzer.
"""

from __future__ import annotations

import enum
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from pr_review_agent.analyzers import Analyzer, Finding, Severity, build_analyzers
from pr_review_agent.diff_parser import FileDiff


class Verdict(str, enum.Enum):
    APPROVE = "approve"
    COMMENT = "comment"
    REQUEST_CHANGES = "request_changes"

    @property
    def label(self) -> str:
        return {
            Verdict.APPROVE: "Approve",
            Verdict.COMMENT: "Comment",
            Verdict.REQUEST_CHANGES: "Request Changes",
        }[self]

    @property
    def emoji(self) -> str:
        return {
            Verdict.APPROVE: "✅",
            Verdict.COMMENT: "💬",
            Verdict.REQUEST_CHANGES: "🛑",
        }[self]


#: 3+ HIGH-severity findings (with no CRITICAL) is treated as severe enough
#: to request changes, same as a single CRITICAL finding.
_HIGH_COUNT_REQUEST_CHANGES_THRESHOLD = 3


@dataclass
class ReviewResult:
    findings: list[Finding]
    verdict: Verdict
    files_reviewed: int
    analyzers_run: list[str]
    severity_counts: dict[Severity, int] = field(default_factory=dict)

    def findings_by_severity(self, severity: Severity) -> list[Finding]:
        return [f for f in self.findings if f.severity == severity]

    def highest_severity(self) -> Severity | None:
        return max((f.severity for f in self.findings), default=None)

    def sorted_findings(self) -> list[Finding]:
        """Worst-first, then by file, then by line."""
        return sorted(
            self.findings,
            key=lambda f: (-f.severity.value, f.file, f.line or 0),
        )


def decide_verdict(findings: list[Finding]) -> Verdict:
    """Deterministic mapping from a set of findings to an overall verdict.

    - Any CRITICAL finding, or 3+ HIGH findings -> request changes.
    - Any remaining HIGH or MEDIUM finding -> comment.
    - Only LOW/INFO findings (or none at all) -> approve.
    """
    if not findings:
        return Verdict.APPROVE

    counts = Counter(f.severity for f in findings)

    if counts.get(Severity.CRITICAL, 0) > 0:
        return Verdict.REQUEST_CHANGES
    if counts.get(Severity.HIGH, 0) >= _HIGH_COUNT_REQUEST_CHANGES_THRESHOLD:
        return Verdict.REQUEST_CHANGES
    if counts.get(Severity.HIGH, 0) > 0 or counts.get(Severity.MEDIUM, 0) > 0:
        return Verdict.COMMENT
    return Verdict.APPROVE


class ReviewOrchestrator:
    """Runs the configured analyzers over a set of file diffs."""

    def __init__(
        self,
        analyzers: list[Analyzer] | None = None,
        analyzer_names: list[str] | None = None,
        parallel: bool = True,
    ) -> None:
        self.analyzers: list[Analyzer] = analyzers or build_analyzers(analyzer_names)
        self.parallel = parallel

    def review(self, file_diffs: list[FileDiff]) -> ReviewResult:
        reviewable = [fd for fd in file_diffs if not fd.is_binary]

        if self.parallel and len(reviewable) > 1:
            with ThreadPoolExecutor(max_workers=min(8, len(reviewable))) as pool:
                per_file_findings = list(pool.map(self._analyze_file, reviewable))
        else:
            per_file_findings = [self._analyze_file(fd) for fd in reviewable]

        all_findings: list[Finding] = [f for group in per_file_findings for f in group]
        verdict = decide_verdict(all_findings)
        severity_counts = dict(Counter(f.severity for f in all_findings))

        return ReviewResult(
            findings=all_findings,
            verdict=verdict,
            files_reviewed=len(reviewable),
            analyzers_run=[a.name for a in self.analyzers],
            severity_counts=severity_counts,
        )

    def _analyze_file(self, file_diff: FileDiff) -> list[Finding]:
        findings: list[Finding] = []
        for analyzer in self.analyzers:
            if not analyzer.applies_to(file_diff):
                continue
            try:
                findings.extend(analyzer.analyze(file_diff))
            except Exception as exc:  # pragma: no cover - defensive
                findings.append(
                    Finding(
                        analyzer=analyzer.name,
                        severity=Severity.INFO,
                        file=file_diff.path,
                        line=None,
                        message=f"Analyzer '{analyzer.name}' failed: {exc}",
                    )
                )
        return findings
