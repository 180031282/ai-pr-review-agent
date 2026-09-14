# AI PR Review Agent

An agentic, multi-analyzer automated code reviewer for GitHub pull requests. Point it at a real PR (or a local diff, entirely offline) and it fetches the diff, runs it through a battery of static-analysis "tools," synthesizes a structured markdown review with severities and `file:line` references, and can optionally post that review as a comment on the PR.

Built as a portfolio project by **Lahari Dilli** to demonstrate a small, real agentic pipeline: an orchestrator that plans and runs a fixed set of tools over each changed file, aggregates their output, and makes a verdict decision — the same pattern that shows up in larger agentic systems, just scoped down to something you can actually install and run today.

## Why this exists

Human code review time is expensive, and a lot of what reviewers catch first — a hardcoded API key, a raw SQL string built with `+`, an `eval()` that shouldn't be there, a function that grew to 15 branches — is mechanical enough to check automatically. This tool runs those checks before a human ever opens the diff, so:

- Obvious security/quality issues (leaked secrets, SQL-injection-shaped code, dangerous `eval`/`exec`, unsafe `pickle`/`yaml.load`) get caught in seconds, not in review comments days later.
- Reviewers spend their time on design and logic, not on pattern-matching for `os.system(`.
- Every PR gets a consistent, structured report — severities, locations, and concrete suggestions — regardless of who's reviewing.

