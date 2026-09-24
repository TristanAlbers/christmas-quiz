import uuid

from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from quiz.application import (
    adjust_points,
    admin_freeze,
    admin_unfreeze,
    force_complete_current,
    freeze_opponent,
    get_admin_state,
    get_public_state,
    get_team_state,
    pause_game,
    provide_hint,
    purchase_hint,
    purchase_uno_reverse,
    reset_game,
    resume_game,
    skip_current,
    start_game,
    submit_answer,
    submit_music_answer,
    use_hint,
)
from quiz.auth import actor_for_user
from quiz.contracts import (
    AdminPoints,
    AdminPuzzle,
    AdminTeam,
    ApplicationError,
    RunCommand,
    StartGame,
    SubmitAnswer,
    SubmitMusicAnswer,
    TeamPuzzle,
)

ERROR_STATUS = {
    "unauthenticated": 401,
    "forbidden": 403,
    "invalid_input": 400,
    "stale_run": 409,
    "stale_question": 409,
    "disallowed_state": 409,
    "request_conflict": 409,
    "temporarily_busy": 503,
    "insufficient_points": 409,
    "no_hint_tokens": 409,
    "already_active": 409,
}


def _error(exc):
    response = HttpResponse(exc.code.replace("_", " "), status=ERROR_STATUS[exc.code])
    response["Cache-Control"] = "no-store"
    return response


def _question_context(state):
    question_id = state.question.id if state.question else ""
    hint_revealed = "1" if state.question and state.question.hint is not None else "0"
    music = state.music
    return ":".join(
        (
            state.run_id or "",
            state.global_state,
            state.team_state,
            question_id,
            hint_revealed,
            music.phase if music else "",
            music.question_id or "" if music else "",
            str(music.question_number or "") if music else "",
        )
    )


def _team_actions_context(state):
    return ":".join(
        (
            state.run_id or "",
            state.global_state,
            state.team_state,
            "1" if state.uno_reverse_active else "0",
            state.first_finisher_team_id or "",
            state.music.phase if state.music else "",
        )
    )


def _team_context(
    state,
    *,
    feedback="",
    replace_pane=False,
    replace_actions=False,
    update_resources=False,
):
    return {
        "state": state,
        "advent_progress": state.advent_progress,
        "first_finisher_team_id": state.first_finisher_team_id,
        "gameplay_elapsed_ms": state.gameplay_elapsed_ms,
        "team_name": "A" if state.run_id is None else "",
        "feedback": feedback,
        "replace_pane": replace_pane,
        "replace_actions": replace_actions,
        "update_resources": update_resources,
        "view_context": _question_context(state),
        "actions_context": _team_actions_context(state),
        "request_id": str(uuid.uuid4()),
        "purchase_request_id": str(uuid.uuid4()),
        "use_request_id": str(uuid.uuid4()),
        "skip_request_id": str(uuid.uuid4()),
        "freeze_request_id": str(uuid.uuid4()),
        "reverse_request_id": str(uuid.uuid4()),
        "music_request_id": str(uuid.uuid4()),
    }


def _admin_global_context(state):
    music_phase = state.music.phase if state.music else ""
    music_question = str(state.music.question_number or "") if state.music else ""
    return ":".join(
        (state.run_id or "", state.global_state, music_phase, music_question)
    )


def _admin_package_context(state):
    package_context = ",".join(
        f"{item.package_id}:{'1' if item.startable else '0'}" for item in state.packages
    )
    mode = "READY" if state.global_state == "READY" else "ACTIVE"
    return "|".join((mode, package_context))


def _admin_team_context(state, team_id):
    team = next((item for item in state.teams if item.team_id == team_id), None)
    if team is None:
        return f"{state.run_id or ''}:{state.global_state}:{team_id}"
    return ":".join(
        (
            state.run_id or "",
            state.global_state,
            team_id,
            team.activity_state,
            team.current_question_id or "",
            "1" if team.hint_revealed else "0",
        )
    )


def _admin_context(
    state,
    *,
    replace_package_controls=False,
    replace_global_controls=False,
    replace_team_a_controls=False,
    replace_team_b_controls=False,
):
    team_controls = [
        {
            "team": team,
            "points_request_id": str(uuid.uuid4()),
            "force_request_id": str(uuid.uuid4()),
            "hint_request_id": str(uuid.uuid4()),
            "freeze_request_id": str(uuid.uuid4()),
            "unfreeze_request_id": str(uuid.uuid4()),
        }
        for team in state.teams
    ]
    controls_by_team = {control["team"].team_id: control for control in team_controls}
    return {
        "global_state": state.global_state,
        "run_id": state.run_id,
        "package_id": state.package_id,
        "teams": state.teams,
        "packages": state.packages,
        "discovery_error": state.discovery_error,
        "music": state.music,
        "first_finisher_team_id": state.first_finisher_team_id,
        "gameplay_elapsed_ms": state.gameplay_elapsed_ms,
        "has_startable_packages": any(item.startable for item in state.packages),
        "global_context": _admin_global_context(state),
        "package_context": _admin_package_context(state),
        "team_a_context": _admin_team_context(state, "a"),
        "team_b_context": _admin_team_context(state, "b"),
        "replace_package_controls": replace_package_controls,
        "replace_global_controls": replace_global_controls,
        "replace_team_a_controls": replace_team_a_controls,
        "replace_team_b_controls": replace_team_b_controls,
        "request_id": str(uuid.uuid4()),
        "pause_request_id": str(uuid.uuid4()),
        "resume_request_id": str(uuid.uuid4()),
        "reset_request_id": str(uuid.uuid4()),
        "team_controls": team_controls,
        "team_a_control": controls_by_team.get("a"),
        "team_b_control": controls_by_team.get("b"),
    }


