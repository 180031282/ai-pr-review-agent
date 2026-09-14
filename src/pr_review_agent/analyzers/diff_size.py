"""Warns about large individual files/diffs that are hard to review well."""

from __future__ import annotations

from pr_review_agent.analyzers.base import Analyzer, Finding, Severity
from pr_review_agent.diff_parser import FileDiff

# (changed-line threshold, severity)
_THRESHOLDS: list[tuple[int, Severity]] = [
    (800, Severity.HIGH),
    (400, Severity.MEDIUM),
    (150, Severity.LOW),
]


class DiffSizeAnalyzer(Analyzer):
    name = "diff_size"
    description = "Warns when a single file's diff is large enough to hurt review quality."

    def analyze(self, file_diff: FileDiff) -> list[Finding]:
        changed = file_diff.added_line_count() + file_diff.removed_line_count()
        severity = None
        for threshold, sev in _THRESHOLDS:
            if changed >= threshold:
                severity = sev
                break
        if severity is None:
            return []

        first_line = file_diff.added_lines()[0].new_lineno if file_diff.added_lines() else None
        return [
            Finding(
                analyzer=self.name,
                severity=severity,
                file=file_diff.path,
                line=first_line,
                message=(
                    f"Large diff: {changed} changed lines "
                    f"(+{file_diff.added_line_count()}/-{file_diff.removed_line_count()}) "
                    "in a single file."
                ),
                suggestion=(
                    "Consider splitting this into smaller, focused PRs/commits "
                    "so reviewers can reason about each change independently."
                ),
            )
        ]
