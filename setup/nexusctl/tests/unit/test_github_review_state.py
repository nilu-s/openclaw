from __future__ import annotations

from nexusctl.backend.integrations.github import derive_review_state


def test_review_state_latest_reviewer_changes_requested_wins():
    assert derive_review_state([
        {"user": {"login": "a"}, "state": "APPROVED", "submitted_at": "2026-01-01T00:00:00Z"},
        {"user": {"login": "a"}, "state": "CHANGES_REQUESTED", "submitted_at": "2026-01-02T00:00:00Z"},
        {"user": {"login": "b"}, "state": "APPROVED", "submitted_at": "2026-01-01T00:00:00Z"},
    ]) == "changes_requested"


def test_review_state_approved_without_changes():
    assert derive_review_state([{"user": {"login": "a"}, "state": "APPROVED", "submitted_at": "2026-01-01T00:00:00Z"}]) == "approved"


def test_review_state_pending_without_reviews():
    assert derive_review_state([]) == "pending"
