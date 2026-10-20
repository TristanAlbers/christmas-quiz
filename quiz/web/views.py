import json
import uuid
from pathlib import Path
from typing import Literal, TypedDict

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.templatetags.static import static
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
    initiate_challenge,
    pause_game,
    provide_hint,
    purchase_hint,
    purchase_uno_reverse,
    reset_game,
    resume_game,
    skip_current,
    start_game,
    submit_answer,
    submit_challenge_answer,
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
    SubmitChallengeAnswer,
    SubmitMusicAnswer,
    TeamPuzzle,
)
from quiz.models import AuditEvent, PuzzleProgress, Run
from quiz.web.team_presentation import get_team_presentation_state


class RoutineFeedbackState(TypedDict):
    globalState: str
    teamState: str
    questionId: str | None
    musicPhase: str | None
    challengePhase: str | None
    firstFinisherTeamId: str | None
    gameplayElapsedMs: int


class RoutineFeedbackChocolate(TypedDict):
    subject: str
    staticUrl: str
    width: int
    height: int
    viewBox: str
    isBroad: bool


class RoutineFeedbackPuzzle(TypedDict, total=False):
    id: str
    number: int
    nextNumber: int
    chocolate: RoutineFeedbackChocolate


class RoutineFeedbackPayload(TypedDict, total=False):
    version: Literal[1]
    eventId: str
    actionId: str
    runId: str
    kind: Literal[
        "puzzle_solved", "puzzle_skipped", "reverse_purchased", "hint_purchased"
    ]
    state: RoutineFeedbackState
    puzzle: RoutineFeedbackPuzzle


_CHOCOLATE_MANIFEST = json.loads(
    (Path(__file__).resolve().parent.parent / "chocolate_manifest.json").read_text()
)
_CHOCOLATE_BY_DOOR = {
    item["door"]: item for item in _CHOCOLATE_MANIFEST["mapping"]
}

_ROUTINE_FEEDBACK_ACTIONS = {
    "answer": ("completed", "puzzle_solved"),
    "skip": ("completed", "puzzle_skipped"),
    "purchase_uno_reverse": ("purchased", "reverse_purchased"),
    "purchase_hint": ("purchased", "hint_purchased"),
}

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
    "challenge_spent": 409,
    "challenge_unavailable": 409,
    "challenge_starting": 409,
    "stale_challenge": 409,
}


def _error(exc):
    response = HttpResponse(exc.code.replace("_", " "), status=ERROR_STATUS[exc.code])
    response["Cache-Control"] = "no-store"
    return response


def _routine_feedback_was_already_accepted(actor, run_id, request_id, action):
    """Suppress a sequential retry; the stable event id also handles race retries."""
    expected = _ROUTINE_FEEDBACK_ACTIONS.get(action)
    if expected is None:
        return False
    try:
        request_uuid = uuid.UUID(request_id)
        run_uuid = uuid.UUID(run_id)
    except (AttributeError, TypeError, ValueError):
        return False
    return AuditEvent.objects.filter(
        run_id=run_uuid,
        actor_id=actor.user_id,
        request_id=request_uuid,
        action=action,
        result=expected[0],
    ).exists()


def _static_asset_url(path):
    try:
        return static(path)
    except ValueError:
        # Test/development environments may not have a collected manifest yet.
        return f"{settings.STATIC_URL.rstrip('/')}/{path}"


