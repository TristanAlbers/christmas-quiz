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


def _context(state):
    question_id = state.question.id if state.question else ""
    hint_revealed = "1" if state.question and state.question.hint is not None else "0"
    return ":".join(
        (
            state.run_id or "",
            state.global_state,
            state.team_state,
            question_id,
            hint_revealed,
        )
    )


def _team_context(state, *, feedback="", replace_pane=False):
    return {
        "state": state,
        "team_name": "A" if state.run_id is None else "",
        "feedback": feedback,
        "replace_pane": replace_pane,
        "view_context": _context(state),
        "request_id": str(uuid.uuid4()),
        "purchase_request_id": str(uuid.uuid4()),
        "use_request_id": str(uuid.uuid4()),
        "skip_request_id": str(uuid.uuid4()),
        "freeze_request_id": str(uuid.uuid4()),
        "reverse_request_id": str(uuid.uuid4()),
    }


def _admin_context(state):
    return {
        "global_state": state.global_state,
        "run_id": state.run_id,
        "package_id": state.package_id,
        "teams": state.teams,
        "request_id": str(uuid.uuid4()),
        "pause_request_id": str(uuid.uuid4()),
        "resume_request_id": str(uuid.uuid4()),
        "reset_request_id": str(uuid.uuid4()),
        "team_controls": [
            {
                "team": team,
                "points_request_id": str(uuid.uuid4()),
                "force_request_id": str(uuid.uuid4()),
                "hint_request_id": str(uuid.uuid4()),
                "freeze_request_id": str(uuid.uuid4()),
                "unfreeze_request_id": str(uuid.uuid4()),
            }
            for team in state.teams
        ],
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
    replace = request.GET.get("view_context") != _context(state)
    return render(
        request,
        "quiz/_team_state.html",
        _team_context(state, replace_pane=replace),
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
        _team_context(result.state, feedback=feedback, replace_pane=True),
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
    return render(request, "quiz/_admin_state.html", _admin_context(state))


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
            result = use_hint(actor, TeamPuzzle(
                **base, question_id=request.POST.get("question_id", "")
            ))
        elif action == "skip":
            result = skip_current(actor, TeamPuzzle(
                **base, question_id=request.POST.get("question_id", "")
            ))
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
        request, "quiz/_team_state.html",
        _team_context(state, feedback=feedback, replace_pane=True),
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
            adjust_points(actor, AdminPoints(
                **base, team_id=request.POST.get("team_id", ""), delta=delta,
            ))
        elif action in ("force-complete", "provide-hint"):
            command = AdminPuzzle(
                **base, team_id=request.POST.get("team_id", ""),
                question_id=request.POST.get("question_id", ""),
            )
            if action == "force-complete":
                force_complete_current(actor, command)
            else:
                provide_hint(actor, command)
        elif action in ("freeze", "unfreeze"):
            command = AdminTeam(
                **base, team_id=request.POST.get("team_id", "")
            )
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
    return render(
        request, "quiz/_admin_state.html", _admin_context(get_admin_state(actor))
    )
