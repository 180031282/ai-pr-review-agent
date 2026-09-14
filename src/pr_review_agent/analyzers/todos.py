"""Flags TODO/FIXME/HACK/XXX markers, and their accumulation across a PR."""

from __future__ import annotations

import re
import threading

from pr_review_agent.analyzers.base import Analyzer, Finding, Severity
from pr_review_agent.diff_parser import FileDiff

_MARKER_RE = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b\s*:?", re.IGNORECASE)

#: Number of new TODO-style markers in a single PR before we escalate to
#: an aggregate "accumulation" warning.
_ACCUMULATION_THRESHOLD = 5


class TodoAnalyzer(Analyzer):
    """Stateful across a single orchestrator run: reuse *one* instance for
    every file in the PR so it can track the running total and raise an
    "accumulation" finding once the threshold is crossed."""

    name = "todos"
    description = (
        "Flags newly-added TODO/FIXME/HACK/XXX markers, and warns when too "
        "many accumulate in one PR."
    )

    def __init__(self) -> None:
        self._total = 0
        self._accumulation_flagged = False
        self._lock = threading.Lock()

    def analyze(self, file_diff: FileDiff) -> list[Finding]:
        findings: list[Finding] = []
        for diff_line in file_diff.added_lines():
            match = _MARKER_RE.search(diff_line.content)
            if not match:
                continue
            with self._lock:
                self._total += 1
                total = self._total
                should_flag = total > _ACCUMULATION_THRESHOLD and not self._accumulation_flagged
                if should_flag:
                    self._accumulation_flagged = True
            findings.append(
                Finding(
                    analyzer=self.name,
                    severity=Severity.LOW,
                    file=file_diff.path,
                    line=diff_line.new_lineno,
                    message=(
                        f"New `{match.group(1).upper()}` marker added: "
                        f"`{diff_line.content.strip()[:120]}`"
                    ),
                    suggestion="Resolve it before merging, or file a tracked issue.",
                )
            )
            if should_flag:
                findings.append(
                    Finding(
                        analyzer=self.name,
                        severity=Severity.MEDIUM,
                        file=file_diff.path,
                        line=diff_line.new_lineno,
                        message=(
                            f"This PR introduces {total} TODO/FIXME-style "
                            f"markers (threshold: {_ACCUMULATION_THRESHOLD}). "
                            "Consider resolving some before merging rather than "
                            "growing the backlog."
                        ),
                        suggestion=(
                            "Triage the new TODOs: fix the quick ones now, file "
                            "issues for the rest."
                        ),
                    )
                )
        return findings
