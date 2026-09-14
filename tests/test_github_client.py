from __future__ import annotations

import pytest
import responses

from pr_review_agent.github_client import GitHubClient, GitHubClientError

REPO = "octocat/hello-world"


@responses.activate
def test_get_pull_request_returns_metadata():
    responses.add(
        responses.GET,
        f"https://api.github.com/repos/{REPO}/pulls/42",
        json={
            "number": 42,
            "title": "Add feature",
            "html_url": f"https://github.com/{REPO}/pull/42",
            "user": {"login": "octocat"},
            "base": {"ref": "main"},
            "head": {"ref": "feature-branch"},
            "state": "open",
        },
        status=200,
    )

    client = GitHubClient(token="fake-token")
    pr = client.get_pull_request(REPO, 42)

    assert pr.number == 42
    assert pr.title == "Add feature"
    assert pr.user == "octocat"
    assert pr.base_ref == "main"
    assert pr.head_ref == "feature-branch"

    # Verify auth header + no network call left un-mocked.
    assert len(responses.calls) == 1
    assert responses.calls[0].request.headers["Authorization"] == "Bearer fake-token"


@responses.activate
def test_get_pull_request_diff_uses_diff_media_type():
    diff_text = "diff --git a/f.py b/f.py\n--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n-x\n+y\n"
    responses.add(
        responses.GET,
        f"https://api.github.com/repos/{REPO}/pulls/7",
        body=diff_text,
        status=200,
        content_type="application/vnd.github.v3.diff",
    )

    client = GitHubClient(token="fake-token")
    result = client.get_pull_request_diff(REPO, 7)

    assert result == diff_text
    assert responses.calls[0].request.headers["Accept"] == "application/vnd.github.v3.diff"


@responses.activate
def test_get_pull_request_raises_on_404():
    responses.add(
        responses.GET,
        f"https://api.github.com/repos/{REPO}/pulls/999",
        json={"message": "Not Found"},
        status=404,
    )

    client = GitHubClient(token="fake-token")
    with pytest.raises(GitHubClientError) as exc_info:
        client.get_pull_request(REPO, 999)

    assert exc_info.value.status_code == 404
    assert "Not Found" in str(exc_info.value)


@responses.activate
def test_post_issue_comment_sends_body_and_returns_json():
    responses.add(
        responses.POST,
        f"https://api.github.com/repos/{REPO}/issues/42/comments",
        json={"id": 123, "body": "Great PR!"},
        status=201,
    )

    client = GitHubClient(token="fake-token")
    result = client.post_issue_comment(REPO, 42, "Great PR!")

    assert result["id"] == 123
    sent_body = responses.calls[0].request.body
    assert b"Great PR!" in sent_body


def test_post_issue_comment_without_token_raises():
    client = GitHubClient(token=None)
    with pytest.raises(GitHubClientError):
        client.post_issue_comment(REPO, 42, "hello")
