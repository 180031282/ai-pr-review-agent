"""Shared types for analyzer "tools".

Each analyzer is a small, focused unit that the orchestrator (the
"agent") invokes once per changed file. Analyzers only ever look at the
diff -- they never need network access or the full checked-out
repository, which is what keeps ``--diff-file`` mode fully offline.
"""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass

from pr_review_agent.diff_parser import FileDiff


class Severity(enum.IntEnum):
    """Ordered so that ``max()`` picks the worse severity."""

    INFO = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

    @property
    def label(self) -> str:
        return self.name.title()

    @property
    def emoji(self) -> str:
        return {
            Severity.INFO: "ℹ️",
            Severity.LOW: "🔵",
            Severity.MEDIUM: "🟡",
            Severity.HIGH: "🟠",
            Severity.CRITICAL: "🔴",
        }[self]


@dataclass(frozen=True)
class Finding:
    """A single issue surfaced by an analyzer."""

    analyzer: str
    severity: Severity
    file: str
    message: str
    line: int | None = None
    suggestion: str | None = None

    def location(self) -> str:
        return f"{self.file}:{self.line}" if self.line else self.file


class Analyzer(ABC):
    """Base class every analyzer tool implements."""

    #: Short machine-friendly identifier, e.g. "secrets".
    name: str = "base"
    #: One-line human-readable description, shown in `--list-analyzers`.
    description: str = ""

    @abstractmethod
    def analyze(self, file_diff: FileDiff) -> list[Finding]:
        """Return findings for a single changed file.

        Implementations should only look at ``file_diff`` (i.e. the diff
        content itself) so that the whole pipeline can run without a
        network connection or a local checkout of the repository.
        """
        raise NotImplementedError

    def applies_to(self, file_diff: FileDiff) -> bool:
        """Cheap pre-filter so the orchestrator can skip irrelevant files
        (e.g. binary files, or files with no added lines)."""
        return not file_diff.is_binary
