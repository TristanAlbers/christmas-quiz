"""Authoritative synchronous use cases for the first persisted game slice."""

import hashlib
import json
import uuid
from dataclasses import asdict

from django.contrib.auth import get_user_model
from django.db import OperationalError
from django.urls import reverse
from django.utils import timezone

from quiz.configuration import InvalidPackage, load_snapshot, stage_snapshot
from quiz.contracts import (
    Actor,
    AdminPoints,
    AdminProjection,
    AdminPuzzle,
    AdminTeamProjection,
    AnswerResult,
    ApplicationError,
    CommandResult,
    QuestionProjection,
    RunCommand,
    StartGame,
    StartResult,
    SubmitAnswer,
    TeamProjection,
    TeamPuzzle,
)
from quiz.domain import (
    CompletionState,
    DomainError,
    PuzzleCompletion,
    complete_puzzle,
    evaluate_answer,
)
from quiz.domain.phase2 import (
    adjust_points as decide_points,
)
from quiz.domain.phase2 import (
    pause_game as decide_pause,
)
from quiz.domain.phase2 import (
    pay_skip,
)
from quiz.domain.phase2 import (
    purchase_hint as decide_hint_purchase,
)
from quiz.domain.phase2 import (
    resume_game as decide_resume,
)
from quiz.domain.phase2 import (
    reveal_hint as decide_hint_reveal,
)
from quiz.models import (
    AccountRole,
    AnswerReceipt,
    Attempt,
    AuditEvent,
    CommandReceipt,
    FragmentAward,
    HintReveal,
    PuzzleProgress,
    Run,
    StartReceipt,
    TeamRun,
)
from quiz.persistence import immediate_transaction, is_busy_error, read_snapshot


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ApplicationError("invalid_input") from exc


