"""A small, dependency-light wrapper around the parts of the GitHub REST
API this tool needs: fetching a PR's metadata and diff, and posting a
review comment.

Deliberately implemented directly on top of ``requests`` rather than a
full SDK like PyGithub, so the dependency footprint stays small and the
behavior stays easy to reason about (and to mock in tests: nothing here
talks to the network at import time or module scope).
"""

from __future__ import annotations

from dataclasses import dataclass

import requests

DEFAULT_API_BASE = "https://api.github.com"
USER_AGENT = "ai-pr-review-agent"
REQUEST_TIMEOUT = 30  # seconds


class GitHubClientError(RuntimeError):
    """Raised for any non-2xx response from the GitHub API."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class PullRequest:
    number: int
    title: str
    html_url: str
    user: str
    base_ref: str
    head_ref: str
    state: str


class GitHubClient:
    def __init__(
        self,
        token: str | None = None,
        api_base: str = DEFAULT_API_BASE,
        session: requests.Session | None = None,
    ) -> None:
        self.token = token
        self.api_base = api_base.rstrip("/")
        self.session = session or requests.Session()

    def _headers(self, accept: str = "application/vnd.github+json") -> dict:
        headers = {
            "Accept": accept,
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def get_pull_request(self, repo: str, pr_number: int) -> PullRequest:
        """Fetch PR metadata (title, author, branches, etc.)."""
        url = f"{self.api_base}/repos/{repo}/pulls/{pr_number}"
        response = self.session.get(url, headers=self._headers(), timeout=REQUEST_TIMEOUT)
        self._raise_for_status(response, f"fetching PR metadata for {repo}#{pr_number}")
        data = response.json()
        return PullRequest(
            number=data["number"],
            title=data.get("title", ""),
            html_url=data.get("html_url", ""),
            user=(data.get("user") or {}).get("login", "unknown"),
            base_ref=(data.get("base") or {}).get("ref", ""),
            head_ref=(data.get("head") or {}).get("ref", ""),
            state=data.get("state", ""),
        )

    def get_pull_request_diff(self, repo: str, pr_number: int) -> str:
        """Fetch the raw unified diff text for a PR, using the GitHub
        ``application/vnd.github.v3.diff`` media type so we get exactly
        the same diff text ``git diff`` would produce, with no need to
        stitch it together from the paginated /files endpoint."""
        url = f"{self.api_base}/repos/{repo}/pulls/{pr_number}"
        response = self.session.get(
            url,
            headers=self._headers(accept="application/vnd.github.v3.diff"),
            timeout=REQUEST_TIMEOUT,
        )
        self._raise_for_status(response, f"fetching PR diff for {repo}#{pr_number}")
        return response.text

    def post_issue_comment(self, repo: str, pr_number: int, body: str) -> dict:
        """Post ``body`` as an issue comment on the PR.

        GitHub pull requests are backed by issues, so the "issue comments"
        endpoint is what posts a normal (non-review) comment on a PR --
        this is the simplest way to leave a bot review comment and only
        needs the standard ``issues: write`` (or ``pull-requests: write``)
        permission.
        """
        if not self.token:
            raise GitHubClientError(
                "Posting a comment requires a GitHub token with write access "
                "(pass --token or set GITHUB_TOKEN)."
            )
        url = f"{self.api_base}/repos/{repo}/issues/{pr_number}/comments"
        response = self.session.post(
            url, headers=self._headers(), json={"body": body}, timeout=REQUEST_TIMEOUT
        )
        self._raise_for_status(response, f"posting comment on {repo}#{pr_number}")
        return response.json()

    @staticmethod
    def _raise_for_status(response: requests.Response, action: str) -> None:
        if 200 <= response.status_code < 300:
            return
        detail = ""
        try:
            payload = response.json()
            detail = payload.get("message", "")
        except ValueError:
            detail = response.text[:300]
        raise GitHubClientError(
            f"GitHub API error while {action}: HTTP {response.status_code} {detail}".strip(),
            status_code=response.status_code,
        )