def _routine_feedback_payload(
    actor, state, request_id, action
) -> RoutineFeedbackPayload | None:
    """Build private presentation data from the committed audit/progress records."""
    expected = _ROUTINE_FEEDBACK_ACTIONS.get(action)
    if expected is None or state.run_id is None:
        return None
    if (
        state.global_state != "ADVENT_QUIZ"
        or state.team_state != "PUZZLE"
        or state.music is not None
        or (
            state.challenge is not None
            and state.challenge.phase in {"starting", "active"}
        )
    ):
        return None
    try:
        request_uuid = uuid.UUID(request_id)
    except (AttributeError, TypeError, ValueError):
        return None
    event = (
        AuditEvent.objects.filter(
            run_id=state.run_id,
            actor_id=actor.user_id,
            request_id=request_uuid,
            action=action,
            result=expected[0],
        )
        .only("id", "run_id", "puzzle_id")
        .first()
    )
    if event is None or not Run.objects.filter(pk=event.run_id, active=True).exists():
        return None

    payload: RoutineFeedbackPayload = {
        "version": 1,
        "eventId": f"{event.run_id}:{request_uuid}:{expected[1]}",
        "actionId": str(request_uuid),
        "runId": str(event.run_id),
        "kind": expected[1],
        "state": {
            "globalState": state.global_state,
            "teamState": state.team_state,
            "questionId": state.question.id if state.question is not None else None,
            "musicPhase": state.music.phase if state.music is not None else None,
            "challengePhase": (
                state.challenge.phase if state.challenge is not None else None
            ),
            "firstFinisherTeamId": state.first_finisher_team_id,
            "gameplayElapsedMs": state.gameplay_elapsed_ms,
        },
    }
    if action not in {"answer", "skip"}:
        return payload

    progress = (
        PuzzleProgress.objects.filter(
            run_id=event.run_id,
            team_id=actor.team_id,
            puzzle_id=event.puzzle_id,
            completed=True,
        )
        .only("puzzle_id", "number")
        .first()
    )
    # Final completion has its own authoritative victory presentation.
    if progress is None or progress.number == 25:
        return None
    chocolate = _CHOCOLATE_BY_DOOR[progress.number]
    chocolate_asset = _CHOCOLATE_MANIFEST["assets"][chocolate["subject"]]
    left, top, right, bottom = chocolate_asset["visible_bounds_alpha_gt_16"]
    puzzle: RoutineFeedbackPuzzle = {
        "id": progress.puzzle_id,
        "number": progress.number,
        "chocolate": {
            "subject": chocolate["subject"],
            "staticUrl": _static_asset_url(
                "quiz/chocolates/" + Path(chocolate["file"]).name
            ),
            "width": chocolate_asset["width"],
            "height": chocolate_asset["height"],
            "viewBox": (
                f"{left - 12} {top - 12} {right - left + 24} {bottom - top + 24}"
            ),
            "isBroad": chocolate["subject"] in {"iglo", "trein"},
        },
    }
    if state.question is not None:
        puzzle["nextNumber"] = state.question.number
    payload["puzzle"] = puzzle
    return payload


def _set_after_swap_triggers(response, *, shop_succeeded=False, routine=None):
    triggers = {}
    if shop_succeeded:
        triggers["shopPurchaseSucceeded"] = True
    if routine is not None:
        triggers["routineFeedbackConfirmed"] = routine
    if triggers:
        response["HX-Trigger-After-Swap"] = json.dumps(
            triggers, separators=(",", ":")
        )


def _question_context(state):
    question_id = state.question.id if state.question else ""
    hint_revealed = "1" if state.question and state.question.hint is not None else "0"
    music = state.music
    challenge = state.challenge
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
            challenge.status if challenge else "",
            challenge.phase if challenge else "",
            challenge.id if challenge else "",
            challenge.question.id if challenge and challenge.question else "",
        )
    )


def _team_actions_context(state, presentation=None):
    opponent_freeze_active = (
        presentation.opponent_freeze_active if presentation is not None else False
    )
    return ":".join(
        (
            state.run_id or "",
            state.global_state,
            state.team_state,
            "1" if state.uno_reverse_active else "0",
            "1" if opponent_freeze_active else "0",
            state.first_finisher_team_id or "",
            state.music.phase if state.music else "",
            "1" if state.challenge_available else "0",
            str(state.challenge_cost if state.challenge_cost is not None else ""),
            "1" if state.can_initiate_challenge else "0",
            state.challenge_ineligible_reason or "",
        )
    )


def _team_event_context(presentation):
    event = presentation.event
    return str(event.id) if event is not None else ""


def _music_final_winner(state):
    """Music champion derived only from the authoritative final score projection."""
    music = state.music
    if music is None or music.phase != "final_results" or len(music.scores) != 2:
        return None
    left, right = music.scores
    if left.score == right.score:
        return None
    return left.team_id if left.score > right.score else right.team_id


