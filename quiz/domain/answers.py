"""Deterministic declared answer validators for the first slice."""

from decimal import Decimal, InvalidOperation

from .types import DomainError


def evaluate_answer(validator_type: str, expected: str, submitted: str) -> bool:
    """Check one answer without state or side effects.

    ``text_exact`` ignores surrounding whitespace and case; internal whitespace
    remains significant. ``number_exact`` compares finite decimal values, so
    forms such as ``2``, ``2.0`` and ``+02`` represent the same answer.
    Invalid user input is an incorrect attempt, not a configuration failure.
    """
    if not isinstance(expected, str) or not isinstance(submitted, str):
        raise DomainError("invalid_input")

    if validator_type == "text_exact":
        if not expected.strip():
            raise DomainError("invalid_input")
        return submitted.strip().casefold() == expected.strip().casefold()

    if validator_type == "number_exact":
        try:
            correct = Decimal(expected.strip())
        except InvalidOperation as exc:
            raise DomainError("invalid_input") from exc
        if not correct.is_finite():
            raise DomainError("invalid_input")
        try:
            proposed = Decimal(submitted.strip())
        except InvalidOperation:
            return False
        return proposed.is_finite() and proposed == correct

    raise DomainError("invalid_input")