It is **not** a replacement for a real security scanner (see [Limitations](#limitations)) — it's a fast, zero-config first pass that's genuinely useful in CI today.

## Install

Not published to PyPI (yet) — install from a clone:

```bash
git clone https://github.com/laharidilli/ai-pr-review-agent.git
cd ai-pr-review-agent
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

This installs the `pr-review-agent` console script into `.venv/bin/`. Activate the venv (`source .venv/bin/activate`) or call `.venv/bin/pr-review-agent` directly.

> **If this were published to PyPI**, install would just be `pip install ai-pr-review-agent`. Publishing it is a matter of running `python -m build` (already verified working — see below) and `twine upload dist/*` against a PyPI API token.

## Usage

### Local / offline mode — no GitHub API, no token, no network

This is the primary mode for CI and for trying the tool out. Point it at any unified diff file (`git diff > my.diff`, or a PR diff you downloaded):

```bash
pr-review-agent review --diff-file tests/fixtures/vulnerable.diff
```

### Live GitHub PR mode

```bash
export GITHUB_TOKEN=ghp_your_personal_access_token   # needs `repo` scope to read a private repo; public repos work token-free for reads
pr-review-agent review --repo octocat/hello-world --pr 42
```

Add `--post` to publish the rendered markdown as a comment on the real PR (requires a token with write access):

```bash
pr-review-agent review --repo your-org/your-repo --pr 42 --token "$GITHUB_TOKEN" --post
```

### Other flags

```
pr-review-agent review --help

  --repo TEXT                GitHub repo as 'owner/name', e.g. octocat/hello-world.
  --pr INTEGER                Pull request number.
  --diff-file PATH            Path to a local unified-diff file. Fully offline.
  --token TEXT                GitHub token. Defaults to $GITHUB_TOKEN.
  --post                      Post the rendered review as a PR comment.
  --output TEXT                File to write markdown to. '-' prints to stdout. [default: -]
  --analyzers TEXT            Comma-separated subset of analyzers to run (default: all).
  --api-base TEXT             GitHub API base URL (for GitHub Enterprise Server).
  --fail-on-request-changes   Exit 1 if the verdict is 'request_changes' -- for CI gating.
```

List available analyzers:

```bash
pr-review-agent list-analyzers
```

## Example output

This is the **real, unedited** output of running the tool against [`tests/fixtures/vulnerable.diff`](tests/fixtures/vulnerable.diff) (a synthetic diff with a hardcoded API key, a hardcoded DB password, two SQL-injection-shaped queries, an `eval()`/`exec()` pair, an overly complex function, and six new TODO/FIXME markers):

```bash
$ pr-review-agent review --diff-file tests/fixtures/vulnerable.diff
```

<details>
<summary><strong>Click to expand full markdown output</strong></summary>

```markdown
# 🤖 AI PR Review

### 🛑 Verdict: **Request Changes**

## Executive Summary

This pull request was reviewed against 5 changed files using 6 automated analyzers (secrets, sql_injection, dangerous_calls, complexity, todos, diff_size). Found 14 finding(s): 3 critical, 3 high, 2 medium, 6 low -- issues were found that should be fixed before merging. Highest-priority items: app/config.py:3 (critical); app/utils.py:3 (critical); app/utils.py:8 (critical). 🛑 Recommended verdict: **Request Changes**.

## Summary

- **Files reviewed:** 5
- **Analyzers run:** secrets, sql_injection, dangerous_calls, complexity, todos, diff_size
- **Total findings:** 14

| Severity | Count |
|---|---|
| 🔴 Critical | 3 |
| 🟠 High | 3 |
| 🟡 Medium | 2 |
| 🔵 Low | 6 |
| ℹ️ Info | 0 |

## Findings

### `app/complex.py`

- 🟡 **Medium** (complexity, line 1): `classify` has cyclomatic complexity 12 (rank C); consider breaking this function into smaller pieces.
  - *Suggestion:* Extract branches/loops into helper functions to reduce the number of independent paths through this function.

### `app/config.py`

- 🔴 **Critical** (secrets, line 3): Hardcoded OpenAI-style API key: `API_KEY = "sk-ABCDEFGHIJKLMNOPQRSTUVWX1234567890"`
  - *Suggestion:* Remove the secret from source control, rotate it, and load it from an environment variable or secret manager instead.
- 🟠 **High** (secrets, line 4): Hardcoded database password: `DATABASE_PASSWORD = "SuperSecretPass123"`
  - *Suggestion:* Remove the secret from source control, rotate it, and load it from an environment variable or secret manager instead.

### `app/db.py`

- 🟠 **High** (sql_injection, line 5): SQL query built with string concatenation: `query = "SELECT * FROM users WHERE username = " + username`
  - *Suggestion:* Use parameterized queries / bound parameters (e.g. `cursor.execute('...WHERE id = %s', (id,))`) instead of interpolating values into SQL text.
- 🟠 **High** (sql_injection, line 10): SQL query built with an f-string (use parameterized queries): `return conn.execute(f"SELECT * FROM users WHERE id = {user_id}").fetchone()`
  - *Suggestion:* Use parameterized queries / bound parameters (e.g. `cursor.execute('...WHERE id = %s', (id,))`) instead of interpolating values into SQL text.

### `app/notes.py`

- 🟡 **Medium** (todos, line 7): This PR introduces 6 TODO/FIXME-style markers (threshold: 5). Consider resolving some before merging rather than growing the backlog.
  - *Suggestion:* Triage the new TODOs: fix the quick ones now, file issues for the rest.
- 🔵 **Low** (todos, line 2): New `TODO` marker added: `# TODO: validate items before processing`
  - *Suggestion:* Resolve it before merging, or file a tracked issue.
- 🔵 **Low** (todos, line 3): New `FIXME` marker added: `# FIXME: this does not handle empty lists`
  - *Suggestion:* Resolve it before merging, or file a tracked issue.
- 🔵 **Low** (todos, line 4): New `TODO` marker added: `# TODO: add retry logic`
  - *Suggestion:* Resolve it before merging, or file a tracked issue.
- 🔵 **Low** (todos, line 5): New `HACK` marker added: `# HACK: temporary workaround for API rate limits`
  - *Suggestion:* Resolve it before merging, or file a tracked issue.
- 🔵 **Low** (todos, line 6): New `TODO` marker added: `# TODO: replace with async implementation`
  - *Suggestion:* Resolve it before merging, or file a tracked issue.
- 🔵 **Low** (todos, line 7): New `XXX` marker added: `# XXX: revisit this whole function`
  - *Suggestion:* Resolve it before merging, or file a tracked issue.

### `app/utils.py`

- 🔴 **Critical** (dangerous_calls, line 3): Use of `eval()` can execute arbitrary code: `result = eval(expression)`
  - *Suggestion:* Avoid dynamic execution of strings/untrusted input; use safer, explicit alternatives.
- 🔴 **Critical** (dangerous_calls, line 8): Use of `exec()` can execute arbitrary code: `exec(cmd)`
  - *Suggestion:* Avoid dynamic execution of strings/untrusted input; use safer, explicit alternatives.

---
*Generated by [AI PR Review Agent](https://github.com/laharidilli/ai-pr-review-agent) — analyzers: secrets, sql_injection, dangerous_calls, complexity, todos, diff_size.*
```

</details>

A clean diff (no issues) produces a short **Approve** report instead — see [`tests/fixtures/clean.diff`](tests/fixtures/clean.diff).

If `OPENAI_API_KEY` is set in the environment, the "Executive Summary" paragraph is instead written by an LLM given the same structured findings as context — everything else about the report (verdict logic, findings, severities) is identical either way. **No key is required**; the tool is fully functional, and the entire test suite runs, with zero API keys and zero network access.

## Analyzers

Each analyzer is a small "tool" that looks at one changed file's diff and returns a list of findings (severity, message, `file:line`, suggestion). Run `pr-review-agent list-analyzers` to see this from the CLI.

| Analyzer | Catches |
|---|---|
| `secrets` | Hardcoded AWS keys, GitHub/Slack/OpenAI-style tokens, private key blocks, and generic API-key/password/DB-password literals assigned in source. |
| `sql_injection` | SQL statements built via f-strings, `%` formatting, `.format()`, or string concatenation instead of parameterized queries; `execute()` called with an f-string. |
| `dangerous_calls` | `eval()`, `exec()`, `os.system()`, `subprocess(..., shell=True)`, unsafe `pickle.load(s)`, `yaml.load()` without `SafeLoader`, dynamic `__import__()`. |
| `complexity` | Cyclomatic complexity of newly-added Python functions/methods (via [`radon`](https://github.com/rubik/radon)) above 10/20/30 → medium/high/critical. |
| `todos` | New `TODO`/`FIXME`/`HACK`/`XXX` markers, plus an aggregate warning once a PR introduces more than 5. |
| `diff_size` | Individual files with large diffs (150+/400+/800+ changed lines) that are hard to review well. |

### Verdict logic

The orchestrator maps the aggregated findings to one of three verdicts, mirroring GitHub's own PR review states:

- **Request Changes** — any `critical` finding, or 3+ `high` findings.
- **Comment** — any remaining `high` or `medium` finding.
- **Approve** — only `low`/`info` findings, or none at all.

## GitHub Actions integration

This repository dogfoods itself: [`.github/workflows/pr-review.yml`](.github/workflows/pr-review.yml) runs the agent against every PR opened on this repo and posts the result as a comment. Drop the same file into any other repo to get the same behavior:

```yaml
name: AI PR Review

on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  contents: read
  pull-requests: write
  issues: write

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - name: Check out repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install AI PR Review Agent
        run: pip install -e .

      - name: Run automated PR review
        run: |
          pr-review-agent review \
            --repo "${{ github.repository }}" \
            --pr "${{ github.event.pull_request.number }}" \
            --token "${{ secrets.GITHUB_TOKEN }}" \
            --post \
            --output review.md

      - name: Upload review as a build artifact
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: pr-review
          path: review.md
```

(Swap `pip install -e .` for `pip install ai-pr-review-agent` once/if this is published to PyPI, or `pip install git+https://github.com/laharidilli/ai-pr-review-agent.git` to install straight from GitHub without cloning.)

## Architecture

```
pr_review_agent/
├── cli.py            Click CLI: `review`, `list-analyzers`
├── github_client.py  Thin `requests`-based GitHub REST API wrapper
│                      (PR metadata, diff fetch, comment post)
├── diff_parser.py     Unified-diff text -> FileDiff/Hunk/DiffLine objects
├── analyzers/          One "tool" per module, all sharing the Analyzer interface
│   ├── base.py         Analyzer ABC, Finding, Severity
│   ├── secrets.py
│   ├── sql_injection.py
│   ├── dangerous_calls.py
│   ├── complexity.py
│   ├── todos.py
│   ├── diff_size.py
│   └── __init__.py     REGISTRY + build_analyzers()
├── orchestrator.py    The "agent": runs analyzers over every changed file
│                      (in parallel), aggregates findings, decides a verdict
├── llm.py              Optional LLM executive summary (OPENAI_API_KEY),
│                      deterministic template fallback otherwise
└── report.py           Renders a ReviewResult to markdown
```

**Pipeline:** `github_client` (or a local file) produces raw diff text → `diff_parser` turns it into structured `FileDiff` objects → `orchestrator` runs every applicable analyzer against every changed file (skipping e.g. binary files, or the Python-only `complexity` analyzer on a `.js` file), in parallel via a thread pool → results are aggregated into a `ReviewResult` with a computed `Verdict` → `report` renders that to markdown, optionally with an LLM-written summary → the CLI prints/saves it and, with `--post`, sends it back to GitHub as a PR comment.

Every analyzer only ever looks at the diff itself (never the full repo checkout, never the network), which is what makes `--diff-file` mode fully offline and is also why every analyzer is trivially unit-testable against a fixture diff.

### Adding a new analyzer

The registry pattern makes this a three-step, self-contained change:

1. Create `analyzers/my_check.py`:

   ```python
   from pr_review_agent.analyzers.base import Analyzer, Finding, Severity
   from pr_review_agent.diff_parser import FileDiff

   class MyCheckAnalyzer(Analyzer):
       name = "my_check"
       description = "One-line description shown in `list-analyzers`."

       def analyze(self, file_diff: FileDiff) -> list[Finding]:
           findings = []
           for line in file_diff.added_lines():
               if "something_bad" in line.content:
                   findings.append(
                       Finding(
                           analyzer=self.name,
                           severity=Severity.MEDIUM,
                           file=file_diff.path,
                           line=line.new_lineno,
                           message="Found something_bad",
                           suggestion="Do this instead.",
                       )
                   )
           return findings
   ```

2. Register it in `analyzers/__init__.py`:

   ```python
   from pr_review_agent.analyzers.my_check import MyCheckAnalyzer
   REGISTRY["my_check"] = MyCheckAnalyzer
   ```

3. Add a fixture + test in `tests/test_analyzers.py`.

That's it — the CLI's `--analyzers` flag, `list-analyzers`, and the orchestrator all pick it up automatically, with no other code to touch.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q
```

The test suite (62 tests) is fully offline: `github_client.py` is tested with the [`responses`](https://github.com/getsentry/responses) library, which intercepts `requests` calls at the transport layer and fails any test that tries to make a real HTTP request. Everything else operates purely on fixture diff text under `tests/fixtures/`.

```bash
python -m build   # produces dist/*.whl and dist/*.tar.gz
```

## Limitations

This is a fast, pattern-based first pass, not a replacement for a real SAST tool, a secret-scanning service (e.g. GitHub secret scanning, TruffleHog), or human review:

- Analyzers work on the diff's added lines with regex/heuristic patterns — they don't build an AST or do cross-file/taint analysis (except `complexity`, which does parse added Python with `radon`, best-effort).
- `complexity` can only analyze added lines that are themselves syntactically complete (e.g. a whole new function); a diff that touches a few lines inside an existing large function is skipped rather than guessed at.
- False positives/negatives are possible and expected of a heuristic tool — the value is catching the *obvious* stuff fast and consistently, not being exhaustive.

## License

MIT — see [LICENSE](LICENSE).
