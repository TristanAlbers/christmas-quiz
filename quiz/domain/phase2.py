"""Pure policies for basic administration and the phase 2 shop actions.

Callers commit each decision, its receipt, and audit event in one transaction.
Authentication, run identity, and persistence remain application concerns.
"""

from dataclasses import replace

from .completion import can_submit_answer, complete_puzzle
from .types import CompletionDecision, CompletionState, DomainError, PuzzleCompletion


def _nonnegative(value: int) -> bool:
    return type(value) is int and value >= 0


def pause_game(global_state: str) -> str:
    """Pause ordinary Advent gameplay without touching either team state."""
    if global_state != "ADVENT_QUIZ":
        raise DomainError("disallowed_state")
    return "PAUSED"


def resume_game(global_state: str) -> str:
    """Resume the Advent state that this phase permits pausing."""
    if global_state != "PAUSED":
        raise DomainError("disallowed_state")
    return "ADVENT_QUIZ"


def adjust_points(points: int, delta: int) -> int:
    """Calculate an admin adjustment without allowing a negative balance."""
    if not _nonnegative(points) or type(delta) is not int:
        raise DomainError("invalid_input")
    updated = points + delta
    if updated < 0:
        raise DomainError("insufficient_points")
    return updated


def purchase_hint(
    global_state: str,
    team_state: str,
    points: int,
    tokens: int,
    cost: int,
) -> tuple[int, int]:
    """Buy one generic token; spending is evaluated before any future reward."""
    if not can_submit_answer(global_state, team_state):
        raise DomainError("disallowed_state")
    if not all(_nonnegative(value) for value in (points, tokens, cost)):
        raise DomainError("invalid_input")
    if points < cost:
        raise DomainError("insufficient_points")
    return points - cost, tokens + 1


def reveal_hint(
    global_state: str,
    team_state: str,
    current_number: int,
    requested_number: int,
    tokens: int,
    revealed: bool,
    admin: bool = False,
) -> tuple[int, bool]:
    """Reveal the current puzzle's only hint, at most once per team and puzzle.

    An existing reveal costs nothing even if the team has no tokens. The
    application stores reveal history and replays an exact request receipt before
    calling this policy. Admin reveals cost no tokens on their first use.
    """
    if not can_submit_answer(global_state, team_state):
        raise DomainError("disallowed_state")
    if (
        type(current_number) is not int
        or current_number < 1
        or type(requested_number) is not int
        or requested_number < 1
        or not _nonnegative(tokens)
        or type(revealed) is not bool
        or type(admin) is not bool
    ):
        raise DomainError("invalid_input")
    if requested_number != current_number:
        raise DomainError("stale_question")
    if revealed:
        return tokens, False
    if admin:
        return tokens, True
    if tokens == 0:
        raise DomainError("no_hint_tokens")
    return tokens - 1, True


def pay_skip(
    state: CompletionState,
    puzzle: PuzzleCompletion,
    cost: int,
    *,
    other_team_finished: bool = False,
) -> CompletionDecision:
    """Complete a skippable puzzle via the canonical route after charging cost.

    Puzzle 25 is deliberately excluded: final-puzzle completion must come from a
    correct answer or the separate administrator force-completion route. The
    application must also reject puzzle 13 until its mandatory Music trigger can
    run atomically; the same guard applies to answer and admin completion routes.
    """
    if not _nonnegative(cost):
        raise DomainError("invalid_input")
    if puzzle.number == 25:
        raise DomainError("disallowed_state")
    decision = complete_puzzle(
        state,
        puzzle,
        "skip",
        other_team_finished=other_team_finished,
    )
    if state.points < cost:
        raise DomainError("insufficient_points")
    return replace(
        decision,
        state=replace(decision.state, points=decision.state.points - cost),
        points_delta=decision.points_delta - cost,
    )