def _public_audio_context(state):
    music = state.music
    return ":".join(
        (
            state.global_state,
            str(music.question_number or "") if music else "",
            music.audio_url or "" if music else "",
        )
    )


def _public_context(state, *, replace_audio=False):
    return {
        "state": state,
        "teams": state.teams,
        "first_finisher_team_id": state.first_finisher_team_id,
        "gameplay_elapsed_ms": state.gameplay_elapsed_ms,
        "audio_context": _public_audio_context(state),
        "replace_audio": replace_audio,
    }


def index(request):
    if request.user.is_authenticated:
        try:
            actor = actor_for_user(request.user)
        except ApplicationError as exc:
            return _error(exc)
        return redirect("team" if actor.role == "team" else "admin_game")
    return render(request, "quiz/index.html")


def health(request):
    return JsonResponse({"status": "ok"})


@never_cache
@require_GET
def team(request):
    try:
        actor = actor_for_user(request.user)
        state = get_team_state(actor)
    except ApplicationError as exc:
        if exc.code == "unauthenticated":
            return redirect("login")
        return _error(exc)
    context = _team_context(state)
    context["team_name"] = actor.team_id.upper()
    return render(request, "quiz/team.html", context)


@never_cache
@require_GET
def team_state(request):
    try:
        actor = actor_for_user(request.user)
        state = get_team_state(actor)
    except ApplicationError as exc:
        return _error(exc)
    replace_pane = request.GET.get("view_context") != _question_context(state)
    replace_actions = request.GET.get("actions_context") != _team_actions_context(state)
    return render(
        request,
        "quiz/_team_state.html",
        _team_context(
            state,
            replace_pane=replace_pane,
            replace_actions=replace_actions,
            update_resources=True,
        ),
    )


@never_cache
@require_POST
def team_answer(request):
    try:
        actor = actor_for_user(request.user)
        result = submit_answer(
            actor,
            SubmitAnswer(
                request_id=request.POST.get("request_id", ""),
                run_id=request.POST.get("run_id", ""),
                question_id=request.POST.get("question_id", ""),
                answer=request.POST.get("answer", ""),
            ),
        )
    except ApplicationError as exc:
        return _error(exc)
    if not request.headers.get("HX-Request"):
        return redirect("team")
    feedback = (
        "Correct answer. Puzzle completed."
        if result.outcome == "completed"
        else "Incorrect answer. Try again."
    )
    return render(
        request,
        "quiz/_team_state.html",
        _team_context(
            result.state,
            feedback=feedback,
            replace_pane=True,
            replace_actions=True,
            update_resources=True,
        ),
    )


@never_cache
@require_POST
def team_music_answer(request):
    try:
        actor = actor_for_user(request.user)
        result = submit_music_answer(
            actor,
            SubmitMusicAnswer(
                request_id=request.POST.get("request_id", ""),
                run_id=request.POST.get("run_id", ""),
                question_id=request.POST.get("question_id", ""),
                answer=request.POST.get("answer", ""),
            ),
        )
    except ApplicationError as exc:
        return _error(exc)
    if not request.headers.get("HX-Request"):
        return redirect("team")
    feedback = (
        "Correct. Your team won this Music question."
        if result.outcome == "won"
        else "Incorrect. Keep trying."
    )
    return render(
        request,
        "quiz/_team_state.html",
        _team_context(
            result.state,
            feedback=feedback,
            replace_pane=True,
            replace_actions=True,
            update_resources=True,
        ),
    )


@never_cache
@require_GET
def overview(request):
    state = get_public_state()
    return render(
        request,
        "quiz/overview.html",
        _public_context(state),
    )


@never_cache
@require_GET
def overview_state(request):
    state = get_public_state()
    return render(
        request,
        "quiz/_public_state.html",
        _public_context(
            state,
            replace_audio=(
                request.GET.get("audio_context") != _public_audio_context(state)
            ),
        ),
    )


