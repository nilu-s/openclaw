"""Recovery evidence payloads for local backup and restore drills."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import hashlib
from pathlib import Path
from typing import Any, Mapping

from nexusctl.domain.errors import ValidationError
from nexusctl.storage.sqlite.migrations import MIGRATIONS

EVIDENCE_VERSION = "recovery-evidence.v1"

_SECRET_KEY_HINTS = ("secret", "token", "password", "passphrase", "private_key", "credential")
_SECRET_VALUE_MARKERS = (
    "ghp_",
    "github_pat_",
    "-----BEGIN",
    "GITHUB_WEBHOOK_SECRET=",
    "real-secret",
)

OPERATOR_CONTROL_BOUNDARIES: dict[str, tuple[str, ...]] = {
    "local_product_evidence": (
        "sqlite_backup_created_or_checked",
        "restore_drill_to_fresh_database",
        "doctor_status",
        "event_chain_integrity",
        "schema_version",
        "failed_checks",
    ),
    "external_operator_controls": (
        "tls_reverse_proxy_enforcement",
        "credential_management_and_rotation",
        "offsite_replication",
        "worm_or_object_lock",
        "external_audit_signatures_or_exports",
        "monitoring_and_paging",
        "retention_enforcement",
    ),
    "incident_triggers": (
        "restore_drill_status_not_ok",
        "doctor_status_not_ok",
        "event_chain_status_not_ok",
        "failed_checks_not_empty",
        "retention_status_not_configured_or_not_green",
        "offsite_status_not_configured_or_not_green",
        "evidence_manifest_missing_or_not_archived",
    ),
}


def operator_control_boundaries_json() -> dict[str, list[str]]:
    """Return the stable secret-free boundary between local evidence and operator controls."""

    return {key: list(values) for key, values in OPERATOR_CONTROL_BOUNDARIES.items()}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _redact_string(value: str) -> str:
    redacted = value
    for marker in _SECRET_VALUE_MARKERS:
        if marker in redacted:
            redacted = redacted.replace(marker, "[redacted]")
    return redacted


def _sanitize(value: Any, *, key: str | None = None) -> Any:
    if key is not None and any(hint in key.lower() for hint in _SECRET_KEY_HINTS):
        return "[redacted]"
    if isinstance(value, Mapping):
        return {str(item_key): _sanitize(item_value, key=str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, str):
        return _redact_string(value)
    return value


@dataclass(frozen=True, slots=True)
class OperatorControlStatus:
    """Operator-provided control status for retention or offsite handling."""

    status_code: str = "not_configured"
    configured: bool = False
    summary: str = "Operator control is not configured in this local evidence payload."
    action: str = "Configure and verify this control outside the repository."

    def to_json(self) -> dict[str, Any]:
        return {
            "status_code": self.status_code,
            "configured": self.configured,
            "summary": self.summary,
            "action": self.action,
        }


@dataclass(frozen=True, slots=True)
class RecoveryEvidence:
    """Stable, secret-free recovery evidence contract for one local drill."""

    generated_at: str
    source_db: str
    backup_path: str
    backup_checksum: str | None
    schema_version: int | None
    latest_schema_version: int
    event_chain_status: dict[str, Any]
    checked_events: int
    doctor_status: str
    failed_checks: list[dict[str, Any]]
    counts: dict[str, int]
    restore_drill_status: str
    retention_status: dict[str, Any] = field(default_factory=lambda: OperatorControlStatus().to_json())
    offsite_status: dict[str, Any] = field(default_factory=lambda: OperatorControlStatus().to_json())
    operator_control_boundaries: dict[str, Any] = field(default_factory=operator_control_boundaries_json)
    evidence_version: str = EVIDENCE_VERSION

    def to_json(self) -> dict[str, Any]:
        payload = {
            "evidence_version": self.evidence_version,
            "generated_at": self.generated_at,
            "source_db": self.source_db,
            "backup_path": self.backup_path,
            "backup_checksum": self.backup_checksum,
            "schema_version": self.schema_version,
            "latest_schema_version": self.latest_schema_version,
            "event_chain_status": self.event_chain_status,
            "checked_events": self.checked_events,
            "doctor_status": self.doctor_status,
            "failed_checks": self.failed_checks,
            "counts": self.counts,
            "restore_drill_status": self.restore_drill_status,
            "retention_status": self.retention_status,
            "offsite_status": self.offsite_status,
            "operator_control_boundaries": self.operator_control_boundaries,
        }
        return _sanitize(payload)


class RecoveryEvidenceBuilder:
    """Build recovery evidence from existing backup and restore-drill payloads."""

    @staticmethod
    def from_restore_drill(
        *,
        source_db: str | Path,
        restore_drill: Mapping[str, Any],
        backup_check: Mapping[str, Any] | None = None,
        generated_at: str | None = None,
        retention_status: Mapping[str, Any] | None = None,
        offsite_status: Mapping[str, Any] | None = None,
    ) -> RecoveryEvidence:
        backup_path = Path(str(restore_drill.get("backup_path") or (backup_check or {}).get("backup_path") or ""))
        failed_checks = _sanitize(list(restore_drill.get("failed_checks") or []))
        checked_events = int(restore_drill.get("checked_events") or (backup_check or {}).get("checked_events") or 0)
        schema_version = restore_drill.get("schema_version") or (backup_check or {}).get("schema_version")
        latest_schema_version = int((backup_check or {}).get("latest_schema_version") or max(m.version for m in MIGRATIONS))
        backup_checksum = (backup_check or {}).get("checksum") or _sha256_file(backup_path)
        doctor_status = str(restore_drill.get("doctor_status") or "unknown")
        restore_ok = bool(restore_drill.get("ok"))
        event_failure = next((item for item in failed_checks if item.get("kind") == "event_integrity"), None)
        if event_failure:
            event_chain_status = {
                "status_code": str(event_failure.get("status_code") or "invalid"),
                "valid": False,
                "checked_events": checked_events,
                "summary": str(event_failure.get("summary") or "event chain integrity failed"),
            }
        elif checked_events > 0 and restore_ok:
            event_chain_status = {
                "status_code": "ok",
                "valid": True,
                "checked_events": checked_events,
                "summary": "Event hash chain was verified during restore drill.",
            }
        else:
            event_chain_status = {
                "status_code": "not_green",
                "valid": False,
                "checked_events": checked_events,
                "summary": "Event hash chain is not proven green by this restore drill.",
            }

        return RecoveryEvidence(
            generated_at=generated_at or _utc_now(),
            source_db=str(source_db),
            backup_path=str(backup_path),
            backup_checksum=str(backup_checksum) if backup_checksum is not None else None,
            schema_version=int(schema_version) if schema_version is not None else None,
            latest_schema_version=latest_schema_version,
            event_chain_status=event_chain_status,
            checked_events=checked_events,
            doctor_status=doctor_status,
            failed_checks=failed_checks,
            counts={str(key): int(value) for key, value in dict(restore_drill.get("counts") or (backup_check or {}).get("counts") or {}).items()},
            restore_drill_status="ok" if restore_ok and doctor_status == "ok" and not failed_checks else "not_green",
            retention_status=_sanitize(dict(retention_status)) if retention_status is not None else OperatorControlStatus().to_json(),
            offsite_status=_sanitize(dict(offsite_status)) if offsite_status is not None else OperatorControlStatus().to_json(),
            operator_control_boundaries=operator_control_boundaries_json(),
        )


def write_recovery_evidence_manifest(
    *,
    evidence: Mapping[str, Any],
    target_path: str | Path,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Atomically write a secret-sanitized recovery evidence manifest as JSON."""

    target = Path(target_path)
    if target.exists() and not overwrite:
        raise ValidationError(f"recovery evidence manifest already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)

    sanitized = _sanitize(dict(evidence))
    serialized = json.dumps(sanitized, indent=2, sort_keys=True) + "\n"
    temporary = target.with_name(f".{target.name}.tmp")
    try:
        temporary.write_text(serialized, encoding="utf-8")
        temporary.replace(target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return {
        "path": str(target),
        "bytes": target.stat().st_size,
        "checksum": _sha256_file(target),
    }
