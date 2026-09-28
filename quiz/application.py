"""Stable application facade.

The pre-Phase-6 use cases remain in `_application_core`. Challenge-specific
projection/command behavior is layered in `phase6_application` so the amended
Phase-6 contract can evolve without duplicating or destabilizing unrelated game
flows. Existing `quiz.application` imports remain the supported API.
"""

from dataclasses import replace

from . import _application_core as _core
from ._application_core import *  # noqa: F403
from .models import Run, TeamRun
from .persistence import read_snapshot
from .phase6_application import (  # noqa: F401
    get_admin_state,
    get_public_state as _phase6_get_public_state,
    get_team_state,
    initiate_challenge,
    submit_challenge_answer,
)


def get_public_state(*, now=None):
    """Apply the approved coarse public Freeze projection to Advent overview state."""
    state = _phase6_get_public_state(now=now)
    if (
        not state.teams
        or state.music is not None
        or state.challenge is not None
        or state.global_state not in {"ADVENT_QUIZ", "PAUSED"}
    ):
        return state

    with read_snapshot():
        run = Run.objects.filter(active=True).first()
        if run is None:
            return state
        rows = {
            team.team_id: team
            for team in TeamRun.objects.filter(run=run).only(
                "team_id", "activity_state", "freeze_started_gameplay_ms"
            )
        }
        teams = []
        for projection in state.teams:
            row = rows.get(projection.team_id)
            if row is None:
                teams.append(projection)
                continue
            effective = _core.reconcile_freeze(
                row.activity_state,
                row.freeze_started_gameplay_ms,
                state.gameplay_elapsed_ms,
            )
            teams.append(
                replace(
                    projection,
                    is_frozen=effective.activity_state == "FREEZE",
                )
            )
        return replace(state, teams=tuple(teams))


def __getattr__(name):
    """Preserve access to private helpers used by focused legacy tests."""
    return getattr(_core, name)
