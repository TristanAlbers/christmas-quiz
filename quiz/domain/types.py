"""Immutable values used by the phase 1 puzzle rules.

These values describe a proposed transition. The application persists the whole
decision, attempt, receipt, and audit event in one transaction.
"""

from dataclasses import dataclass
from typing import Literal

CompletionRoute = Literal["correct_answer", "skip", "admin_force"]
DomainErrorCode = Literal[
    "disallowed_state", "stale_question", "prerequisite_violation", "invalid_input",
    "insufficient_points", "no_hint_tokens", "already_active"
]


class DomainError(Exception):
    def __init__(self, code: DomainErrorCode):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class CompletionState:
    global_state: str
    team_state: str
    current_number: int
    points: int
    completed_numbers: frozenset[int]
    rewarded_numbers: frozenset[int]
    fragment_awarded_numbers: frozenset[int]


@dataclass(frozen=True)
class PuzzleCompletion:
    number: int
    reward_points: int
    fragment: str | None
    next_number: int | None


@dataclass(frozen=True)
class CompletionDecision:
    state: CompletionState
    route: CompletionRoute
    puzzle_number: int
    points_delta: int
    fragment_award: str | None
    progressed: bool
