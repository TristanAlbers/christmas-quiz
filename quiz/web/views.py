import uuid

from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from quiz.application import (
    get_admin_status,
    get_team_state,
    start_game,
    submit_answer,
)
from quiz.auth import actor_for_user
from quiz.contracts import ApplicationError, StartGame, SubmitAnswer

ERROR_STATUS = {
    "unauthenticated": 401,
    "forbidden": 403,
    "invalid_input": 400,
    "stale_run": 409,
    "stale_question": 409,
    "disallowed_state": 409,
    "request_conflict": 409,
    "temporarily_busy": 503,
}


def _error(exc):
    response = HttpResponse(exc.code.replace("_", " "), status=ERROR_STATUS[exc.code])
    response["Cache-Control"] = "no-store"
    return response


def _context(state):
    question_id = state.question.id if state.question else ""
    return ":".join(
        (state.run_id or "", state.global_state, state.team_state, question_id)
    )


def _team_context(state, *, feedback="", replace_pane=False):
    return {
        "state": state,
        "team_name": "A" if state.run_id is None else "",
        "feedback": feedback,
        "replace_pane": replace_pane,
        "view_context": _context(state),
        "request_id": str(uuid.uuid4()),
    }


def index(request):
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
        status = get_admin_status(actor)
    except ApplicationError as exc:
        if exc.code == "unauthenticated":
            return redirect("admin_login")
        return _error(exc)
    return render(
        request,
        "quiz/admin.html",
        {
            "global_state": status.global_state if status else "READY",
            "run_id": status.run_id if status else None,
            "request_id": str(uuid.uuid4()),
        },
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
