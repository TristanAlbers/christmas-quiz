"""Serve only currently authorized private puzzle assets."""

from django.http import FileResponse, Http404
from django.utils.timezone import now as server_now
from django.views.decorators.cache import never_cache

from quiz import _application_core as core
from quiz.auth import actor_for_user
from quiz.configuration import (
    InvalidPackage,
    load_snapshot,
    puzzle_media_paths,
    snapshot_challenge_media_path,
    snapshot_media_path,
)
from quiz.contracts import ApplicationError
from quiz.domain.phase3 import effective_gameplay_ms, reconcile_freeze
from quiz.domain.phase6 import challenge_grace_remaining_ms
from quiz.domain.types import DomainError
from quiz.models import Challenge, Run, TeamRun
from quiz.persistence import read_snapshot


@never_cache
def private_media(request, run_id, team_id, asset_path):
    try:
        actor = actor_for_user(request.user)
    except ApplicationError as exc:
        raise Http404 from exc
    if actor.role != "team" or actor.team_id != team_id:
        raise Http404
    with read_snapshot():
        try:
            run = Run.objects.get(pk=run_id, active=True)
            config = load_snapshot(run)
            global_state, gameplay_ms, _, _ = core._effective_run_state(
                run,
                config,
                server_now(),
            )
            if global_state != "ADVENT_QUIZ":
                raise Http404
            team = TeamRun.objects.get(run=run, team_id=actor.team_id)
            effective_team = reconcile_freeze(
                team.activity_state,
                team.freeze_started_gameplay_ms,
                gameplay_ms,
            )
            if effective_team.activity_state != "PUZZLE":
                raise Http404
            puzzle = config["teams"][actor.team_id]["puzzles"][team.current_number - 1]
            if asset_path not in puzzle_media_paths(puzzle):
                raise Http404
            path = snapshot_media_path(run, actor.team_id, asset_path)
            if path is None:
                raise Http404
            file = path.open("rb")
        except (
            Run.DoesNotExist,
            TeamRun.DoesNotExist,
            DomainError,
            InvalidPackage,
            IndexError,
            OSError,
        ) as exc:
            raise Http404 from exc
    response = FileResponse(file)
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@never_cache
def challenge_media(request, run_id, challenge_id, asset_path):
    """Serve post-grace Challenge media to participants or admins only."""
    try:
        actor = actor_for_user(request.user)
    except ApplicationError as exc:
        raise Http404 from exc
    with read_snapshot():
        try:
            run = Run.objects.get(pk=run_id, active=True)
            challenge = Challenge.objects.get(pk=challenge_id, run=run)
            load_snapshot(run)
            gameplay_ms = effective_gameplay_ms(
                run.gameplay_elapsed_ms,
                run.advent_clock_anchor,
                server_now(),
            )
            if challenge_grace_remaining_ms(
                challenge.started_gameplay_ms, gameplay_ms
            ) > 0:
                raise Http404
            path = snapshot_challenge_media_path(
                run,
                challenge,
                actor_role=actor.role,
                actor_team_id=actor.team_id,
                relative_path=asset_path,
            )
            if path is None:
                raise Http404
            file = path.open("rb")
        except (
            Run.DoesNotExist,
            Challenge.DoesNotExist,
            DomainError,
            InvalidPackage,
            OSError,
        ) as exc:
            raise Http404 from exc
    response = FileResponse(file)
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
