"""Parser for unified diff / ``git diff`` text.

Turns the raw text of a unified diff (as produced by ``git diff``, or
returned by the GitHub REST API when requesting a PR with
``Accept: application/vnd.github.v3.diff``) into a small object model that
the analyzers can walk over: a list of :class:`FileDiff`, each holding a
list of :class:`Hunk`, each holding a list of :class:`DiffLine`.

Only line-oriented information is kept; the parser doesn't try to
understand the language of the file being diffed. That's left to the
analyzers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_DIFF_GIT_RE = re.compile(r"^diff --git a/(?P<a>.*) b/(?P<b>.*)$")
_HUNK_HEADER_RE = re.compile(
    r"^@@ -(?P<old_start>\d+)(,(?P<old_count>\d+))? "
    r"\+(?P<new_start>\d+)(,(?P<new_count>\d+))? @@"
)


@dataclass
class DiffLine:
    """A single line inside a diff hunk."""

    type: str  # "add", "del", or "context"
    content: str
    new_lineno: int | None = None
    old_lineno: int | None = None

    @property
    def is_added(self) -> bool:
        return self.type == "add"

    @property
    def is_removed(self) -> bool:
        return self.type == "del"


@dataclass
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[DiffLine] = field(default_factory=list)


@dataclass
class FileDiff:
    old_path: str | None
    new_path: str | None
    is_new: bool = False
    is_deleted: bool = False
    is_binary: bool = False
    hunks: list[Hunk] = field(default_factory=list)

    @property
    def path(self) -> str:
        """The most relevant path to report findings against."""
        if self.is_deleted:
            return self.old_path or self.new_path or "<unknown>"
        return self.new_path or self.old_path or "<unknown>"

    @property
    def extension(self) -> str:
        return Path(self.path).suffix.lstrip(".")

    def added_lines(self) -> list[DiffLine]:
        return [ln for h in self.hunks for ln in h.lines if ln.is_added]

    def removed_lines(self) -> list[DiffLine]:
        return [ln for h in self.hunks for ln in h.lines if ln.is_removed]

    def all_lines(self) -> list[DiffLine]:
        return [ln for h in self.hunks for ln in h.lines]

    def added_line_count(self) -> int:
        return len(self.added_lines())

    def removed_line_count(self) -> int:
        return len(self.removed_lines())

    def full_added_text(self) -> str:
        """Concatenate all added lines' content, useful for pattern search
        that needs to run over a whole file's added content at once."""
        return "\n".join(ln.content for ln in self.added_lines())


def parse_diff(text: str) -> list[FileDiff]:
    """Parse unified diff text into a list of :class:`FileDiff`.

    Tolerant of the common variations produced by ``git diff`` and the
    GitHub API: file mode lines, rename lines, "Binary files ... differ",
    and "\\ No newline at end of file" markers are all handled gracefully
    (ignored where they don't carry line-level information).
    """
    if not text:
        return []

    lines = text.splitlines()
    files: list[FileDiff] = []
    current: FileDiff | None = None
    current_hunk: Hunk | None = None
    old_lineno = 0
    new_lineno = 0

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]

        m = _DIFF_GIT_RE.match(line)
        if m:
            if current is not None:
                files.append(current)
            current = FileDiff(old_path=m.group("a"), new_path=m.group("b"))
            current_hunk = None
            i += 1
            continue

        if current is None:
            # Stray content before any "diff --git" header (e.g. a diff
            # produced without git headers). Start an implicit file using
            # the classic "--- a/x" / "+++ b/x" headers below.
            if line.startswith("--- ") or line.startswith("+++ "):
                current = FileDiff(old_path=None, new_path=None)
            else:
                i += 1
                continue

        if line.startswith("new file mode"):
            current.is_new = True
            i += 1
            continue
        if line.startswith("deleted file mode"):
            current.is_deleted = True
            i += 1
            continue
        if line.startswith("Binary files ") and line.endswith("differ"):
            current.is_binary = True
            i += 1
            continue
        if line.startswith("--- "):
            path = line[4:].strip()
            if path != "/dev/null":
                current.old_path = _strip_prefix(path)
            i += 1
            continue
        if line.startswith("+++ "):
            path = line[4:].strip()
            if path != "/dev/null":
                current.new_path = _strip_prefix(path)
            else:
                current.is_deleted = True
            i += 1
            continue

        hm = _HUNK_HEADER_RE.match(line)
        if hm:
            old_start = int(hm.group("old_start"))
            old_count = int(hm.group("old_count") or "1")
            new_start = int(hm.group("new_start"))
            new_count = int(hm.group("new_count") or "1")
            current_hunk = Hunk(
                old_start=old_start,
                old_count=old_count,
                new_start=new_start,
                new_count=new_count,
            )
            current.hunks.append(current_hunk)
            old_lineno = old_start
            new_lineno = new_start
            i += 1
            continue

        if current_hunk is not None and line.startswith("\\"):
            # "\ No newline at end of file": no line-number information.
            i += 1
            continue

        if current_hunk is not None and line[:1] in ("+", "-", " "):
            tag = line[0]
            content = line[1:]
            if tag == "+":
                current_hunk.lines.append(
                    DiffLine(type="add", content=content, new_lineno=new_lineno)
                )
                new_lineno += 1
            elif tag == "-":
                current_hunk.lines.append(
                    DiffLine(type="del", content=content, old_lineno=old_lineno)
                )
                old_lineno += 1
            else:
                current_hunk.lines.append(
                    DiffLine(
                        type="context",
                        content=content,
                        new_lineno=new_lineno,
                        old_lineno=old_lineno,
                    )
                )
                old_lineno += 1
                new_lineno += 1
            i += 1
            continue

        # Any other line (e.g. "index abc123..def456 100644") is metadata
        # we don't need.
        i += 1

    if current is not None:
        files.append(current)

    return files


def _strip_prefix(path: str) -> str:
    """Strip the leading ``a/`` or ``b/`` that git puts on diff paths."""
    if path.startswith("a/") or path.startswith("b/"):
        return path[2:]
    return path
