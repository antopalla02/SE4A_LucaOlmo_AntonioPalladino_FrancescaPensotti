"""Domain errors.

Every violation of a domain rule (R14-R18, R31-R33), of an FSM transition
(RASD Sec. 3.2) or of a validation rule raises a DomainError carrying a
machine-readable code. The API layer translates these into HTTP 409/422
responses whose error codes reuse the requirement identifiers (DD Sec. 3.3,
R41), e.g. ``R14_DUPLICATE_PROPOSAL``.

The domain package depends on nothing (DD Sec. 2.1.3 / 2.1.7).
"""


class DomainError(Exception):
    """Base class for every rule violation raised by the domain."""

    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class ValidationError(DomainError):
    """Malformed input (missing fields, out-of-range values). Maps to HTTP 422."""


class InvariantViolation(DomainError):
    """Violation of a domain rule (R14-R18, R31-R33). Maps to HTTP 409."""


class IllegalTransition(DomainError):
    """Illegal FSM transition (RASD Sec. 3.2). Maps to HTTP 409."""
