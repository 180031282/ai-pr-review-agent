from __future__ import annotations

from pr_review_agent.diff_parser import parse_diff
from tests.conftest import load_fixture


def test_parse_diff_empty_string_returns_empty_list():
    assert parse_diff("") == []


def test_parse_secret_leak_fixture_single_new_file():
    text = load_fixture("secret_leak.diff")
    files = parse_diff(text)

    assert len(files) == 1
    fd = files[0]
    assert fd.path == "app/config.py"
    assert fd.is_new is True
    assert fd.is_deleted is False
    assert fd.is_binary is False
    assert fd.extension == "py"


def test_added_lines_have_correct_new_line_numbers():
    text = load_fixture("secret_leak.diff")
    fd = parse_diff(text)[0]

    added = fd.added_lines()
    assert len(added) == 8
    # First added line should be new_lineno == 1 (start of a new file).
    assert added[0].new_lineno == 1
    assert added[0].content == "import os"
    # Line numbers should be strictly increasing by 1 for a contiguous hunk.
    for i in range(1, len(added)):
        assert added[i].new_lineno == added[i - 1].new_lineno + 1


def test_api_key_line_is_captured_at_correct_line_number():
    text = load_fixture("secret_leak.diff")
    fd = parse_diff(text)[0]

    api_key_lines = [ln for ln in fd.added_lines() if ln.content.startswith("API_KEY")]
    assert len(api_key_lines) == 1
    assert api_key_lines[0].new_lineno == 3


def test_sql_injection_fixture_parses_two_functions():
    text = load_fixture("sql_injection.diff")
    fd = parse_diff(text)[0]

    assert fd.path == "app/db.py"
    assert fd.added_line_count() == 10
    assert fd.removed_line_count() == 0


def test_dangerous_eval_fixture():
    text = load_fixture("dangerous_eval.diff")
    fd = parse_diff(text)[0]

    assert fd.path == "app/utils.py"
    contents = [ln.content for ln in fd.added_lines()]
    assert any("eval(expression)" in c for c in contents)
    assert any("exec(cmd)" in c for c in contents)


def test_clean_fixture_has_no_suspicious_markers():
    text = load_fixture("clean.diff")
    fd = parse_diff(text)[0]

    assert fd.path == "app/math_utils.py"
    joined = fd.full_added_text()
    assert "eval(" not in joined
    assert "API_KEY" not in joined


def test_vulnerable_fixture_has_multiple_files():
    text = load_fixture("vulnerable.diff")
    files = parse_diff(text)

    paths = {f.path for f in files}
    assert paths == {
        "app/config.py",
        "app/db.py",
        "app/utils.py",
        "app/complex.py",
        "app/notes.py",
    }


def test_parse_diff_handles_modified_file_with_context_and_removed_lines():
    diff_text = """\
diff --git a/app/greet.py b/app/greet.py
index 1111111..2222222 100644
--- a/app/greet.py
+++ b/app/greet.py
@@ -1,5 +1,6 @@
 def greet(name):
-    return "Hello " + name
+    greeting = f"Hello, {name}!"
+    return greeting


 def farewell(name):
"""
    files = parse_diff(diff_text)
    assert len(files) == 1
    fd = files[0]
    assert fd.old_path == "app/greet.py"
    assert fd.new_path == "app/greet.py"
    assert fd.is_new is False

    removed = fd.removed_lines()
    added = fd.added_lines()
    assert len(removed) == 1
    assert removed[0].content == '    return "Hello " + name'
    assert removed[0].old_lineno == 2

    assert len(added) == 2
    assert added[0].content == '    greeting = f"Hello, {name}!"'
    assert added[0].new_lineno == 2
    assert added[1].new_lineno == 3


def test_parse_diff_handles_deleted_file():
    diff_text = """\
diff --git a/old_module.py b/old_module.py
deleted file mode 100644
index 1111111..0000000
--- a/old_module.py
+++ /dev/null
@@ -1,2 +0,0 @@
-def unused():
-    pass
"""
    files = parse_diff(diff_text)
    assert len(files) == 1
    fd = files[0]
    assert fd.is_deleted is True
    assert fd.path == "old_module.py"
    assert fd.added_line_count() == 0
    assert fd.removed_line_count() == 2


def test_parse_diff_handles_binary_file():
    diff_text = """\
diff --git a/image.png b/image.png
new file mode 100644
index 0000000..abc1234
Binary files /dev/null and b/image.png differ
"""
    files = parse_diff(diff_text)
    assert len(files) == 1
    assert files[0].is_binary is True
