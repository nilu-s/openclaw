"""Typed domain and authorization errors for Nexusctl."""

from __future__ import annotations


class NexusctlError(Exception):
    """Base class for all expected Nexusctl failures."""


class ValidationError(NexusctlError):
    """Raised when a domain object is structurally invalid."""


class AuthenticationError(NexusctlError):
    """Raised when an HTTP/API token is missing, invalid, or expired."""


class UnknownDomainError(ValidationError):
    """Raised when a referenced domain does not exist."""


class UnknownAgentError(ValidationError):
    """Raised when a referenced agent does not exist."""


class UnknownCapabilityError(ValidationError):
    """Raised when a referenced capability does not exist."""


class PolicyDeniedError(NexusctlError):
    """Raised by callers that require an authorization decision to be allowed."""

    def __init__(self, reason: str, *, rule_id: str | None = None) -> None:
        self.reason = reason
        self.rule_id = rule_id
        prefix = f"{rule_id}: " if rule_id else ""
        super().__init__(f"{prefix}{reason}")
