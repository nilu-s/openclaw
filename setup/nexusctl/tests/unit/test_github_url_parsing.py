from __future__ import annotations

import pytest

from nexusctl.backend.integrations.github import parse_github_issue_url, parse_github_pr_url
from nexusctl.errors import NexusError



pytestmark = pytest.mark.unit
def test_parse_pr_url_accepts_expected_shape():
    ref = parse_github_pr_url("https://github.com/org/repo/pull/78")
    assert (ref.owner, ref.repo, ref.number) == ("org", "repo", 78)


def test_parse_issue_url_accepts_expected_shape():
    ref = parse_github_issue_url("https://github.com/org/repo/issues/45")
    assert (ref.owner, ref.repo, ref.number) == ("org", "repo", 45)


@pytest.mark.parametrize("url", ["http://github.com/org/repo/pull/1", "https://example.com/org/repo/pull/1", "https://github.com/org/repo/pulls/1", "https://github.com/org/repo/pull/x"])
def test_parse_pr_url_rejects_invalid(url):
    with pytest.raises(NexusError):
        parse_github_pr_url(url)
