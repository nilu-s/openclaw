from __future__ import annotations

import pytest

from nexusctl.backend.integrations.github import _map_github_error



pytestmark = pytest.mark.unit
def test_github_error_mapping():
    assert _map_github_error(401) == "NX-GH-AUTH"
    assert _map_github_error(403) == "NX-GH-AUTH"
    assert _map_github_error(404) == "NX-GH-NOT-FOUND"
    assert _map_github_error(410) == "NX-GH-DISABLED"
    assert _map_github_error(422) == "NX-GH-VALIDATION"
    assert _map_github_error(429) == "NX-GH-RATE-LIMIT"
    assert _map_github_error(503) == "NX-GH-UPSTREAM"
