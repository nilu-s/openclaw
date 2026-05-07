from __future__ import annotations

import pytest

from nexusctl.backend.integrations.github_templates import render_issue_body



pytestmark = pytest.mark.unit
def test_issue_template_is_sanitized_and_structured():
    body = render_issue_body(
        request={"request_id": "REQ-123", "sanitized_summary": "Implement deterministic checker", "objective": "secret domain objective", "branch": "feature/req-123", "acceptance_criteria": ["AC1"]},
        repo={"repo_id": "trading-engine"},
        implementation_context={"component": "risk", "entrypoints": ["risk.check"], "likely_files": ["src/risk.py"], "do_not_touch": ["secrets/*"], "test_commands": ["pytest"]},
    )
    assert "Nexus Request: REQ-123" in body
    assert "Implement deterministic checker" in body
    assert "secrets/*" in body
    assert "secret domain objective" not in body
