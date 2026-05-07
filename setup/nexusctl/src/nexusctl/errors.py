from __future__ import annotations

from dataclasses import dataclass


EXIT_SUCCESS = 0
EXIT_VALIDATION_ERROR = 2
EXIT_NOT_FOUND = 3
EXIT_PERMISSION_DENIED = 4
EXIT_PRECONDITION_FAILED = 6
EXIT_INFRA_ERROR = 10


ERROR_TO_EXIT = {
    "NX-VAL-001": EXIT_VALIDATION_ERROR,
    "NX-VAL-002": EXIT_VALIDATION_ERROR,
    "NX-NOTFOUND-001": EXIT_NOT_FOUND,
    "NX-PERM-001": EXIT_PERMISSION_DENIED,
    "NX-PRECONDITION-001": EXIT_PRECONDITION_FAILED,
    "NX-PRECONDITION-002": EXIT_PRECONDITION_FAILED,
    "NX-PRECONDITION-003": EXIT_PRECONDITION_FAILED,
    "NX-INFRA-001": EXIT_INFRA_ERROR,
    "NX-INFRA-002": EXIT_INFRA_ERROR,
}


@dataclass
class NexusError(Exception):
    code: str
    message: str
    exit_code: int | None = None

    def __post_init__(self) -> None:
        if self.exit_code is None:
            self.exit_code = ERROR_TO_EXIT.get(self.code, EXIT_INFRA_ERROR)
        super().__init__(f"{self.code}: {self.message}")


def raise_error(code: str, message: str) -> None:
    raise NexusError(code=code, message=message)
