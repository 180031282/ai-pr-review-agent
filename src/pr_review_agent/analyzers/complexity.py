"""Cyclomatic complexity of newly-added Python code, via `radon`.

Because we only ever have the diff (not a full checkout of the repo),
complexity is computed over the *added* lines of each Python file,
concatenated in order. This works well when a PR adds a self-contained
new function/method (the common case, and exactly what static-analysis-
in-CI needs to catch), and is skipped gracefully when the added lines
don't form parseable Python on their own (e.g. a diff that only touches
a few lines in the middle of an existing function).
"""

from __future__ import annotations

from radon.complexity import cc_rank, cc_visit
from radon.visitors import Function

from pr_review_agent.analyzers.base import Analyzer, Finding, Severity
from pr_review_agent.diff_parser import FileDiff

# Cyclomatic complexity thresholds -> severity.
_THRESHOLDS: list[tuple[int, Severity]] = [
    (30, Severity.CRITICAL),
    (20, Severity.HIGH),
    (10, Severity.MEDIUM),
]


def _severity_for(complexity: int) -> Severity | None:
    for threshold, severity in _THRESHOLDS:
        if complexity > threshold:
            return severity
    return None


class ComplexityAnalyzer(Analyzer):
    name = "complexity"
    description = (
        "Computes cyclomatic complexity of added Python functions/methods "
        "with radon and flags anything above 10."
    )

    def applies_to(self, file_diff: FileDiff) -> bool:
        return not file_diff.is_binary and file_diff.extension == "py"

    def analyze(self, file_diff: FileDiff) -> list[Finding]:
        added = file_diff.added_lines()
        if not added:
            return []

        source = "\n".join(ln.content for ln in added)
        # Map 1-based line number within `source` -> real new-file line number.
        lineno_map = {idx + 1: ln.new_lineno for idx, ln in enumerate(added)}

        try:
            blocks = cc_visit(source)
        except SyntaxError:
            # The added lines alone aren't a syntactically complete unit
            # (e.g. a diff hunk in the middle of an existing function).
            # Skip rather than produce noise/false positives.
            return []

        findings: list[Finding] = []
        for block in blocks:
            severity = _severity_for(block.complexity)
            if severity is None:
                continue
            kind = "method" if isinstance(block, Function) and block.is_method else "function"
            real_line = lineno_map.get(block.lineno, file_diff.added_lines()[0].new_lineno)
            findings.append(
                Finding(
                    analyzer=self.name,
                    severity=severity,
                    file=file_diff.path,
                    line=real_line,
                    message=(
                        f"`{block.name}` has cyclomatic complexity "
                        f"{block.complexity} (rank {cc_rank(block.complexity)}); "
                        f"consider breaking this {kind} into smaller pieces."
                    ),
                    suggestion=(
                        "Extract branches/loops into helper functions to "
                        "reduce the number of independent paths through this "
                        f"{kind}."
                    ),
                )
            )
        return findings
