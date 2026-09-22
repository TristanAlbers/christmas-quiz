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
    AnswerResult,
    ApplicationError,
    QuestionProjection,
    StartGame,
    StartResult,
    SubmitAnswer,
    TeamProjection,
)
from quiz.domain import (
    CompletionState,
    DomainError,
    PuzzleCompletion,
    can_submit_answer,
    complete_puzzle,
    evaluate_answer,
)
from quiz.models import (
    AccountRole,
    AnswerReceipt,
    Attempt,
    AuditEvent,
    FragmentAward,
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
    progress = list(PuzzleProgress.objects.filter(run=run, team_id=team_id))
    completed = tuple(sorted(row.number for row in progress if row.completed))
    fragments = tuple(
        FragmentAward.objects.filter(run=run, team_id=team_id)
        .order_by("awarded_at", "pk")
        .values_list("fragment", flat=True)
    )
    question = None
    if run.global_state == "ADVENT_QUIZ" and team.activity_state == "PUZZLE":
        config = load_snapshot(run)
        puzzles = config["teams"][team_id]["puzzles"]
        if team.current_number <= len(puzzles) and team.current_number not in completed:
            item = puzzles[team.current_number - 1]
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


def get_team_state(actor: Actor) -> TeamProjection:
    with read_snapshot():
        _verify_actor(actor, "team")
        return _projection(Run.objects.filter(active=True).first(), actor.team_id)


def get_admin_status(actor: Actor) -> StartResult | None:
    with read_snapshot():
        _verify_actor(actor, "admin")
        run = Run.objects.filter(active=True).first()
        return StartResult(str(run.id), run.global_state) if run else None


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
            team = TeamRun.objects.get(run=run, team_id=actor.team_id)
            if not can_submit_answer(run.global_state, team.activity_state):
                raise ApplicationError("disallowed_state")
            config = load_snapshot(run)
            puzzles = config["teams"][actor.team_id]["puzzles"]
            if team.current_number > len(puzzles):
                raise ApplicationError("disallowed_state")
            puzzle = puzzles[team.current_number - 1]
            if command.question_id != puzzle["id"]:
                raise ApplicationError("stale_question")
            progress = list(
                PuzzleProgress.objects.filter(run=run, team_id=actor.team_id)
            )
            current = next(row for row in progress if row.number == team.current_number)
            if current.completed or any(
                not row.completed
                for row in progress
                if row.number < team.current_number
            ):
                raise ApplicationError("stale_question")
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
                awarded_ids = set(
                    FragmentAward.objects.filter(run=run, team_id=actor.team_id)
                    .values_list("puzzle_id", flat=True)
                )
                state = CompletionState(
                    global_state=run.global_state,
                    team_state=team.activity_state,
                    current_number=team.current_number,
                    points=team.points,
                    completed_numbers=frozenset(
                        row.number for row in progress if row.completed
                    ),
                    rewarded_numbers=frozenset(
                        row.number for row in progress if row.reward_awarded
                    ),
                    fragment_awarded_numbers=frozenset(
                        row.number for row in progress if row.puzzle_id in awarded_ids
                    ),
                )
                decision = complete_puzzle(
                    state,
                    PuzzleCompletion(
                        number=puzzle["number"],
                        reward_points=puzzle["reward_points"],
                        fragment=puzzle["fragment"],
                        next_number=(
                            team.current_number + 1
                            if team.current_number < len(puzzles)
                            else None
                        ),
                    ),
                    "correct_answer",
                )
                prior_points = team.points
                prior_number = team.current_number
                current.completed = True
                current.completion_route = decision.route
                current.reward_awarded = True
                current.completed_at = timezone.now()
                current.save(update_fields=[
                    "completed", "completion_route", "reward_awarded", "completed_at"
                ])
                team.points = decision.state.points
                team.current_number = decision.state.current_number
                team.save(update_fields=["points", "current_number"])
                if decision.fragment_award is not None:
                    FragmentAward.objects.create(
                        run=run,
                        team_id=actor.team_id,
                        puzzle_id=puzzle["id"],
                        fragment=decision.fragment_award,
                    )
                changes = {
                    "points": {
                        "previous": prior_points,
                        "delta": decision.points_delta,
                        "new": team.points,
                    },
                    "current_number": {
                        "previous": prior_number,
                        "new": team.current_number,
                    },
                    "completed": {"previous": False, "new": True},
                    "fragment": decision.fragment_award,
                }
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
