"""Pure game rules live here; no Django or persistence imports."""

from .answers import evaluate_answer
from .completion import can_submit_answer, complete_puzzle
from .types import (
    CompletionDecision,
    CompletionRoute,
    CompletionState,
    DomainError,
    PuzzleCompletion,
)

__all__ = [
    "CompletionDecision",
    "CompletionRoute",
    "CompletionState",
    "DomainError",
    "PuzzleCompletion",
    "can_submit_answer",
    "complete_puzzle",
    "evaluate_answer",
]
