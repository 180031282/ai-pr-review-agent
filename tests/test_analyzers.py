from __future__ import annotations

from pr_review_agent.analyzers.base import Severity
from pr_review_agent.analyzers.complexity import ComplexityAnalyzer
from pr_review_agent.analyzers.dangerous_calls import DangerousCallsAnalyzer
from pr_review_agent.analyzers.diff_size import DiffSizeAnalyzer
from pr_review_agent.analyzers.secrets import SecretsAnalyzer
from pr_review_agent.analyzers.sql_injection import SqlInjectionAnalyzer
from pr_review_agent.analyzers.todos import TodoAnalyzer
from pr_review_agent.diff_parser import parse_diff
from tests.conftest import load_fixture


def _first_file(fixture_name: str):
    return parse_diff(load_fixture(fixture_name))[0]


class TestSecretsAnalyzer:
    def test_detects_api_key_and_password(self):
        fd = _first_file("secret_leak.diff")
        findings = SecretsAnalyzer().analyze(fd)

        assert len(findings) == 2
        by_line = {f.line: f for f in findings}

        assert by_line[3].severity == Severity.CRITICAL
        assert "API key" in by_line[3].message
        assert by_line[3].file == "app/config.py"

        assert by_line[4].severity == Severity.HIGH
        assert "password" in by_line[4].message.lower()

    def test_clean_diff_has_no_secret_findings(self):
        fd = _first_file("clean.diff")
        assert SecretsAnalyzer().analyze(fd) == []

    def test_placeholder_values_are_not_flagged(self):
        diff_text = """\
diff --git a/app/settings.py b/app/settings.py
new file mode 100644
index 0000000..1111111
--- /dev/null
+++ b/app/settings.py
@@ -0,0 +1,1 @@
+api_key = "changeme"
"""
        fd = parse_diff(diff_text)[0]
        assert SecretsAnalyzer().analyze(fd) == []


class TestSqlInjectionAnalyzer:
    def test_detects_concatenation_and_fstring(self):
        fd = _first_file("sql_injection.diff")
        findings = SqlInjectionAnalyzer().analyze(fd)

        assert len(findings) == 2
        assert all(f.severity == Severity.HIGH for f in findings)
        lines = {f.line for f in findings}
        assert lines == {5, 10}

    def test_clean_diff_has_no_sql_findings(self):
        fd = _first_file("clean.diff")
        assert SqlInjectionAnalyzer().analyze(fd) == []

    def test_parameterized_query_is_not_flagged(self):
        diff_text = """\
diff --git a/app/safe_db.py b/app/safe_db.py
new file mode 100644
index 0000000..1111111
--- /dev/null
+++ b/app/safe_db.py
@@ -0,0 +1,2 @@
+def get_user(conn, username):
+    return conn.execute("SELECT * FROM users WHERE username = %s", (username,)).fetchone()
"""
        fd = parse_diff(diff_text)[0]
        assert SqlInjectionAnalyzer().analyze(fd) == []


class TestDangerousCallsAnalyzer:
    def test_detects_eval_and_exec(self):
        fd = _first_file("dangerous_eval.diff")
        findings = DangerousCallsAnalyzer().analyze(fd)

        assert len(findings) == 2
        assert all(f.severity == Severity.CRITICAL for f in findings)
        lines = {f.line for f in findings}
        assert lines == {3, 8}

    def test_clean_diff_has_no_dangerous_call_findings(self):
        fd = _first_file("clean.diff")
        assert DangerousCallsAnalyzer().analyze(fd) == []

    def test_commented_out_eval_is_not_flagged(self):
        diff_text = """\
diff --git a/app/note.py b/app/note.py
new file mode 100644
index 0000000..1111111
--- /dev/null
+++ b/app/note.py
@@ -0,0 +1,1 @@
+# eval(user_input) -- removed, do not re-add
"""
        fd = parse_diff(diff_text)[0]
        assert DangerousCallsAnalyzer().analyze(fd) == []

    def test_shell_true_is_flagged(self):
        diff_text = """\
diff --git a/app/run.py b/app/run.py
new file mode 100644
index 0000000..1111111
--- /dev/null
+++ b/app/run.py
@@ -0,0 +1,1 @@
+subprocess.run(cmd, shell=True)
"""
        fd = parse_diff(diff_text)[0]
        findings = DangerousCallsAnalyzer().analyze(fd)
        assert len(findings) == 1
        assert findings[0].severity == Severity.HIGH


class TestComplexityAnalyzer:
    def test_complex_function_in_vulnerable_fixture_is_flagged(self):
        files = parse_diff(load_fixture("vulnerable.diff"))
        complex_file = next(f for f in files if f.path == "app/complex.py")
        findings = ComplexityAnalyzer().analyze(complex_file)

        assert len(findings) == 1
        assert findings[0].severity in (Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL)
        assert "classify" in findings[0].message

    def test_clean_diff_has_no_complexity_findings(self):
        fd = _first_file("clean.diff")
        assert ComplexityAnalyzer().analyze(fd) == []

    def test_non_python_file_is_skipped(self):
        diff_text = """\
diff --git a/app/script.js b/app/script.js
new file mode 100644
index 0000000..1111111
--- /dev/null
+++ b/app/script.js
@@ -0,0 +1,1 @@
+function noop() {}
"""
        fd = parse_diff(diff_text)[0]
        analyzer = ComplexityAnalyzer()
        assert analyzer.applies_to(fd) is False


class TestTodoAnalyzer:
    def test_detects_todo_fixme_hack_xxx_markers(self):
        files = parse_diff(load_fixture("vulnerable.diff"))
        notes_file = next(f for f in files if f.path == "app/notes.py")

        analyzer = TodoAnalyzer()
        findings = analyzer.analyze(notes_file)

        marker_findings = [f for f in findings if f.severity == Severity.LOW]
        assert len(marker_findings) == 6

    def test_accumulation_warning_once_threshold_crossed(self):
        files = parse_diff(load_fixture("vulnerable.diff"))
        notes_file = next(f for f in files if f.path == "app/notes.py")

        analyzer = TodoAnalyzer()
        findings = analyzer.analyze(notes_file)

        accumulation_findings = [f for f in findings if f.severity == Severity.MEDIUM]
        assert len(accumulation_findings) == 1
        assert "6 TODO/FIXME-style markers" in accumulation_findings[0].message

    def test_clean_diff_has_no_todo_findings(self):
        fd = _first_file("clean.diff")
        assert TodoAnalyzer().analyze(fd) == []


class TestDiffSizeAnalyzer:
    def test_small_fixture_diffs_are_not_flagged(self):
        for name in ("secret_leak.diff", "sql_injection.diff", "dangerous_eval.diff", "clean.diff"):
            fd = _first_file(name)
            assert DiffSizeAnalyzer().analyze(fd) == []

    def test_large_diff_is_flagged(self):
        added = "\n".join(f"+line {i}" for i in range(200))
        diff_text = f"""\
diff --git a/app/big.py b/app/big.py
new file mode 100644
index 0000000..1111111
--- /dev/null
+++ b/app/big.py
@@ -0,0 +1,200 @@
{added}
"""
        fd = parse_diff(diff_text)[0]
        findings = DiffSizeAnalyzer().analyze(fd)
        assert len(findings) == 1
        assert findings[0].severity == Severity.LOW
