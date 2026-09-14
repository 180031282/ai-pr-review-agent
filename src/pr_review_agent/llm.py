"""Executive summary generation.

If ``OPENAI_API_KEY`` is set in the environment, the executive summary at
the top of the review is written by an LLM given the structured findings
as context. If it is not set (the default, and what the test suite
always exercises), a deterministic, template-based summary is
generated instead. The rest of the tool (analyzers, verdict, per-finding
detail) is 100% identical either way: the LLM is decoration on top of a
tool that is fully useful without it.
"""

from __future__ import annotations

import os

from pr_review_agent.analyzers.base import Finding, Severity
from pr_review_agent.orchestrator import ReviewResult, Verdict

_VERDICT_BLURB = {
    Verdict.APPROVE: "no blocking issues were found",
    Verdict.COMMENT: "some issues are worth a look before merging",
    Verdict.REQUEST_CHANGES: "issues were found that should be fixed before merging",
}


def generate_executive_summary(result: ReviewResult, pr_title: str | None = None) -> str:
    """Return a short natural-language summary of the review.

    Uses the OpenAI API when ``OPENAI_API_KEY`` is set; otherwise falls
    back to :func:`template_summary`. Any failure talking to the API
    (network error, bad key, missing ``openai`` package, etc.) also falls
    back to the template so the tool never hard-fails because of the
    optional LLM step.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return template_summary(result, pr_title)

    try:
        return _openai_summary(result, pr_title, api_key)
    except Exception:
        # Never let the optional LLM enhancement break the core tool.
        return template_summary(result, pr_title)


def template_summary(result: ReviewResult, pr_title: str | None = None) -> str:
    """Deterministic, zero-dependency executive summary."""
    subject = f'"{pr_title}"' if pr_title else "This pull request"
    counts = result.severity_counts
    n_findings = len(result.findings)

    if n_findings == 0:
        return (
            f"{subject} was reviewed against {result.files_reviewed} changed "
            f"file(s) using {len(result.analyzers_run)} automated analyzers "
            f"and came back clean: no issues found. {result.verdict.emoji} "
            f"Recommended verdict: **{result.verdict.label}**."
        )

    parts = []
    for severity in (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO):
        c = counts.get(severity, 0)
        if c:
            parts.append(f"{c} {severity.label.lower()}")
    counts_str = ", ".join(parts)

    blurb = _VERDICT_BLURB[result.verdict]
    files_word = "file" if result.files_reviewed == 1 else "files"

    top = result.sorted_findings()[:3]
    top_lines = "; ".join(f"{f.location()} ({f.severity.label.lower()})" for f in top)

    return (
        f"{subject} was reviewed against {result.files_reviewed} changed "
        f"{files_word} using {len(result.analyzers_run)} automated analyzers "
        f"({', '.join(result.analyzers_run)}). Found {n_findings} finding(s): "
        f"{counts_str}; {blurb}. Highest-priority items: {top_lines}. "
        f"{result.verdict.emoji} Recommended verdict: **{result.verdict.label}**."
    )


def _openai_summary(result: ReviewResult, pr_title: str | None, api_key: str) -> str:
    """Call the OpenAI Chat Completions API for a nicer executive summary.

    Imports ``openai`` lazily so it never needs to be installed for the
    fully-offline / no-API-key path (including the entire test suite).
    """
    from openai import OpenAI  # type: ignore[import-not-found]

    client = OpenAI(api_key=api_key)
    findings_text = "\n".join(
        f"- [{f.severity.label}] {f.location()} ({f.analyzer}): {f.message}"
        for f in result.sorted_findings()[:25]
    )
    prompt = (
        "You are an experienced staff software engineer writing the opening "
        "executive summary of an automated code review comment on a GitHub "
        "pull request. Be concise (3-5 sentences), specific, and actionable. "
        "Do not invent issues beyond what's listed.\n\n"
        f"PR title: {pr_title or '(untitled)'}\n"
        f"Files reviewed: {result.files_reviewed}\n"
        f"Recommended verdict: {result.verdict.label}\n"
        f"Findings:\n{findings_text or '(none)'}\n"
    )
    response = client.chat.completions.create(
        model=os.environ.get("PR_REVIEW_AGENT_OPENAI_MODEL", "gpt-4o-mini"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=300,
    )
    content = response.choices[0].message.content
    return content.strip() if content else template_summary(result, pr_title)
