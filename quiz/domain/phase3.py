"""Deterministic gameplay-clock, Freeze, and Uno Reverse policies.

The application supplies persisted values and an aware server time, then commits
accepted decisions inside its transaction.  This module never reads a wall clock
or persistence layer itself.
"""

from dataclasses import dataclass, replace
from datetime import datetime

from .types import DomainError

FREEZE_DURATION_MS = 300_000
_TEAM_STATES = frozenset({"READY", "PUZZLE", "FREEZE", "CHALLENGE", "FINISHED"})


@dataclass(frozen=True)
class GameplayClock:
    accumulated_ms: int
    anchor: datetime | None


@dataclass(frozen=True)
class ClockTransition:
    global_state: str
    clock: GameplayClock


@dataclass(frozen=True)
class FreezeState:
    activity_state: str
    freeze_started_ms: int | None


@dataclass(frozen=True)
class EffectTeamState:
    activity_state: str
    points: int
    freeze_started_ms: int | None = None
    uno_reverse_active: bool = False


@dataclass(frozen=True)
class FreezeDecision:
    team: EffectTeamState


@dataclass(frozen=True)
class FreezeAttackDecision:
    attacker: EffectTeamState
    target: EffectTeamState
    reversed: bool
    points_delta: int


@dataclass(frozen=True)
class UnoReverseDecision:
    team: EffectTeamState
    points_delta: int


def _nonnegative_int(value: object) -> bool:
    return type(value) is int and value >= 0


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _validate_clock_input(
    accumulated_ms: int, anchor: datetime | None, now: datetime
) -> None:
    if (
        not _nonnegative_int(accumulated_ms)
        or (anchor is not None and not _aware(anchor))
        or not _aware(now)
    ):
        raise DomainError("invalid_input")


def effective_gameplay_ms(
    accumulated_ms: int, anchor: datetime | None, now: datetime
) -> int:
    """Return recoverable Advent gameplay time from persisted clock values.

    A present anchor means Advent gameplay is running, including through process
    downtime.  A stopped clock has no anchor.  Backward wall-clock movement is
    clamped, so the effective value never falls below the persisted accumulator.
    Sub-millisecond wall-clock precision is intentionally discarded.
    """
    _validate_clock_input(accumulated_ms, anchor, now)
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


def pause_gameplay_clock(
    global_state: str,
    accumulated_ms: int,
    anchor: datetime | None,
    now: datetime,
) -> ClockTransition:
    """Stop an active Advent clock after reconciling its elapsed duration."""
    if global_state != "ADVENT_QUIZ":
        raise DomainError("disallowed_state")
    _validate_clock_input(accumulated_ms, anchor, now)
    if anchor is None:
        raise DomainError("invalid_input")
    return ClockTransition(
        global_state="PAUSED",
        clock=GameplayClock(effective_gameplay_ms(accumulated_ms, anchor, now), None),
    )


def resume_gameplay_clock(
    global_state: str,
    accumulated_ms: int,
    anchor: datetime | None,
    now: datetime,
) -> ClockTransition:
    """Resume a stopped paused clock without changing accumulated gameplay."""
    if global_state != "PAUSED":
        raise DomainError("disallowed_state")
    _validate_clock_input(accumulated_ms, anchor, now)
    if anchor is not None:
        raise DomainError("invalid_input")
    return ClockTransition(
        global_state="ADVENT_QUIZ",
        clock=GameplayClock(accumulated_ms, now),
    )


def freeze_remaining_ms(
    freeze_started_ms: int | None, current_gameplay_ms: int
) -> int | None:
    """Return remaining Freeze time; zero is expired and ``None`` is absent."""
    if not _nonnegative_int(current_gameplay_ms) or (
        freeze_started_ms is not None
        and not _nonnegative_int(freeze_started_ms)
    ):
        raise DomainError("invalid_input")
    if freeze_started_ms is None:
        return None
    if freeze_started_ms > current_gameplay_ms:
        raise DomainError("invalid_input")
    return max(0, freeze_started_ms + FREEZE_DURATION_MS - current_gameplay_ms)


