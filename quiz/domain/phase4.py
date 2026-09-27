"""Pure Music Quiz interruption, scoring, and recoverable-clock policies.

Callers supply persisted state and an aware server timestamp.  The returned
immutable decisions are proposals which the application persists atomically
with receipts, attempts, rewards, and audit events.  This module has no wall
clock, database, HTTP, or filesystem dependency.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from .answers import evaluate_answer
from .phase3 import GameplayClock, effective_gameplay_ms
from .types import DomainError

MUSIC_QUESTION_TOTAL = 11
MUSIC_GATHERING_DURATION_MS = 60_000

MusicPhase = Literal["gathering", "question", "final_results", "completed"]
MusicAnswerOutcome = Literal["incorrect", "won"]


@dataclass(frozen=True)
class MusicClock:
    accumulated_ms: int
    anchor: datetime | None


@dataclass(frozen=True)
class UnderlyingTeamState:
    """The interruption-owned subset of an underlying Advent team state."""

    team_id: str
    activity_state: str
    freeze_started_ms: int | None


@dataclass(frozen=True)
class MusicScore:
    team_id: str
    score: int


@dataclass(frozen=True)
class MusicStartDecision:
    triggered: bool
    global_state: str
    advent_clock: GameplayClock
    music_clock: MusicClock | None
    underlying_teams: tuple[UnderlyingTeamState, ...]
    pause_resume_target: str | None
    phase: MusicPhase | None
    current_question_number: int | None
    current_question_started_ms: int | None


@dataclass(frozen=True)
class MusicInterruptionDecision:
    global_state: str
    advent_clock: GameplayClock
    music_clock: MusicClock
    underlying_teams: tuple[UnderlyingTeamState, ...]
    pause_resume_target: str | None


@dataclass(frozen=True)
class MusicAnswerDecision:
    outcome: MusicAnswerOutcome
    phase: MusicPhase
    attempted_question_number: int
    current_question_number: int | None
    scores: tuple[MusicScore, ...]
    team_points: int
    score_delta: int
    points_delta: int
    winner_team_id: str | None
    final_results_started_ms: int | None

    @property
    def advanced(self) -> bool:
        return self.outcome == "won"


@dataclass(frozen=True)
class MusicTimingDecision:
    global_state: str
    phase: MusicPhase
    music_clock: MusicClock
    advent_clock: GameplayClock
    current_question_number: int | None
    current_question_started_ms: int | None
    gathering_remaining_ms: int | None
    final_results_started_ms: int | None
    final_results_remaining_ms: int | None
    logical_transition_at: datetime | None


def _nonnegative_int(value: object) -> bool:
    return type(value) is int and value >= 0


def _positive_int(value: object) -> bool:
    return type(value) is int and value > 0


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_clock(
    accumulated_ms: int, anchor: datetime | None, now: datetime
) -> None:
    if (
        not _nonnegative_int(accumulated_ms)
        or (anchor is not None and not _aware(anchor))
        or not _aware(now)
    ):
        raise DomainError("invalid_input")


def _validate_advent_clock(clock: GameplayClock, now: datetime) -> None:
    if not isinstance(clock, GameplayClock):
        raise DomainError("invalid_input")
    _validate_clock(clock.accumulated_ms, clock.anchor, now)


def _validate_underlying_teams(
    teams: tuple[UnderlyingTeamState, ...],
) -> tuple[UnderlyingTeamState, ...]:
    if not isinstance(teams, tuple) or len(teams) != 2:
        raise DomainError("invalid_input")
    seen: set[str] = set()
    for team in teams:
        if (
            not isinstance(team, UnderlyingTeamState)
            or not _nonempty_string(team.team_id)
            or team.team_id in seen
            or not _nonempty_string(team.activity_state)
            or (
                team.freeze_started_ms is not None
                and not _nonnegative_int(team.freeze_started_ms)
            )
            or (team.activity_state == "FREEZE")
            != (team.freeze_started_ms is not None)
        ):
            raise DomainError("invalid_input")
        seen.add(team.team_id)
    return teams


def _validate_scores(
    scores: tuple[MusicScore, ...], current_question_number: int
) -> None:
    if not isinstance(scores, tuple) or len(scores) != 2:
        raise DomainError("invalid_input")
    seen: set[str] = set()
    total = 0
    for score in scores:
        if (
            not isinstance(score, MusicScore)
            or not _nonempty_string(score.team_id)
            or score.team_id in seen
            or not _nonnegative_int(score.score)
            or score.score > MUSIC_QUESTION_TOTAL
        ):
            raise DomainError("invalid_input")
        seen.add(score.team_id)
        total += score.score
    if total != current_question_number - 1:
        raise DomainError("invalid_input")


def effective_music_ms(
    accumulated_ms: int, anchor: datetime | None, now: datetime
) -> int:
    """Return the recoverable Music-active time represented by a clock."""
    _validate_clock(accumulated_ms, anchor, now)
    if anchor is None:
        return accumulated_ms
    elapsed = now - anchor
    elapsed_ms = max(
        0,
        elapsed.days * 86_400_000
        + elapsed.seconds * 1_000
        + elapsed.microseconds // 1_000,
    )
    return accumulated_ms + elapsed_ms


def begin_music_interruption(
    *,
    global_state: str,
    already_triggered: bool,
    advent_clock: GameplayClock,
    underlying_teams: tuple[UnderlyingTeamState, ...],
    now: datetime,
) -> MusicStartDecision:
    """Decide the one-time puzzle-13 interruption without mutating team state.

    A prior durable trigger is an intentional no-op: a later canonical
    re-completion of puzzle 13 remains valid but cannot restart Music.
    """
    if global_state != "ADVENT_QUIZ":
        raise DomainError("disallowed_state")
    if type(already_triggered) is not bool:
        raise DomainError("invalid_input")
    _validate_advent_clock(advent_clock, now)
    teams = _validate_underlying_teams(underlying_teams)
    if advent_clock.anchor is None:
        raise DomainError("invalid_input")

    if already_triggered:
        return MusicStartDecision(
            triggered=False,
            global_state="ADVENT_QUIZ",
            advent_clock=advent_clock,
            music_clock=None,
            underlying_teams=teams,
            pause_resume_target=None,
            phase=None,
            current_question_number=None,
            current_question_started_ms=None,
        )

    reconciled_advent = GameplayClock(
        effective_gameplay_ms(
            advent_clock.accumulated_ms, advent_clock.anchor, now
        ),
        None,
    )
    return MusicStartDecision(
        triggered=True,
        global_state="MUSIC_QUIZ",
        advent_clock=reconciled_advent,
        music_clock=MusicClock(0, now),
        underlying_teams=teams,
        pause_resume_target=None,
        phase="gathering",
        current_question_number=None,
        current_question_started_ms=None,
    )


def pause_music_interruption(
    *,
    global_state: str,
    advent_clock: GameplayClock,
    music_clock: MusicClock,
    underlying_teams: tuple[UnderlyingTeamState, ...],
    now: datetime,
) -> MusicInterruptionDecision:
    """Pause Music while leaving the already-stopped Advent clock untouched."""
    if global_state != "MUSIC_QUIZ":
        raise DomainError("disallowed_state")
    _validate_advent_clock(advent_clock, now)
    if advent_clock.anchor is not None or not isinstance(music_clock, MusicClock):
        raise DomainError("invalid_input")
    _validate_clock(music_clock.accumulated_ms, music_clock.anchor, now)
    if music_clock.anchor is None:
        raise DomainError("invalid_input")
    teams = _validate_underlying_teams(underlying_teams)
    return MusicInterruptionDecision(
        global_state="PAUSED",
        advent_clock=advent_clock,
        music_clock=MusicClock(
            effective_music_ms(
                music_clock.accumulated_ms, music_clock.anchor, now
            ),
            None,
        ),
        underlying_teams=teams,
        pause_resume_target="MUSIC_QUIZ",
    )


def resume_music_interruption(
    *,
    global_state: str,
    pause_resume_target: str | None,
    advent_clock: GameplayClock,
    music_clock: MusicClock,
    underlying_teams: tuple[UnderlyingTeamState, ...],
    now: datetime,
) -> MusicInterruptionDecision:
    """Resume the same Music phase without consuming intentionally paused time."""
    if global_state != "PAUSED" or pause_resume_target != "MUSIC_QUIZ":
        raise DomainError("disallowed_state")
    _validate_advent_clock(advent_clock, now)
    if advent_clock.anchor is not None or not isinstance(music_clock, MusicClock):
        raise DomainError("invalid_input")
    _validate_clock(music_clock.accumulated_ms, music_clock.anchor, now)
    if music_clock.anchor is not None:
        raise DomainError("invalid_input")
    teams = _validate_underlying_teams(underlying_teams)
    return MusicInterruptionDecision(
        global_state="MUSIC_QUIZ",
        advent_clock=advent_clock,
        music_clock=MusicClock(music_clock.accumulated_ms, now),
        underlying_teams=teams,
        pause_resume_target=None,
    )


def resolve_music_answer(
    *,
    global_state: str,
    phase: str,
    current_question_id: str | None,
    submitted_question_id: str,
    current_question_number: int,
    validator_type: str,
    expected_answer: str,
    submitted_answer: str,
    team_id: str,
    scores: tuple[MusicScore, ...],
    team_points: int,
    reward_points: int,
    current_music_ms: int,
) -> MusicAnswerDecision:
    """Resolve an accepted current-question attempt and its complete effects."""
    # State precedes anti-staleness: paused/final/Advent requests are not active
    # Music submissions even when they carry an old displayed identifier.
    if global_state != "MUSIC_QUIZ" or phase != "question":
        raise DomainError("disallowed_state")
    if current_question_id is None:
        raise DomainError("disallowed_state")
    if submitted_question_id != current_question_id:
        raise DomainError("stale_question")

    if (
        not _nonempty_string(current_question_id)
        or not _nonempty_string(submitted_question_id)
        or not _positive_int(current_question_number)
        or current_question_number > MUSIC_QUESTION_TOTAL
        or not _nonempty_string(validator_type)
        or not isinstance(expected_answer, str)
        or not _nonempty_string(submitted_answer)
        or not _nonempty_string(team_id)
        or not _nonnegative_int(team_points)
        or not _nonnegative_int(reward_points)
        or not _nonnegative_int(current_music_ms)
    ):
        raise DomainError("invalid_input")
    _validate_scores(scores, current_question_number)
    if team_id not in {score.team_id for score in scores}:
        raise DomainError("invalid_input")

    correct = evaluate_answer(validator_type, expected_answer, submitted_answer)
    if not correct:
        return MusicAnswerDecision(
            outcome="incorrect",
            phase="question",
            attempted_question_number=current_question_number,
            current_question_number=current_question_number,
            scores=scores,
            team_points=team_points,
            score_delta=0,
            points_delta=0,
            winner_team_id=None,
            final_results_started_ms=None,
        )

    updated_scores = tuple(
        MusicScore(score.team_id, score.score + (score.team_id == team_id))
        for score in scores
    )
    is_final = current_question_number == MUSIC_QUESTION_TOTAL
    return MusicAnswerDecision(
        outcome="won",
        phase="final_results" if is_final else "question",
        attempted_question_number=current_question_number,
        current_question_number=(
            None if is_final else current_question_number + 1
        ),
        scores=updated_scores,
        team_points=team_points + reward_points,
        score_delta=1,
        points_delta=reward_points,
        winner_team_id=team_id,
        final_results_started_ms=current_music_ms if is_final else None,
    )


def music_phase_elapsed_ms(
    current_music_ms: int, phase_started_ms: int
) -> int:
    """Derive a non-authoritative upward counter from the Music clock."""
    if (
        not _nonnegative_int(current_music_ms)
        or not _nonnegative_int(phase_started_ms)
        or phase_started_ms > current_music_ms
    ):
        raise DomainError("invalid_input")
    return current_music_ms - phase_started_ms


def reconcile_music_timing(
    *,
    global_state: str,
    pause_resume_target: str | None,
    phase: str,
    music_clock: MusicClock,
    advent_clock: GameplayClock,
    current_question_number: int | None,
    current_question_started_ms: int | None,
    final_results_started_ms: int | None,
    final_results_duration_ms: int,
    now: datetime,
) -> MusicTimingDecision:
    """Reconcile Music subphase timing at its logical clock boundary.

    Active Music downtime counts because its anchor remains present.  A Music
    pause has no anchor and therefore consumes no gathering or display
    duration.  Logical transitions use the clock boundary rather than this
    call's potentially later observation time.
    """
    if not isinstance(music_clock, MusicClock):
        raise DomainError("invalid_input")
    _validate_clock(music_clock.accumulated_ms, music_clock.anchor, now)
    _validate_advent_clock(advent_clock, now)
    if not _positive_int(final_results_duration_ms):
        raise DomainError("invalid_input")

    if phase == "completed":
        if (
            global_state != "ADVENT_QUIZ"
            or pause_resume_target is not None
            or music_clock.anchor is not None
            or advent_clock.anchor is None
            or current_question_number is not None
            or current_question_started_ms is not None
            or not _nonnegative_int(final_results_started_ms)
        ):
            raise DomainError("invalid_input")
        return MusicTimingDecision(
            global_state="ADVENT_QUIZ",
            phase="completed",
            music_clock=music_clock,
            advent_clock=advent_clock,
            current_question_number=None,
            current_question_started_ms=None,
            gathering_remaining_ms=None,
            final_results_started_ms=final_results_started_ms,
            final_results_remaining_ms=0,
            logical_transition_at=None,
        )

    if global_state == "MUSIC_QUIZ":
        if pause_resume_target is not None or music_clock.anchor is None:
            raise DomainError("invalid_input")
    elif global_state == "PAUSED":
        if pause_resume_target != "MUSIC_QUIZ" or music_clock.anchor is not None:
            raise DomainError("invalid_input")
    else:
        raise DomainError("disallowed_state")
    if advent_clock.anchor is not None:
        raise DomainError("invalid_input")

    current_music_ms = effective_music_ms(
        music_clock.accumulated_ms, music_clock.anchor, now
    )
    if phase == "gathering":
        if (
            current_question_number is not None
            or current_question_started_ms is not None
            or final_results_started_ms is not None
        ):
            raise DomainError("invalid_input")
        remaining_ms = max(
            0, MUSIC_GATHERING_DURATION_MS - current_music_ms
        )
        if remaining_ms > 0 or global_state == "PAUSED":
            return MusicTimingDecision(
                global_state=global_state,
                phase="gathering",
                music_clock=music_clock,
                advent_clock=advent_clock,
                current_question_number=None,
                current_question_started_ms=None,
                gathering_remaining_ms=remaining_ms,
                final_results_started_ms=None,
                final_results_remaining_ms=None,
                logical_transition_at=None,
            )

        until_question_ms = max(
            0, MUSIC_GATHERING_DURATION_MS - music_clock.accumulated_ms
        )
        logical_start = music_clock.anchor + timedelta(
            milliseconds=until_question_ms
        )
        return MusicTimingDecision(
            global_state="MUSIC_QUIZ",
            phase="question",
            music_clock=music_clock,
            advent_clock=advent_clock,
            current_question_number=1,
            current_question_started_ms=MUSIC_GATHERING_DURATION_MS,
            gathering_remaining_ms=None,
            final_results_started_ms=None,
            final_results_remaining_ms=None,
            logical_transition_at=logical_start,
        )
    if phase == "question":
        if (
            not _positive_int(current_question_number)
            or current_question_number > MUSIC_QUESTION_TOTAL
            or not _nonnegative_int(current_question_started_ms)
            or current_question_started_ms > current_music_ms
            or final_results_started_ms is not None
        ):
            raise DomainError("invalid_input")
        return MusicTimingDecision(
            global_state=global_state,
            phase="question",
            music_clock=music_clock,
            advent_clock=advent_clock,
            current_question_number=current_question_number,
            current_question_started_ms=current_question_started_ms,
            gathering_remaining_ms=None,
            final_results_started_ms=None,
            final_results_remaining_ms=None,
            logical_transition_at=None,
        )
    if (
        phase != "final_results"
        or current_question_number is not None
        or current_question_started_ms is not None
        or not _nonnegative_int(final_results_started_ms)
    ):
        raise DomainError("invalid_input")
    if final_results_started_ms > current_music_ms:
        raise DomainError("invalid_input")

    expires_at_music_ms = (
        final_results_started_ms + final_results_duration_ms
    )
    remaining_ms = max(0, expires_at_music_ms - current_music_ms)
    if remaining_ms > 0 or global_state == "PAUSED":
        return MusicTimingDecision(
            global_state=global_state,
            phase="final_results",
            music_clock=music_clock,
            advent_clock=advent_clock,
            current_question_number=None,
            current_question_started_ms=None,
            gathering_remaining_ms=None,
            final_results_started_ms=final_results_started_ms,
            final_results_remaining_ms=remaining_ms,
            logical_transition_at=None,
        )

    # The active clock's anchor maps its persisted accumulator onto wall time.
    # Thus this value is stable even when expiry is first observed after restart.
    until_expiry_ms = max(
        0, expires_at_music_ms - music_clock.accumulated_ms
    )
    logical_expiry = music_clock.anchor + timedelta(milliseconds=until_expiry_ms)
    return MusicTimingDecision(
        global_state="ADVENT_QUIZ",
        phase="completed",
        music_clock=MusicClock(expires_at_music_ms, None),
        advent_clock=GameplayClock(advent_clock.accumulated_ms, logical_expiry),
        current_question_number=None,
        current_question_started_ms=None,
        gathering_remaining_ms=None,
        final_results_started_ms=final_results_started_ms,
        final_results_remaining_ms=0,
        logical_transition_at=logical_expiry,
    )