def _digest(action: str, actor: Actor, payload: dict) -> str:
    raw = json.dumps(
        {"action": action, "actor": actor.user_id, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def _verify_actor(actor: Actor, role: str) -> None:
    """Recheck roles from the database; callers can construct Actor values."""
    if not isinstance(actor, Actor):
        raise ApplicationError("unauthenticated")
    user = get_user_model().objects.filter(pk=actor.user_id, is_active=True).first()
    if user is None:
        raise ApplicationError("unauthenticated")
    account = AccountRole.objects.filter(user_id=actor.user_id).first()
    if (
        account is None
        or account.role != actor.role
        or account.team_id != actor.team_id
    ):
        raise ApplicationError("forbidden")
    if account.role != role:
        raise ApplicationError("forbidden")


def _projection(run: Run | None, team_id: str) -> TeamProjection:
    if run is None:
        return TeamProjection(None, "READY", "READY", 0, None, (), (), None)
    team = TeamRun.objects.get(run=run, team_id=team_id)
    config = load_snapshot(run)
    progress = list(PuzzleProgress.objects.filter(run=run, team_id=team_id))
    completed = tuple(sorted(row.number for row in progress if row.completed))
    fragments = tuple(
        FragmentAward.objects.filter(run=run, team_id=team_id)
        .order_by("awarded_at", "pk")
        .values_list("fragment", flat=True)
    )
    question = None
    if run.global_state == "ADVENT_QUIZ" and team.activity_state == "PUZZLE":
        puzzles = config["teams"][team_id]["puzzles"]
        if team.current_number <= len(puzzles) and team.current_number not in completed:
            item = puzzles[team.current_number - 1]
            reveal = HintReveal.objects.filter(
                run=run, team_id=team_id, puzzle_id=item["id"]
            ).exists()
            question = QuestionProjection(
                id=item["id"],
                number=item["number"],
                title=item["title"],
                body=item["body"],
                media_urls=tuple(
                    reverse(
                        "private_media",
                        kwargs={
                            "run_id": run.id,
                            "team_id": team_id,
                            "asset_path": path,
                        },
                    )
                    for path in item["media"]
                ),
                hint=item["hint"] if reveal else None,
                hint_available=item["hint"] is not None,
            )
    return TeamProjection(
        run_id=str(run.id),
        global_state=run.global_state,
        team_state=team.activity_state,
        points=team.points,
        current_number=team.current_number,
        completed_numbers=completed,
        fragments=fragments,
        question=question,
        hint_tokens=team.hint_tokens,
        hint_cost=config.get("hint_cost"),
        skip_cost=config.get("skip_cost"),
    )


def _restore_answer(value: dict) -> AnswerResult:
    data = value["state"].copy()
    data["completed_numbers"] = tuple(data["completed_numbers"])
    data["fragments"] = tuple(data["fragments"])
    if data["question"] is not None:
        question = data["question"].copy()
        question["media_urls"] = tuple(question["media_urls"])
        data["question"] = QuestionProjection(**question)
    return AnswerResult(value["outcome"], TeamProjection(**data))


def _active_run(run_id: uuid.UUID) -> Run:
    run = Run.objects.filter(pk=run_id, active=True).first()
    if run is None:
        raise ApplicationError("stale_run")
    return run


def _receipt(actor: Actor, request_id: uuid.UUID, digest: str):
    row = CommandReceipt.objects.filter(
        actor_id=actor.user_id, request_id=request_id
    ).first()
    if row is None:
        return None
    if row.payload_digest != digest:
        raise ApplicationError("request_conflict")
    return CommandResult(**row.result)


def _save_receipt(run, actor, request_id, action, digest, result):
    CommandReceipt.objects.create(
        run=run,
        actor_id=actor.user_id,
        request_id=request_id,
        action=action,
        payload_digest=digest,
        result=asdict(result),
    )


def _event(
    run, actor, request_id, action, result, *, team_id=None, puzzle_id="", changes=None
):
    AuditEvent.objects.create(
        run=run,
        request_id=request_id,
        actor_id=actor.user_id,
        actor_role=actor.role,
        team_id=team_id,
        action=action,
        result=result,
        puzzle_id=puzzle_id,
        changes=changes or {},
    )


def _command_identity(actor, command, action, payload):
    request_id = _uuid(command.request_id)
    run_id = _uuid(command.run_id)
    digest = _digest(action, actor, {"run_id": str(run_id), **payload})
    return request_id, run_id, digest


def _command_result(outcome, run):
    return CommandResult(outcome, str(run.id), run.global_state)


def _current_puzzle(run, team_id, question_id):
    if run.global_state != "ADVENT_QUIZ":
        raise ApplicationError("disallowed_state")
    team = TeamRun.objects.get(run=run, team_id=team_id)
    if team.activity_state != "PUZZLE":
        raise ApplicationError("disallowed_state")
    config = load_snapshot(run)
    puzzles = config["teams"][team_id]["puzzles"]
    if team.current_number > len(puzzles):
        raise ApplicationError("disallowed_state")
    puzzle = puzzles[team.current_number - 1]
    if question_id != puzzle["id"]:
        raise ApplicationError("stale_question")
    progress = list(PuzzleProgress.objects.filter(run=run, team_id=team_id))
    current = next(row for row in progress if row.number == team.current_number)
    if current.completed or any(
        not row.completed for row in progress if row.number < team.current_number
    ):
        raise ApplicationError("stale_question")
    return team, config, puzzles, puzzle, progress, current


def _complete_current(
    run, actor, team_id, team, puzzles, puzzle, progress, current, route, *, cost=0
):
    # The phase-4 Music interruption is mandatory on puzzle 13. Until it exists,
    # do not open that puzzle through any completion route.
    if puzzle["number"] >= 13 or (puzzle["number"] == 12 and len(puzzles) >= 13):
        raise ApplicationError("disallowed_state")
    awarded_ids = set(
        FragmentAward.objects.filter(run=run, team_id=team_id).values_list(
            "puzzle_id", flat=True
        )
    )
    state = CompletionState(
        global_state=run.global_state,
        team_state=team.activity_state,
        current_number=team.current_number,
        points=team.points,
        completed_numbers=frozenset(row.number for row in progress if row.completed),
        rewarded_numbers=frozenset(
            row.number for row in progress if row.reward_awarded
        ),
        fragment_awarded_numbers=frozenset(
            row.number for row in progress if row.puzzle_id in awarded_ids
        ),
    )
    completion = PuzzleCompletion(
        number=puzzle["number"],
        reward_points=puzzle["reward_points"],
        fragment=puzzle["fragment"],
        next_number=(
            team.current_number + 1 if team.current_number < len(puzzles) else None
        ),
    )
    decision = (
        pay_skip(state, completion, cost)
        if route == "skip"
        else complete_puzzle(state, completion, route)
    )
    prior_points = team.points
    prior_number = team.current_number
    reward = 0 if current.reward_awarded else puzzle["reward_points"]
    current.completed = True
    current.completion_route = decision.route
    current.reward_awarded = True
    current.completed_at = timezone.now()
    current.save(
        update_fields=[
            "completed", "completion_route", "reward_awarded", "completed_at"
        ]
    )
    team.points = decision.state.points
    team.current_number = decision.state.current_number
    team.save(update_fields=["points", "current_number"])
    if decision.fragment_award is not None:
        FragmentAward.objects.create(
            run=run,
            team_id=team_id,
            puzzle_id=puzzle["id"],
            fragment=decision.fragment_award,
        )
    return {
        "points": {
            "previous": prior_points,
            "delta": team.points - prior_points,
            "new": team.points,
        },
        "current_number": {"previous": prior_number, "new": team.current_number},
        "completed": {"previous": False, "new": True},
        "fragment": decision.fragment_award,
        "cost": cost,
        "reward": reward,
    }


def get_team_state(actor: Actor) -> TeamProjection:
    with read_snapshot():
        _verify_actor(actor, "team")
        return _projection(Run.objects.filter(active=True).first(), actor.team_id)


def get_admin_status(actor: Actor) -> StartResult | None:
    with read_snapshot():
        _verify_actor(actor, "admin")
        run = Run.objects.filter(active=True).first()
        return StartResult(str(run.id), run.global_state) if run else None


def get_admin_state(actor: Actor) -> AdminProjection:
    with read_snapshot():
        _verify_actor(actor, "admin")
        run = Run.objects.filter(active=True).first()
        if run is None:
            return AdminProjection(None, "READY", None, ())
        config = load_snapshot(run)
        teams = []
        for team_id in ("a", "b"):
            row = TeamRun.objects.get(run=run, team_id=team_id)
            progress = list(PuzzleProgress.objects.filter(run=run, team_id=team_id))
            puzzles = config["teams"][team_id]["puzzles"]
            completed_numbers = tuple(
                sorted(p.number for p in progress if p.completed)
            )
            puzzle = (
                puzzles[row.current_number - 1]
                if (
                    row.current_number <= len(puzzles)
                    and row.current_number not in completed_numbers
                )
                else None
            )
            teams.append(AdminTeamProjection(
                team_id=team_id,
                activity_state=row.activity_state,
                points=row.points,
                hint_tokens=row.hint_tokens,
                current_number=row.current_number,
                current_question_id=puzzle["id"] if puzzle else None,
                completed_numbers=completed_numbers,
                hint_revealed=bool(puzzle and HintReveal.objects.filter(
                    run=run, team_id=team_id, puzzle_id=puzzle["id"]
                ).exists()),
            ))
        return AdminProjection(
            str(run.id), run.global_state, run.package_id, tuple(teams)
        )


def start_game(actor: Actor, command: StartGame) -> StartResult:
    request_id = _uuid(command.request_id)
    if not isinstance(command.package_id, str) or not command.package_id:
        raise ApplicationError("invalid_input")
    digest = _digest("start", actor, {"package_id": command.package_id})
    # Recover a committed Start even if the source package was later deleted.
    with read_snapshot():
        _verify_actor(actor, "admin")
        prior = StartReceipt.objects.filter(
            actor_id=actor.user_id, request_id=request_id
        ).first()
        if prior:
            if prior.payload_digest != digest:
                raise ApplicationError("request_conflict")
            return StartResult(**prior.result)
    with read_snapshot():
        ready_exists = Run.objects.filter(active=True, global_state="READY").exists()
    if ready_exists:
        staged = None
    else:
        try:
            staged = stage_snapshot(command.package_id)
        except InvalidPackage as exc:
            raise ApplicationError("invalid_input") from exc
    try:
        with immediate_transaction():
            _verify_actor(actor, "admin")
            prior = StartReceipt.objects.filter(
                actor_id=actor.user_id, request_id=request_id
            ).first()
            if prior:
                if prior.payload_digest != digest:
                    raise ApplicationError("request_conflict")
                return StartResult(**prior.result)
            if Run.objects.filter(active=True).exists():
                ready = Run.objects.filter(active=True, global_state="READY").first()
                if ready is None or ready.package_id != command.package_id:
                    raise ApplicationError("disallowed_state")
                ready.global_state = "ADVENT_QUIZ"
                ready.save(update_fields=["global_state"])
                TeamRun.objects.filter(run=ready).update(activity_state="PUZZLE")
                result = StartResult(str(ready.id), "ADVENT_QUIZ")
                StartReceipt.objects.create(
                    actor_id=actor.user_id, request_id=request_id,
                    payload_digest=digest, run=ready, result=asdict(result),
                )
                _event(ready, actor, request_id, "start", "started", changes={
                    "global_state": {"previous": "READY", "new": "ADVENT_QUIZ"},
                    "initial_points": load_snapshot(ready)["initial_points"],
                })
                return result
            if staged is None:
                raise ApplicationError("disallowed_state")
            run = Run.objects.create(
                global_state="ADVENT_QUIZ",
                package_id=command.package_id,
                snapshot_path=staged.path,
                snapshot_digest=staged.digest,
            )
            for team_id in ("a", "b"):
                TeamRun.objects.create(
                    run=run,
                    team_id=team_id,
                    activity_state="PUZZLE",
                    current_number=1,
                    points=staged.config["initial_points"],
                )
                for puzzle in staged.config["teams"][team_id]["puzzles"]:
                    PuzzleProgress.objects.create(
                        run=run,
                        team_id=team_id,
                        puzzle_id=puzzle["id"],
                        number=puzzle["number"],
                    )
            result = StartResult(str(run.id), "ADVENT_QUIZ")
            StartReceipt.objects.create(
                actor_id=actor.user_id,
                request_id=request_id,
                payload_digest=digest,
                run=run,
                result=asdict(result),
            )
            AuditEvent.objects.create(
                run=run,
                request_id=request_id,
                actor_id=actor.user_id,
                actor_role="admin",
                action="start",
                result="started",
                changes={
                    "global_state": {"previous": "READY", "new": "ADVENT_QUIZ"},
                    "initial_points": staged.config["initial_points"],
                },
            )
            return result
    except OperationalError as exc:
        if is_busy_error(exc):
            raise ApplicationError("temporarily_busy") from exc
        raise


def submit_answer(actor: Actor, command: SubmitAnswer) -> AnswerResult:
    request_id = _uuid(command.request_id)
    run_id = _uuid(command.run_id)
    if (
        not isinstance(command.question_id, str)
        or not command.question_id
        or not isinstance(command.answer, str)
        or not command.answer.strip()
        or len(command.answer) > 500
    ):
        raise ApplicationError("invalid_input")
    digest = _digest(
        "answer",
        actor,
        {
            "run_id": str(run_id),
            "question_id": command.question_id,
            "answer": command.answer,
        },
    )
    try:
        with immediate_transaction():
            _verify_actor(actor, "team")
            receipt = AnswerReceipt.objects.filter(
                run_id=run_id, actor_id=actor.user_id, request_id=request_id
            ).first()
            if receipt:
                if receipt.payload_digest != digest:
                    raise ApplicationError("request_conflict")
                return _restore_answer(receipt.result)
            run = Run.objects.filter(pk=run_id, active=True).first()
            if run is None:
                raise ApplicationError("stale_run")
            team, config, puzzles, puzzle, progress, current = _current_puzzle(
                run, actor.team_id, command.question_id
            )
            correct = evaluate_answer(
                puzzle["validator"]["type"],
                puzzle["validator"]["answer"],
                command.answer,
            )
            Attempt.objects.create(
                run=run,
                team_id=actor.team_id,
                actor_id=actor.user_id,
                puzzle_id=puzzle["id"],
                number=puzzle["number"],
                is_correct=correct,
            )
            if correct:
                changes = _complete_current(
                    run, actor, actor.team_id, team, puzzles, puzzle, progress,
                    current, "correct_answer"
                )
                outcome = "completed"
            else:
                changes = {}
                outcome = "incorrect"
            result = AnswerResult(outcome, _projection(run, actor.team_id))
            AnswerReceipt.objects.create(
                run=run,
                actor_id=actor.user_id,
                request_id=request_id,
                payload_digest=digest,
                result=asdict(result),
            )
            AuditEvent.objects.create(
                run=run,
                request_id=request_id,
                actor_id=actor.user_id,
                actor_role="team",
                team_id=actor.team_id,
                action="answer",
                result=outcome,
                puzzle_id=puzzle["id"],
                changes=changes,
            )
            return result
    except DomainError as exc:
        code = "stale_question" if exc.code == "prerequisite_violation" else exc.code
        raise ApplicationError(code) from exc
    except OperationalError as exc:
        if is_busy_error(exc):
            raise ApplicationError("temporarily_busy") from exc
        raise


def _perform(actor, command, action, role, payload, apply):
    """One writer transaction for a phase-2 action, receipt, and audit event."""
    request_id, run_id, digest = _command_identity(actor, command, action, payload)
    try:
        with immediate_transaction():
            _verify_actor(actor, role)
            prior = _receipt(actor, request_id, digest)
            if prior is not None:
                return prior
            run = _active_run(run_id)
            outcome, result_run, changes, team_id, puzzle_id = apply(run, request_id)
            result = _command_result(outcome, result_run)
            _save_receipt(run, actor, request_id, action, digest, result)
            _event(run, actor, request_id, action, outcome,
                   team_id=team_id, puzzle_id=puzzle_id, changes=changes)
            return result
    except DomainError as exc:
        code = "stale_question" if exc.code == "prerequisite_violation" else exc.code
        raise ApplicationError(code) from exc
    except OperationalError as exc:
        if is_busy_error(exc):
            raise ApplicationError("temporarily_busy") from exc
        raise


def pause_game(actor: Actor, command: RunCommand) -> CommandResult:
    def apply(run, _request_id):
        previous = run.global_state
        run.global_state = decide_pause(previous)
        run.save(update_fields=["global_state"])
        return (
            "paused", run,
            {"global_state": {"previous": previous, "new": run.global_state}},
            None, "",
        )
    return _perform(actor, command, "pause", "admin", {}, apply)


def resume_game(actor: Actor, command: RunCommand) -> CommandResult:
    def apply(run, _request_id):
        previous = run.global_state
        run.global_state = decide_resume(previous)
        run.save(update_fields=["global_state"])
        return (
            "resumed", run,
            {"global_state": {"previous": previous, "new": run.global_state}},
            None, "",
        )
    return _perform(actor, command, "resume", "admin", {}, apply)


def adjust_points(actor: Actor, command: AdminPoints) -> CommandResult:
    if (
        command.team_id not in ("a", "b")
        or type(command.delta) is not int
        or command.delta == 0
    ):
        raise ApplicationError("invalid_input")

    def apply(run, _request_id):
        if run.global_state not in ("ADVENT_QUIZ", "PAUSED"):
            raise ApplicationError("disallowed_state")
        team = TeamRun.objects.get(run=run, team_id=command.team_id)
        before = team.points
        team.points = decide_points(before, command.delta)
        team.save(update_fields=["points"])
        return (
            "adjusted", run,
            {"points": {
                "previous": before, "delta": command.delta, "new": team.points,
            }},
            command.team_id, "",
        )
    return _perform(actor, command, "adjust_points", "admin", {
        "team_id": command.team_id, "delta": command.delta
    }, apply)


def purchase_hint(actor: Actor, command: RunCommand) -> CommandResult:
    def apply(run, _request_id):
        team = TeamRun.objects.get(run=run, team_id=actor.team_id)
        config = load_snapshot(run)
        if "hint_cost" not in config:
            raise ApplicationError("disallowed_state")
        before = team.points
        before_tokens = team.hint_tokens
        team.points, team.hint_tokens = decide_hint_purchase(
            run.global_state, team.activity_state, team.points,
            team.hint_tokens, config["hint_cost"]
        )
        team.save(update_fields=["points", "hint_tokens"])
        return "purchased", run, {
            "points": {
                "previous": before,
                "delta": team.points - before,
                "new": team.points,
            },
            "hint_tokens": {"previous": before_tokens, "new": team.hint_tokens},
        }, actor.team_id, ""
    return _perform(actor, command, "purchase_hint", "team", {}, apply)


def _reveal(
    actor: Actor, command: AdminPuzzle | TeamPuzzle, *, admin: bool
) -> CommandResult:
    if admin and command.team_id not in ("a", "b"):
        raise ApplicationError("invalid_input")
    if not isinstance(command.question_id, str) or not command.question_id:
        raise ApplicationError("invalid_input")
    team_id = command.team_id if admin else actor.team_id
    action = "provide_hint" if admin else "use_hint"
    def apply(run, request_id):
        team, _config, _puzzles, puzzle, _progress, _current = _current_puzzle(
            run, team_id, command.question_id
        )
        if puzzle["hint"] is None:
            raise ApplicationError("disallowed_state")
        revealed = HintReveal.objects.filter(
            run=run, team_id=team_id, puzzle_id=puzzle["id"]
        ).exists()
        before = team.hint_tokens
        team.hint_tokens, newly = decide_hint_reveal(
            run.global_state, team.activity_state, team.current_number,
            puzzle["number"], team.hint_tokens, revealed, admin=admin
        )
        if not newly:
            # A fresh repeat is a no-op, without another reveal audit event.
            return "already_revealed", run, {}, team_id, puzzle["id"]
        team.save(update_fields=["hint_tokens"])
        HintReveal.objects.create(
            run=run, team_id=team_id, puzzle_id=puzzle["id"],
            source="admin" if admin else "player", actor_id=actor.user_id,
            request_id=request_id,
        )
        return "revealed", run, {
            "hint_tokens": {"previous": before, "new": team.hint_tokens},
            "hint_revealed": {"previous": False, "new": True},
        }, team_id, puzzle["id"]
    return _perform(actor, command, action, "admin" if admin else "team", {
        **({"team_id": team_id} if admin else {}), "question_id": command.question_id,
    }, apply)


def use_hint(actor: Actor, command: TeamPuzzle) -> CommandResult:
    return _reveal(actor, command, admin=False)


def provide_hint(actor: Actor, command: AdminPuzzle) -> CommandResult:
    return _reveal(actor, command, admin=True)


def _complete_action(
    actor: Actor, command: AdminPuzzle | TeamPuzzle, *, admin: bool
) -> CommandResult:
    if admin and command.team_id not in ("a", "b"):
        raise ApplicationError("invalid_input")
    if not isinstance(command.question_id, str) or not command.question_id:
        raise ApplicationError("invalid_input")
    team_id = command.team_id if admin else actor.team_id
    action = "force_complete" if admin else "skip"
    def apply(run, _request_id):
        team, config, puzzles, puzzle, progress, current = _current_puzzle(
            run, team_id, command.question_id
        )
        cost = 0
        if not admin:
            if "skip_cost" not in config:
                raise ApplicationError("disallowed_state")
            cost = config["skip_cost"]
        changes = _complete_current(
            run, actor, team_id, team, puzzles, puzzle, progress, current,
            "admin_force" if admin else "skip", cost=cost,
        )
        return "completed", run, changes, team_id, puzzle["id"]
    return _perform(actor, command, action, "admin" if admin else "team", {
        **({"team_id": team_id} if admin else {}), "question_id": command.question_id,
    }, apply)


def skip_current(actor: Actor, command: TeamPuzzle) -> CommandResult:
    return _complete_action(actor, command, admin=False)


def force_complete_current(actor: Actor, command: AdminPuzzle) -> CommandResult:
    return _complete_action(actor, command, admin=True)


def reset_game(actor: Actor, command: RunCommand) -> CommandResult:
    def apply(run, _request_id):
        config = load_snapshot(run)
        run.active = False
        run.save(update_fields=["active"])
        fresh = Run.objects.create(
            global_state="READY", package_id=run.package_id,
            snapshot_path=run.snapshot_path, snapshot_digest=run.snapshot_digest,
        )
        for team_id in ("a", "b"):
            TeamRun.objects.create(
                run=fresh, team_id=team_id, activity_state="READY",
                current_number=1, points=config["initial_points"], hint_tokens=0,
            )
            for puzzle in config["teams"][team_id]["puzzles"]:
                PuzzleProgress.objects.create(
                    run=fresh,
                    team_id=team_id,
                    puzzle_id=puzzle["id"],
                    number=puzzle["number"],
                )
        return "reset", fresh, {
            "global_state": {"previous": run.global_state, "new": "READY"},
            "new_run_id": str(fresh.id),
            "initial_points": config["initial_points"],
        }, None, ""
    return _perform(actor, command, "reset", "admin", {}, apply)