def reconcile_freeze(
    activity_state: str,
    freeze_started_ms: int | None,
    current_gameplay_ms: int,
) -> FreezeState:
    """Project logical Freeze expiry without requiring a persistence write."""
    if activity_state not in _TEAM_STATES:
        raise DomainError("invalid_input")
    if activity_state == "FREEZE":
        if freeze_started_ms is None:
            raise DomainError("invalid_input")
        remaining = freeze_remaining_ms(freeze_started_ms, current_gameplay_ms)
        if remaining == 0:
            return FreezeState("PUZZLE", None)
        return FreezeState("FREEZE", freeze_started_ms)
    if freeze_started_ms is not None:
        raise DomainError("invalid_input")
    if not _nonnegative_int(current_gameplay_ms):
        raise DomainError("invalid_input")
    return FreezeState(activity_state, None)


def _reconcile_team(
    team: EffectTeamState, current_gameplay_ms: int
) -> EffectTeamState:
    if (
        not isinstance(team, EffectTeamState)
        or not _nonnegative_int(team.points)
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


def apply_direct_freeze(
    global_state: str,
    team: EffectTeamState,
    current_gameplay_ms: int,
) -> FreezeDecision:
    """Apply canonical Freeze directly, without Reverse routing or a cost.

    This is the route for an admin action and, in a later phase, Challenge loss.
    Admin Freeze is allowed while paused and starts at the stopped gameplay time.
    """
    if global_state not in {"ADVENT_QUIZ", "PAUSED"}:
        raise DomainError("disallowed_state")
    reconciled = _reconcile_team(team, current_gameplay_ms)
    if reconciled.activity_state == "FREEZE":
        raise DomainError("already_active")
    if reconciled.activity_state != "PUZZLE":
        raise DomainError("disallowed_state")
    return FreezeDecision(
        replace(
            reconciled,
            activity_state="FREEZE",
            freeze_started_ms=current_gameplay_ms,
        )
    )


def remove_freeze(
    global_state: str,
    team: EffectTeamState,
    current_gameplay_ms: int,
) -> FreezeDecision:
    """Remove an active Freeze immediately; no timer remains."""
    if global_state not in {"ADVENT_QUIZ", "PAUSED"}:
        raise DomainError("disallowed_state")
    reconciled = _reconcile_team(team, current_gameplay_ms)
    if reconciled.activity_state != "FREEZE":
        raise DomainError("disallowed_state")
    return FreezeDecision(
        replace(reconciled, activity_state="PUZZLE", freeze_started_ms=None)
    )


def resolve_freeze_attack(
    global_state: str,
    attacker: EffectTeamState,
    target: EffectTeamState,
    current_gameplay_ms: int,
    cost: int,
) -> FreezeAttackDecision:
    """Resolve one paid player attack, including optional Reverse redirection."""
    if global_state != "ADVENT_QUIZ":
        raise DomainError("disallowed_state")
    if not _nonnegative_int(cost):
        raise DomainError("invalid_input")
    attacker = _reconcile_team(attacker, current_gameplay_ms)
    target = _reconcile_team(target, current_gameplay_ms)
    if target.activity_state == "FREEZE":
        raise DomainError("already_active")
    if attacker.activity_state != "PUZZLE" or target.activity_state != "PUZZLE":
        raise DomainError("disallowed_state")
    if attacker.points < cost:
        raise DomainError("insufficient_points")

    attacker = replace(attacker, points=attacker.points - cost)
    if target.uno_reverse_active:
        target = replace(target, uno_reverse_active=False)
        attacker = replace(
            attacker,
            activity_state="FREEZE",
            freeze_started_ms=current_gameplay_ms,
        )
        reversed_attack = True
    else:
        target = replace(
            target,
            activity_state="FREEZE",
            freeze_started_ms=current_gameplay_ms,
        )
        reversed_attack = False

    return FreezeAttackDecision(
        attacker=attacker,
        target=target,
        reversed=reversed_attack,
        points_delta=-cost,
    )


def purchase_uno_reverse(
    global_state: str,
    team: EffectTeamState,
    current_gameplay_ms: int,
    cost: int,
) -> UnoReverseDecision:
    """Pay for the team's single durable active Uno Reverse."""
    if global_state != "ADVENT_QUIZ":
        raise DomainError("disallowed_state")
    if not _nonnegative_int(cost):
        raise DomainError("invalid_input")
    team = _reconcile_team(team, current_gameplay_ms)
    if team.activity_state != "PUZZLE":
        raise DomainError("disallowed_state")
    if team.uno_reverse_active:
        raise DomainError("already_active")
    if team.points < cost:
        raise DomainError("insufficient_points")
    return UnoReverseDecision(
        team=replace(team, points=team.points - cost, uno_reverse_active=True),
        points_delta=-cost,
    )