def _team_context(
    state,
    *,
    feedback="",
    replace_pane=False,
    replace_actions=False,
    update_resources=False,
    presentation_event=None,
    viewer_team_id="",
    presentation=None,
):
    if presentation is None:
        presentation = get_team_presentation_state(
            state.run_id, viewer_team_id, state.gameplay_elapsed_ms
        )
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
        "actions_context": _team_actions_context(state, presentation),
        "event_context": _team_event_context(presentation),
        "opponent_freeze_active": presentation.opponent_freeze_active,
        "presentation_event": presentation_event,
        "viewer_team_id": viewer_team_id,
        "music_winner_team_id": _music_final_winner(state),
        "request_id": str(uuid.uuid4()),
        "purchase_request_id": str(uuid.uuid4()),
        "use_request_id": str(uuid.uuid4()),
        "skip_request_id": str(uuid.uuid4()),
        "freeze_request_id": str(uuid.uuid4()),
        "reverse_request_id": str(uuid.uuid4()),
        "music_request_id": str(uuid.uuid4()),
        "challenge_request_id": str(uuid.uuid4()),
        "challenge_answer_request_id": str(uuid.uuid4()),
    }


def _admin_global_context(state):
    music_phase = state.music.phase if state.music else ""
    music_question = str(state.music.question_number or "") if state.music else ""
    challenge_phase = state.challenge.phase if state.challenge else ""
    challenge_id = state.challenge.id if state.challenge else ""
    return ":".join(
        (
            state.run_id or "",
            state.global_state,
            music_phase,
            music_question,
            challenge_phase,
            challenge_id,
        )
    )


def _admin_package_context(state):
    package_context = ",".join(
        f"{item.package_id}:{'1' if item.startable else '0'}" for item in state.packages
    )
    mode = "READY" if state.global_state == "READY" else "ACTIVE"
    return "|".join((mode, package_context))


def _admin_package_diagnostics_context(state):
    return repr(
        (
            state.discovery_error,
            tuple((item.package_id, item.diagnostic) for item in state.packages),
        )
    )


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
            "1" if team.challenge_available else "0",
        )
    )


