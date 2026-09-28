"""Stable application facade.

The pre-Phase-6 use cases remain in `_application_core`. Challenge-specific
projection/command behavior is layered in `phase6_application` so the amended
Phase-6 contract can evolve without duplicating or destabilizing unrelated game
flows. Existing `quiz.application` imports remain the supported API.
"""

from dataclasses import replace

from . import _application_core as _core
from ._application_core import *  # noqa: F403
from .contracts import (
    AnswerResult,
    MusicAnswerResult,
    PublicAdventTeamProgressProjection,
)
from .models import Run, TeamRun
from .persistence import read_snapshot
from .phase6_application import (  # noqa: F401
    get_admin_state,
    get_team_state,
    initiate_challenge,
    submit_challenge_answer,
)
from .phase6_application import get_public_state as _phase6_get_public_state


def _enrich_active_team_state(actor, state, *, now=None):
    """Refresh presentation metadata only when the receipt's run is still active."""
    if state.run_id is None:
        return state
    if not Run.objects.filter(pk=state.run_id, active=True).exists():
        return state
    return get_team_state(actor, now=now)


def submit_answer(actor, command, *, now=None):
    """Preserve the core answer transaction and enrich active team presentation."""
    result = _core.submit_answer(actor, command, now=now)
    return AnswerResult(
        result.outcome,
        _enrich_active_team_state(actor, result.state, now=now),
    )


def submit_music_answer(actor, command, *, now=None):
    """Keep Music idempotency intact while enriching a returned Advent puzzle."""
    result = _core.submit_music_answer(actor, command, now=now)
    return MusicAnswerResult(
        result.outcome,
        _enrich_active_team_state(actor, result.state, now=now),
    )


def get_public_state(*, now=None):
    """Apply the approved coarse public Freeze projection to Advent overview state."""
    with read_snapshot():
        # Keep the base public projection and the coarse Freeze enrichment in one
        # read snapshot so a concurrent reset/start cannot mix two different runs.
        state = _phase6_get_public_state(now=now)
        if (
            not state.teams
            or state.music is not None
            or state.challenge is not None
            or state.global_state not in {"ADVENT_QUIZ", "PAUSED"}
        ):
            return state

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
            is_frozen = False
            if row is not None:
                effective = _core.reconcile_freeze(
                    row.activity_state,
                    row.freeze_started_gameplay_ms,
                    state.gameplay_elapsed_ms,
                )
                is_frozen = effective.activity_state == "FREEZE"
            teams.append(
                PublicAdventTeamProgressProjection(
                    team_id=projection.team_id,
                    advent_progress=projection.advent_progress,
                    is_frozen=is_frozen,
                )
            )
        return replace(state, teams=tuple(teams))


def __getattr__(name):
    """Preserve access to private helpers used by focused legacy tests."""
    return getattr(_core, name)
