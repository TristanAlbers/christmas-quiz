"""Serve only a team's currently visible private puzzle assets."""

from django.http import FileResponse, Http404
from django.views.decorators.cache import never_cache

from quiz.auth import actor_for_user
from quiz.configuration import InvalidPackage, load_snapshot, snapshot_media_path
from quiz.contracts import ApplicationError
from quiz.models import Run, TeamRun
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
            run = Run.objects.get(pk=run_id, active=True, global_state="ADVENT_QUIZ")
            team = TeamRun.objects.get(
                run=run, team_id=actor.team_id, activity_state="PUZZLE"
            )
            config = load_snapshot(run)
            puzzle = config["teams"][actor.team_id]["puzzles"][team.current_number - 1]
            if asset_path not in puzzle["media"]:
                raise Http404
            path = snapshot_media_path(run, actor.team_id, asset_path)
            if path is None:
                raise Http404
            file = path.open("rb")
        except (
            Run.DoesNotExist,
            TeamRun.DoesNotExist,
            InvalidPackage,
            IndexError,
            OSError,
        ) as exc:
            raise Http404 from exc
    response = FileResponse(file)
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
