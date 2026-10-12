"""Pure Challenge eligibility, start timing, and answer-resolution policies.

The application supplies persisted state after taking the SQLite writer slot.
Returned immutable decisions are complete proposals for atomic persistence with
receipts, attempts, Challenge facts, and audit events. This module performs no
I/O and does not provide persistence-level first-writer or retry guarantees.
"""

from dataclasses import dataclass, replace
from typing import Literal

from .answers import evaluate_answer
from .phase3 import EffectTeamState, apply_direct_freeze, reconcile_freeze
from .types import DomainError

CHALLENGE_GRACE_PERIOD_MS = 30_000

ChallengeEligibilityReason = Literal[
    "opportunity_spent",
    "opponent_unavailable",
    "game_unavailable",
]
ChallengeAnswerOutcome = Literal["incorrect", "won"]


@dataclass(frozen=True)
class ChallengeTeamState:
    team_id: str
    activity_state: str
    points: int
    opportunity_available: bool
    freeze_started_ms: int | None = None
    uno_reverse_active: bool = False


@dataclass(frozen=True)
class ChallengeEligibility:
    can_initiate: bool
    reason: ChallengeEligibilityReason | None


@dataclass(frozen=True)
class ChallengeStartDecision:
    initiator: ChallengeTeamState
    challenged: ChallengeTeamState
    points_delta: int
    opportunity_consumed: bool


@dataclass(frozen=True)
class ChallengeAnswerDecision:
    outcome: ChallengeAnswerOutcome
    initiator: ChallengeTeamState
    challenged: ChallengeTeamState
    winner_team_id: str | None
    freeze_applied: bool
    points_delta: int = 0
    advent_progressed: bool = False
    fragment_award: str | None = None
    music_triggered: bool = False


def _nonnegative_int(value: object) -> bool:
    return type(value) is int and value >= 0


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def challenge_grace_remaining_ms(
    started_gameplay_ms: int, current_gameplay_ms: int
) -> int:
    """Return the server-authoritative gathering time remaining.

    Challenge start timing uses Advent gameplay time, so the existing global
    Pause mechanism naturally freezes this countdown and restart recovery only
    needs the durable start gameplay timestamp.
    """
    if not _nonnegative_int(started_gameplay_ms) or not _nonnegative_int(
        current_gameplay_ms
    ):
        raise DomainError("invalid_input")
    if current_gameplay_ms < started_gameplay_ms:
        raise DomainError("invalid_input")
    elapsed = current_gameplay_ms - started_gameplay_ms
    return max(0, CHALLENGE_GRACE_PERIOD_MS - elapsed)


def _reconcile_team(
    team: ChallengeTeamState, current_gameplay_ms: int
) -> ChallengeTeamState:
    if (
        not isinstance(team, ChallengeTeamState)
        or not _nonempty_string(team.team_id)
        or not _nonnegative_int(team.points)
        or type(team.opportunity_available) is not bool
        or type(team.uno_reverse_active) is not bool
    ):
        raise DomainError("invalid_input")
    freeze = reconcile_freeze(
        team.activity_state, team.freeze_started_ms, current_gameplay_ms
    )
    return replace(
        team,
        activity_state=freeze.activity_state,
        freeze_started_ms=freeze.freeze_started_ms,
    )


def _validated_teams(
    initiator: ChallengeTeamState,
    challenged: ChallengeTeamState,
    current_gameplay_ms: int,
) -> tuple[ChallengeTeamState, ChallengeTeamState]:
    initiator = _reconcile_team(initiator, current_gameplay_ms)
    challenged = _reconcile_team(challenged, current_gameplay_ms)
    if initiator.team_id == challenged.team_id:
        raise DomainError("invalid_input")
    return initiator, challenged


def challenge_eligibility(
    *,
    global_state: str,
    challenge_active: bool,
    initiator: ChallengeTeamState,
    challenged: ChallengeTeamState,
    current_gameplay_ms: int,
    cost: int = 0,
) -> ChallengeEligibility:
    """Return caller-safe eligibility for the free, one-use Challenge.

    `cost` remains at this boundary only as a compatibility assertion while the
    unmerged Phase-6 schema still stores a zero-valued cost fact. Any nonzero
    value is invalid configuration: Challenge can never become affordable or
    unaffordable because it is always free.
    """
    if type(challenge_active) is not bool or type(cost) is not int or cost != 0:
        raise DomainError("invalid_input")
    initiator, challenged = _validated_teams(
        initiator, challenged, current_gameplay_ms
    )
    if (
        global_state != "ADVENT_QUIZ"
        or initiator.activity_state != "PUZZLE"
    ):
        return ChallengeEligibility(False, "game_unavailable")
    if not initiator.opportunity_available:
        return ChallengeEligibility(False, "opportunity_spent")
    if challenge_active:
        return ChallengeEligibility(False, "game_unavailable")
    if challenged.activity_state != "PUZZLE":
        return ChallengeEligibility(False, "opponent_unavailable")
    return ChallengeEligibility(True, None)