@never_cache
@require_GET
def admin_game(request):
    try:
        actor = actor_for_user(request.user)
        status = get_admin_state(actor)
    except ApplicationError as exc:
        if exc.code == "unauthenticated":
            return redirect("admin_login")
        return _error(exc)
    return render(request, "quiz/admin.html", _admin_context(status))


@never_cache
@require_GET
def admin_state(request):
    try:
        actor = actor_for_user(request.user)
        state = get_admin_state(actor)
    except ApplicationError as exc:
        return _error(exc)
    return render(
        request,
        "quiz/_admin_state.html",
        _admin_context(
            state,
            replace_package_controls=(
                request.GET.get("package_context") != _admin_package_context(state)
            ),
            replace_global_controls=(
                request.GET.get("global_context") != _admin_global_context(state)
            ),
            replace_team_a_controls=(
                request.GET.get("team_a_context") != _admin_team_context(state, "a")
            ),
            replace_team_b_controls=(
                request.GET.get("team_b_context") != _admin_team_context(state, "b")
            ),
        ),
    )


@never_cache
@require_POST
def admin_start(request):
    try:
        actor = actor_for_user(request.user)
        start_game(
            actor,
            StartGame(
                request_id=request.POST.get("request_id", ""),
                package_id=request.POST.get("package_id", ""),
            ),
        )
    except ApplicationError as exc:
        return _error(exc)
    return redirect("admin_game")


@never_cache
@require_POST
def team_action(request, action):
    try:
        actor = actor_for_user(request.user)
        base = dict(
            request_id=request.POST.get("request_id", ""),
            run_id=request.POST.get("run_id", ""),
        )
        if action == "purchase-hint":
            result = purchase_hint(actor, RunCommand(**base))
        elif action == "use-hint":
            result = use_hint(
                actor,
                TeamPuzzle(**base, question_id=request.POST.get("question_id", "")),
            )
        elif action == "skip":
            result = skip_current(
                actor,
                TeamPuzzle(**base, question_id=request.POST.get("question_id", "")),
            )
        elif action == "freeze":
            result = freeze_opponent(actor, RunCommand(**base))
        elif action == "purchase-reverse":
            result = purchase_uno_reverse(actor, RunCommand(**base))
        else:
            return HttpResponse(status=404)
        state = get_team_state(actor)
    except ApplicationError as exc:
        return _error(exc)
    if not request.headers.get("HX-Request"):
        return redirect("team")
    feedback = (
        "Hint was already revealed. No token used."
        if result.outcome == "already_revealed"
        else {
            "purchase-hint": "Hint token purchased.",
            "use-hint": "Hint revealed.",
            "skip": "Puzzle skipped and completed.",
            "freeze": (
                "The opposing team's Reverse redirected the Freeze to you."
                if result.outcome == "reversed"
                else "The opposing team is frozen."
            ),
            "purchase-reverse": "Uno Reverse activated.",
        }[action]
    )
    return render(
        request,
        "quiz/_team_state.html",
        _team_context(
            state,
            feedback=feedback,
            replace_pane=True,
            replace_actions=True,
            update_resources=True,
        ),
    )


@never_cache
@require_POST
def admin_action(request, action):
    try:
        actor = actor_for_user(request.user)
        base = dict(
            request_id=request.POST.get("request_id", ""),
            run_id=request.POST.get("run_id", ""),
        )
        team_id = request.POST.get("team_id", "")
        if action == "pause":
            pause_game(actor, RunCommand(**base))
        elif action == "resume":
            resume_game(actor, RunCommand(**base))
        elif action == "reset":
            reset_game(actor, RunCommand(**base))
        elif action == "points":
            try:
                delta = int(request.POST.get("delta", ""))
            except (TypeError, ValueError) as exc:
                raise ApplicationError("invalid_input") from exc
            adjust_points(
                actor,
                AdminPoints(
                    **base,
                    team_id=team_id,
                    delta=delta,
                ),
            )
        elif action in ("force-complete", "provide-hint"):
            command = AdminPuzzle(
                **base,
                team_id=team_id,
                question_id=request.POST.get("question_id", ""),
            )
            if action == "force-complete":
                force_complete_current(actor, command)
            else:
                provide_hint(actor, command)
        elif action in ("freeze", "unfreeze"):
            command = AdminTeam(**base, team_id=team_id)
            if action == "freeze":
                admin_freeze(actor, command)
            else:
                admin_unfreeze(actor, command)
        else:
            return HttpResponse(status=404)
    except ApplicationError as exc:
        return _error(exc)
    if not request.headers.get("HX-Request"):
        return redirect("admin_game")

    state = get_admin_state(actor)
    global_change = action in ("pause", "resume", "reset") or bool(state.music)
    return render(
        request,
        "quiz/_admin_state.html",
        _admin_context(
            state,
            replace_package_controls=action == "reset",
            replace_global_controls=global_change,
            replace_team_a_controls=global_change or team_id == "a",
            replace_team_b_controls=global_change or team_id == "b",
        ),
    )
