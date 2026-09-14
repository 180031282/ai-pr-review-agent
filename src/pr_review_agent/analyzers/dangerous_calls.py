"""Flags use of dangerous/likely-unsafe built-ins and stdlib calls."""

from __future__ import annotations

import re

from pr_review_agent.analyzers.base import Analyzer, Finding, Severity
from pr_review_agent.diff_parser import FileDiff

_PATTERNS: list[tuple[re.Pattern, str, Severity]] = [
    (
        re.compile(r"(?<![\w.])eval\s*\("),
        "Use of `eval()` can execute arbitrary code",
        Severity.CRITICAL,
    ),
    (
        re.compile(r"(?<![\w.])exec\s*\("),
        "Use of `exec()` can execute arbitrary code",
        Severity.CRITICAL,
    ),
    (
        re.compile(r"os\.system\s*\("),
        "`os.system()` runs a shell command; prefer `subprocess.run([...])`",
        Severity.HIGH,
    ),
    (
        re.compile(r"subprocess\.\w+\([^)]*shell\s*=\s*True"),
        "`subprocess` called with `shell=True` is injection-prone",
        Severity.HIGH,
    ),
    (
        re.compile(r"pickle\.loads?\s*\("),
        "`pickle.load(s)` on untrusted data allows arbitrary code execution",
        Severity.HIGH,
    ),
    (
        re.compile(r"yaml\.load\s*\((?![^)]*Loader\s*=\s*yaml\.SafeLoader)"),
        "`yaml.load()` without `Loader=yaml.SafeLoader` can execute arbitrary code",
        Severity.HIGH,
    ),
    (
        re.compile(r"(?<![\w.])__import__\s*\("),
        "Dynamic `__import__()` call, verify the imported name isn't user-controlled",
        Severity.MEDIUM,
    ),
    (
        re.compile(r"(?<![\w.])input\s*\([^)]*\)\s*.*\beval\("),
        "`eval(input(...))` executes arbitrary user input",
        Severity.CRITICAL,
    ),
]


class DangerousCallsAnalyzer(Analyzer):
    name = "dangerous_calls"
    description = (
        "Flags eval/exec, shell=True, unsafe pickle/yaml loads, and similar "
        "dangerous calls."
    )

    def analyze(self, file_diff: FileDiff) -> list[Finding]:
        findings: list[Finding] = []
        for diff_line in file_diff.added_lines():
            text = diff_line.content
            stripped = text.strip()
            if stripped.startswith("#"):
                continue
            for pattern, message, severity in _PATTERNS:
                if pattern.search(text):
                    findings.append(
                        Finding(
                            analyzer=self.name,
                            severity=severity,
                            file=file_diff.path,
                            line=diff_line.new_lineno,
                            message=f"{message}: `{stripped[:120]}`",
                            suggestion=(
                                "Avoid dynamic execution of strings/untrusted "
                                "input; use safer, explicit alternatives."
                            ),
                        )
                    )
                    break
        return findings
