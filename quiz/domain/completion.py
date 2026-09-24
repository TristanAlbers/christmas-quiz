"""Canonical, persistence-free puzzle completion policy."""

from dataclasses import replace

from .types import (
    CompletionDecision,
    CompletionRoute,
    CompletionState,
    DomainError,
    PuzzleCompletion,
)

FINAL_PUZZLE_NUMBER = 25


def can_submit_answer(global_state: str, team_state: str) -> bool:
    return global_state == "ADVENT_QUIZ" and team_state == "PUZZLE"


def complete_puzzle(
    state: CompletionState,
    puzzle: PuzzleCompletion,
    route: CompletionRoute,
    *,
    other_team_finished: bool = False,
) -> CompletionDecision:
    """Return all effects for one completion, including Skip and admin routes.

    Current completion and historical award markers are deliberately separate.
    A reopened puzzle can become completed again without repeating an award.
    Only the application may atomically commit this proposal with a receipt and
    event, after acquiring the SQLite writer slot and rereading current state.
    """
    if route not in ("correct_answer", "skip", "admin_force"):
        raise DomainError("invalid_input")
    if type(other_team_finished) is not bool:
        raise DomainError("invalid_input")
    if state.global_state != "ADVENT_QUIZ" or state.team_state != "PUZZLE":
        raise DomainError("disallowed_state")
    if (
        state.current_number < 1
        or puzzle.number < 1
        or puzzle.number > FINAL_PUZZLE_NUMBER
        or puzzle.reward_points < 0
        or state.points < 0
        or (puzzle.next_number is not None and puzzle.next_number != puzzle.number + 1)
        or (puzzle.number == FINAL_PUZZLE_NUMBER and puzzle.next_number is not None)
    ):
        raise DomainError("invalid_input")
    if puzzle.number > state.current_number or (
        puzzle.number < state.current_number and route != "admin_force"
    ):
        raise DomainError("stale_question")
    if puzzle.number in state.completed_numbers:
        raise DomainError("stale_question")
    if any(n not in state.completed_numbers for n in range(1, puzzle.number)):
        raise DomainError("prerequisite_violation")

    reward = puzzle.reward_points if puzzle.number not in state.rewarded_numbers else 0
    fragment = (
        puzzle.fragment
        if puzzle.fragment is not None
        and puzzle.number not in state.fragment_awarded_numbers
        else None
    )
    progressed = (
        puzzle.number == state.current_number and puzzle.next_number is not None
    )
    team_finished = puzzle.number == FINAL_PUZZLE_NUMBER
    game_finished = team_finished and other_team_finished
    updated = replace(
        state,
        global_state="FINISHED" if game_finished else state.global_state,
        team_state="FINISHED" if team_finished else state.team_state,
        current_number=puzzle.next_number if progressed else state.current_number,
        points=state.points + reward,
        completed_numbers=state.completed_numbers | {puzzle.number},
        rewarded_numbers=state.rewarded_numbers | {puzzle.number},
        fragment_awarded_numbers=(
            state.fragment_awarded_numbers | {puzzle.number}
            if fragment is not None
            else state.fragment_awarded_numbers
        ),
    )
    return CompletionDecision(
        state=updated,
        route=route,
        puzzle_number=puzzle.number,
        points_delta=reward,
        fragment_award=fragment,
        progressed=progressed,
        team_finished=team_finished,
        claim_first_finisher=team_finished and not other_team_finished,
        game_finished=game_finished,
    )