def _admin_context(
    state,
    *,
    replace_package_controls=False,
    replace_package_diagnostics=False,
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
        "challenge": state.challenge,
        "first_finisher_team_id": state.first_finisher_team_id,
        "gameplay_elapsed_ms": state.gameplay_elapsed_ms,
        "has_startable_packages": any(item.startable for item in state.packages),
        "global_context": _admin_global_context(state),
        "package_context": _admin_package_context(state),
        "package_diagnostics_context": _admin_package_diagnostics_context(state),
        "team_a_context": _admin_team_context(state, "a"),
        "team_b_context": _admin_team_context(state, "b"),
        "replace_package_controls": replace_package_controls,
        "replace_package_diagnostics": replace_package_diagnostics,
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
        "music_winner_team_id": _music_final_winner(state),
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
    context = _team_context(state, viewer_team_id=actor.team_id)
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
    presentation = get_team_presentation_state(
        state.run_id, actor.team_id, state.gameplay_elapsed_ms
    )
    replace_actions = (
        request.GET.get("actions_context")
        != _team_actions_context(state, presentation)
    )
    presentation_event = (
        presentation.event
        if request.GET.get("event_context") != _team_event_context(presentation)
        else None
    )
    return render(
        request,
        "quiz/_team_state.html",
        _team_context(
            state,
            replace_pane=replace_pane,
            replace_actions=replace_actions,
            update_resources=True,
            presentation_event=presentation_event,
            viewer_team_id=actor.team_id,
            presentation=presentation,
        ),
    )


@never_cache
@require_POST
def team_answer(request):
    try:
        actor = actor_for_user(request.user)
        request_id = request.POST.get("request_id", "")
        run_id = request.POST.get("run_id", "")
        repeated_success = _routine_feedback_was_already_accepted(
            actor, run_id, request_id, "answer"
        )
        result = submit_answer(
            actor,
            SubmitAnswer(
                request_id=request_id,
                run_id=run_id,
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
    response = render(
        request,
        "quiz/_team_state.html",
        _team_context(
            result.state,
            feedback=feedback,
            replace_pane=True,
            replace_actions=True,
            update_resources=True,
            viewer_team_id=actor.team_id,
        ),
    )
    routine = None
    if result.outcome == "completed" and not repeated_success:
        routine = _routine_feedback_payload(actor, result.state, request_id, "answer")
    _set_after_swap_triggers(response, routine=routine)
    return response


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
            viewer_team_id=actor.team_id,
        ),
    )


@never_cache
@require_POST
def team_challenge_answer(request):
    try:
        actor = actor_for_user(request.user)
        result = submit_challenge_answer(
            actor,
            SubmitChallengeAnswer(
                request_id=request.POST.get("request_id", ""),
                run_id=request.POST.get("run_id", ""),
                challenge_id=request.POST.get("challenge_id", ""),
                question_id=request.POST.get("question_id", ""),
                answer=request.POST.get("answer", ""),
            ),
        )
    except ApplicationError as exc:
        return _error(exc)
    if not request.headers.get("HX-Request"):
        return redirect("team")
    feedback = (
        "Challenge won. The result is final."
        if result.outcome == "won"
        else "Incorrect Challenge answer. Keep trying."
    )
    resolved = result.outcome == "won"
    return render(
        request,
        "quiz/_team_state.html",
        _team_context(
            result.state,
            feedback=feedback,
            replace_pane=resolved,
            replace_actions=resolved,
            update_resources=resolved,
            viewer_team_id=actor.team_id,
        ),
    )


@never_cache
@require_GET
def overview(request):
    state = get_public_state()
    return render(request, "quiz/overview.html", _public_context(state))


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
            replace_package_diagnostics=(
                request.GET.get("package_diagnostics_context")
                != _admin_package_diagnostics_context(state)
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
        if exc.code == "invalid_input" and actor.role == "admin":
            # A rejected READY Start must show a Dutch, recoverable error while
            # leaving package validation and snapshot semantics server-owned.
            state = get_admin_state(actor)
            if state.global_state == "READY":
                context = _admin_context(state)
                context["error"] = (
                    "Spel starten is niet gelukt. Kies een geldig spelpakket "
                    "en controleer de validatiemeldingen."
                )
                return render(request, "quiz/admin.html", context, status=400)
        return _error(exc)
    return redirect("admin_game")


@never_cache
@require_POST
def team_action(request, action):
    try:
        actor = actor_for_user(request.user)
        request_id = request.POST.get("request_id", "")
        run_id = request.POST.get("run_id", "")
        base = dict(
            request_id=request_id,
            run_id=run_id,
        )
        routine_action = {
            "purchase-hint": "purchase_hint",
            "skip": "skip",
            "purchase-reverse": "purchase_uno_reverse",
        }.get(action)
        repeated_success = bool(
            routine_action
            and _routine_feedback_was_already_accepted(
                actor, run_id, request_id, routine_action
            )
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
        elif action == "challenge":
            result = initiate_challenge(actor, RunCommand(**base))
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
            "purchase-reverse": "Uno Reverse purchased and armed.",
            "challenge": "Challenge starting. Gather around!",
        }[action]
    )
    presentation = get_team_presentation_state(
        state.run_id, actor.team_id, state.gameplay_elapsed_ms
    )
    presentation_event = None
    if (
        action == "freeze"
        and request.POST.get("event_context") != _team_event_context(presentation)
    ):
        presentation_event = presentation.event
    if action in {"purchase-hint", "purchase-reverse"}:
        replace_pane = request.POST.get("view_context") != _question_context(state)
    else:
        replace_pane = action != "freeze" or state.team_state == "FREEZE"
    response = render(
        request,
        "quiz/_team_state.html",
        _team_context(
            state,
            feedback=feedback,
            # Preserve the exact answer input for a same-puzzle shop purchase
            # and an unchanged attacker's puzzle. A stale/missing context or
            # authoritative Reverse reflection still replaces the pane.
            replace_pane=replace_pane,
            replace_actions=True,
            update_resources=True,
            presentation_event=presentation_event,
            viewer_team_id=actor.team_id,
            presentation=presentation,
        ),
    )
    routine = None
    if routine_action is not None and not repeated_success:
        routine = _routine_feedback_payload(actor, state, request_id, routine_action)
    _set_after_swap_triggers(
        response,
        shop_succeeded=action
        in {"purchase-hint", "freeze", "purchase-reverse", "challenge"},
        routine=routine,
    )
    return response


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
            adjust_points(actor, AdminPoints(**base, team_id=team_id, delta=delta))
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
    global_change = action in ("pause", "resume", "reset") or bool(
        state.music or state.challenge
    )
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