def initiate_challenge(
    *,
    global_state: str,
    challenge_active: bool,
    initiator: ChallengeTeamState,
    challenged: ChallengeTeamState,
    current_gameplay_ms: int,
    cost: int = 0,
) -> ChallengeStartDecision:
    """Consume the free one-use opportunity and enter Challenge activity."""
    if type(challenge_active) is not bool or type(cost) is not int or cost != 0:
        raise DomainError("invalid_input")
    initiator, challenged = _validated_teams(
        initiator, challenged, current_gameplay_ms
    )
    if global_state != "ADVENT_QUIZ" or initiator.activity_state != "PUZZLE":
        raise DomainError("disallowed_state")
    if not initiator.opportunity_available:
        raise DomainError("challenge_spent")
    if challenge_active or challenged.activity_state != "PUZZLE":
        raise DomainError("challenge_unavailable")

    return ChallengeStartDecision(
        initiator=replace(
            initiator,
            activity_state="CHALLENGE",
            opportunity_available=False,
        ),
        challenged=replace(challenged, activity_state="CHALLENGE"),
        points_delta=0,
        opportunity_consumed=True,
    )


def _as_effect_team(team: ChallengeTeamState) -> EffectTeamState:
    return EffectTeamState(
        activity_state=team.activity_state,
        points=team.points,
        freeze_started_ms=team.freeze_started_ms,
        uno_reverse_active=team.uno_reverse_active,
    )


def _with_effect_team(
    team: ChallengeTeamState, effect: EffectTeamState
) -> ChallengeTeamState:
    return replace(
        team,
        activity_state=effect.activity_state,
        points=effect.points,
        freeze_started_ms=effect.freeze_started_ms,
        uno_reverse_active=effect.uno_reverse_active,
    )


def resolve_challenge_answer(
    *,
    global_state: str,
    challenge_status: str,
    current_challenge_id: str | None,
    submitted_challenge_id: str,
    current_question_id: str | None,
    submitted_question_id: str,
    validator_type: str,
    expected_answer: str,
    submitted_answer: str,
    answering_team_id: str,
    initiator: ChallengeTeamState,
    challenged: ChallengeTeamState,
    current_gameplay_ms: int,
) -> ChallengeAnswerDecision:
    """Resolve one post-grace Challenge attempt without rewards/progression."""
    if global_state != "ADVENT_QUIZ":
        raise DomainError("disallowed_state")
    if challenge_status != "active" or current_challenge_id is None:
        raise DomainError("stale_challenge")
    if submitted_challenge_id != current_challenge_id:
        raise DomainError("stale_challenge")
    if current_question_id is None:
        raise DomainError("stale_challenge")
    if submitted_question_id != current_question_id:
        raise DomainError("stale_question")
    if (
        not _nonempty_string(current_challenge_id)
        or not _nonempty_string(submitted_challenge_id)
        or not _nonempty_string(current_question_id)
        or not _nonempty_string(submitted_question_id)
        or not _nonempty_string(validator_type)
        or not isinstance(expected_answer, str)
        or not _nonempty_string(submitted_answer)
        or not _nonempty_string(answering_team_id)
    ):
        raise DomainError("invalid_input")

    initiator, challenged = _validated_teams(
        initiator, challenged, current_gameplay_ms
    )
    if (
        initiator.activity_state != "CHALLENGE"
        or challenged.activity_state != "CHALLENGE"
    ):
        raise DomainError("stale_challenge")
    if answering_team_id not in {initiator.team_id, challenged.team_id}:
        raise DomainError("disallowed_state")

    if not evaluate_answer(validator_type, expected_answer, submitted_answer):
        return ChallengeAnswerDecision(
            outcome="incorrect",
            initiator=initiator,
            challenged=challenged,
            winner_team_id=None,
            freeze_applied=False,
        )

    initiator = replace(initiator, activity_state="PUZZLE")
    challenged = replace(challenged, activity_state="PUZZLE")
    freeze_applied = answering_team_id == initiator.team_id
    if freeze_applied:
        frozen = apply_direct_freeze(
            "ADVENT_QUIZ", _as_effect_team(challenged), current_gameplay_ms
        )
        challenged = _with_effect_team(challenged, frozen.team)

    return ChallengeAnswerDecision(
        outcome="won",
        initiator=initiator,
        challenged=challenged,
        winner_team_id=answering_team_id,
        freeze_applied=freeze_applied,
    )
