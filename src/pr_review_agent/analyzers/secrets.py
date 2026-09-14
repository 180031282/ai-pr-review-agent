"""Detects hardcoded secrets / credentials introduced by a diff."""

from __future__ import annotations

import re

from pr_review_agent.analyzers.base import Analyzer, Finding, Severity
from pr_review_agent.diff_parser import FileDiff

# (compiled pattern, human message, severity)
_PATTERNS: list[tuple[re.Pattern, str, Severity]] = [
    (
        re.compile(r"AKIA[0-9A-Z]{16}"),
        "Hardcoded AWS Access Key ID",
        Severity.CRITICAL,
    ),
    (
        re.compile(r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}"),
        "Hardcoded GitHub token",
        Severity.CRITICAL,
    ),
    (
        re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
        "Hardcoded Slack token",
        Severity.CRITICAL,
    ),
    (
        re.compile(r"sk-[A-Za-z0-9]{20,}"),
        "Hardcoded OpenAI-style API key",
        Severity.CRITICAL,
    ),
    (
        re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
        "Hardcoded private key block",
        Severity.CRITICAL,
    ),
    (
        re.compile(
            r"""(?i)\b(api[_-]?key|secret[_-]?key|access[_-]?token|"""
            r"""client[_-]?secret|auth[_-]?token)\b\s*[:=]\s*"""
            r"""["']([A-Za-z0-9/+_\-\.]{12,})["']"""
        ),
        "Hardcoded API key / token assigned to a variable",
        Severity.HIGH,
    ),
    (
        re.compile(
            r"""(?i)\bpassword\b\s*[:=]\s*["'](?!.*\{)([^"'\s]{4,})["']"""
        ),
        "Hardcoded password literal",
        Severity.HIGH,
    ),
    (
        re.compile(
            r"""(?i)\b(db|database)[_-]?(password|pwd)\b\s*[:=]\s*"""
            r"""["']([^"'\s]{4,})["']"""
        ),
        "Hardcoded database password",
        Severity.HIGH,
    ),
]

# Placeholders that commonly trigger false positives; skip if the matched
# secret text (lowercased) is exactly one of these.
_PLACEHOLDER_VALUES = {
    "changeme",
    "your_api_key",
    "your-api-key",
    "example",
    "xxxxxxxx",
    "insert_key_here",
    "<your-token>",
    "placeholder",
    "test",
    "dummy",
}


class SecretsAnalyzer(Analyzer):
    name = "secrets"
    description = "Flags hardcoded API keys, tokens, passwords, and private keys."

    def analyze(self, file_diff: FileDiff) -> list[Finding]:
        findings: list[Finding] = []
        for diff_line in file_diff.added_lines():
            text = diff_line.content
            stripped = text.strip().strip("'\"").lower()
            if stripped in _PLACEHOLDER_VALUES:
                continue
            for pattern, message, severity in _PATTERNS:
                match = pattern.search(text)
                if not match:
                    continue
                groups = [g for g in match.groups() if g] if match.groups() else []
                if groups and groups[-1].lower() in _PLACEHOLDER_VALUES:
                    continue
                findings.append(
                    Finding(
                        analyzer=self.name,
                        severity=severity,
                        file=file_diff.path,
                        line=diff_line.new_lineno,
                        message=f"{message}: `{text.strip()[:120]}`",
                        suggestion=(
                            "Remove the secret from source control, rotate it, "
                            "and load it from an environment variable or secret "
                            "manager instead."
                        ),
                    )
                )
                break  # one finding per line is enough
        return findings
