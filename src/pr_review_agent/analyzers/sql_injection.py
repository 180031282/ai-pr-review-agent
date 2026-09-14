"""Heuristics for SQL-injection-prone string building.

This is intentionally a heuristic, pattern-based analyzer (not a real SQL
parser / taint tracker) -- it looks for the classic anti-patterns: string
concatenation, f-strings, ``%`` formatting, and ``.format()`` used to
build a string that contains SQL keywords, especially when that string
flows into ``execute(...)``/``executemany(...)``.
"""

from __future__ import annotations

import re

from pr_review_agent.analyzers.base import Analyzer, Finding, Severity
from pr_review_agent.diff_parser import FileDiff

_SQL_KEYWORDS = (
    r"(SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE)\b.*"
    r"(FROM|INTO|TABLE|WHERE|VALUES|SET)"
)

# f-string / .format()/ % containing a SQL statement with an interpolation.
_FSTRING_SQL = re.compile(
    rf"""f["'][^"']*{_SQL_KEYWORDS}[^"']*\{{[^}}]+\}}""", re.IGNORECASE
)
_PERCENT_SQL = re.compile(
    rf"""["'][^"']*{_SQL_KEYWORDS}[^"']*["']\s*%\s*""", re.IGNORECASE
)
_FORMAT_SQL = re.compile(
    rf"""["'][^"']*{_SQL_KEYWORDS}[^"']*["']\s*\.\s*format\(""", re.IGNORECASE
)
# String concatenation building a query: "...SQL..." + something
_CONCAT_SQL = re.compile(
    rf"""["'][^"']*{_SQL_KEYWORDS}[^"']*["']\s*\+\s*\S""", re.IGNORECASE
)
_CONCAT_SQL_REVERSE = re.compile(
    rf"""\S\s*\+\s*["'][^"']*{_SQL_KEYWORDS}[^"']*["']""", re.IGNORECASE
)

# execute()/executemany() called with something that looks interpolated
# (%s style placeholders are the SAFE parametrized form and are ignored).
_EXECUTE_WITH_INTERPOLATION = re.compile(
    r"""\.execute(?:many)?\(\s*f["']""", re.IGNORECASE
)

_ALL_PATTERNS: list[tuple[re.Pattern, str]] = [
    (_FSTRING_SQL, "SQL query built with an f-string (use parameterized queries)"),
    (_PERCENT_SQL, "SQL query built with %-string formatting"),
    (_FORMAT_SQL, "SQL query built with str.format()"),
    (_CONCAT_SQL, "SQL query built with string concatenation"),
    (_CONCAT_SQL_REVERSE, "SQL query built with string concatenation"),
    (_EXECUTE_WITH_INTERPOLATION, "execute() called with an interpolated f-string"),
]


class SqlInjectionAnalyzer(Analyzer):
    name = "sql_injection"
    description = (
        "Flags SQL statements built via string concatenation/formatting "
        "instead of parameterized queries."
    )

    def analyze(self, file_diff: FileDiff) -> list[Finding]:
        findings: list[Finding] = []
        for diff_line in file_diff.added_lines():
            text = diff_line.content
            for pattern, message in _ALL_PATTERNS:
                if pattern.search(text):
                    findings.append(
                        Finding(
                            analyzer=self.name,
                            severity=Severity.HIGH,
                            file=file_diff.path,
                            line=diff_line.new_lineno,
                            message=f"{message}: `{text.strip()[:120]}`",
                            suggestion=(
                                "Use parameterized queries / bound parameters "
                                "(e.g. `cursor.execute('...WHERE id = %s', (id,))`) "
                                "instead of interpolating values into SQL text."
                            ),
                        )
                    )
                    break
        return findings
