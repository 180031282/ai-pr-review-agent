"""Command-line interface for the AI PR Review Agent.

Two ways to run a review:

- Live GitHub mode: ``pr-review-agent review --repo owner/repo --pr 123
  [--token ...] [--post]`` -- fetches the PR diff from the GitHub API.
- Local/offline mode: ``pr-review-agent review --diff-file some.diff`` --
  reads a unified diff from disk and never touches the network. This is
  the mode the test suite and the offline demo use.
"""

from __future__ import annotations

import sys

import click

from pr_review_agent import __version__
from pr_review_agent.analyzers import REGISTRY
from pr_review_agent.diff_parser import parse_diff
from pr_review_agent.github_client import GitHubClient, GitHubClientError
from pr_review_agent.orchestrator import ReviewOrchestrator, Verdict
from pr_review_agent.report import render_markdown


@click.group()
@click.version_option(__version__, prog_name="pr-review-agent")
def cli() -> None:
    """AI PR Review Agent -- agentic, multi-analyzer automated code review
    for GitHub pull requests."""


@cli.command()
def list_analyzers() -> None:
    """List all available analyzers and what they check for."""
    for name, cls in REGISTRY.items():
        click.echo(f"{name}: {cls.description}")


@cli.command()
@click.option("--repo", default=None, help="GitHub repo as 'owner/name', e.g. octocat/hello-world.")
@click.option("--pr", "pr_number", type=int, default=None, help="Pull request number.")
@click.option(
    "--diff-file",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Path to a local unified-diff file. Fully offline: no GitHub API calls at all.",
)
@click.option(
    "--token",
    envvar="GITHUB_TOKEN",
    default=None,
    help="GitHub token (read access to fetch a PR; write access to use --post). "
    "Defaults to $GITHUB_TOKEN.",
)
@click.option(
    "--post",
    is_flag=True,
    default=False,
    help="Post the rendered review as a comment on the live PR (requires --repo/--pr "
    "and a token with write access). Not available with --diff-file.",
)
@click.option(
    "--output",
    default="-",
    show_default=True,
    help="File to write the markdown review to. '-' prints to stdout.",
)
@click.option(
    "--analyzers",
    "analyzer_names",
    default=None,
    help=f"Comma-separated subset of analyzers to run (default: all). "
    f"Available: {', '.join(REGISTRY)}.",
)
@click.option(
    "--api-base",
    default="https://api.github.com",
    show_default=True,
    help="GitHub API base URL (override for GitHub Enterprise Server).",
)
@click.option(
    "--fail-on-request-changes",
    is_flag=True,
    default=False,
    help="Exit with status 1 if the verdict is 'request_changes' -- useful for "
    "gating CI on the review result.",
)
def review(
    repo: str | None,
    pr_number: int | None,
    diff_file: str | None,
    token: str | None,
    post: bool,
    output: str,
    analyzer_names: str | None,
    api_base: str,
    fail_on_request_changes: bool,
) -> None:
    """Review a pull request and produce a structured markdown report."""
    names = [n.strip() for n in analyzer_names.split(",")] if analyzer_names else None

    pr_title = None
    pr_url = None

    if diff_file:
        if post:
            raise click.ClickException("--post cannot be used with --diff-file (no PR to post to).")
        with open(diff_file, encoding="utf-8") as fh:
            diff_text = fh.read()
    else:
        if not repo or not pr_number:
            raise click.ClickException(
                "Either --diff-file, or both --repo and --pr, are required."
            )
        client = GitHubClient(token=token, api_base=api_base)
        try:
            pr = client.get_pull_request(repo, pr_number)
            diff_text = client.get_pull_request_diff(repo, pr_number)
        except GitHubClientError as exc:
            raise click.ClickException(str(exc)) from exc
        pr_title = pr.title
        pr_url = pr.html_url

    file_diffs = parse_diff(diff_text)

    try:
        orchestrator = ReviewOrchestrator(analyzer_names=names)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    result = orchestrator.review(file_diffs)
    markdown = render_markdown(
        result,
        pr_title=pr_title,
        pr_url=pr_url,
        repo=repo,
        pr_number=pr_number,
    )

    if output == "-":
        click.echo(markdown)
    else:
        with open(output, "w", encoding="utf-8") as fh:
            fh.write(markdown)
        click.echo(f"Review written to {output}", err=True)

    click.echo(
        f"[pr-review-agent] {result.verdict.emoji} verdict={result.verdict.value} "
        f"findings={len(result.findings)} files={result.files_reviewed}",
        err=True,
    )

    if post:
        assert repo is not None and pr_number is not None  # enforced above
        try:
            client.post_issue_comment(repo, pr_number, markdown)
        except GitHubClientError as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(f"Posted review comment on {repo}#{pr_number}", err=True)

    if fail_on_request_changes and result.verdict == Verdict.REQUEST_CHANGES:
        sys.exit(1)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
