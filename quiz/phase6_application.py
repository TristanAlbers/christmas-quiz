"""Phase-6 Challenge application overrides for the stable application facade."""

from dataclasses import asdict, replace

from django.db import OperationalError
from django.urls import reverse

from quiz import _application_core as core
from quiz.configuration import puzzle_media_descriptor
from quiz.contracts import (
    AdminChallengeProjection,
    ChallengeAnswerResult,
    ChallengeQuestionProjection,
    PublicChallengeProjection,
    PuzzleMediaProjection,
    RunCommand,
    SubmitChallengeAnswer,
    TeamChallengeProjection,
)
from quiz.domain.phase6 import challenge_grace_remaining_ms
from quiz.models import Challenge, ChallengeAttempt, CommandReceipt, Run, TeamRun
from quiz.persistence import immediate_transaction, is_busy_error, read_snapshot


# The legacy core predates the amended two-puzzle Phase-6 contract and typed
# normal-puzzle media. Keep it unchanged by supplying a runtime-only compatible
# view of the immutable snapshot. The persisted snapshot retains the authoritative
# typed media objects and `challenge_puzzles` map.
_CORE_LOAD_SNAPSHOT = core.load_snapshot
_AUTHORITATIVE_CONFIG_ATTR = "_phase6_authoritative_snapshot_config"


def _load_snapshot_compatible(run_or_path):
    config = _CORE_LOAD_SNAPSHOT(run_or_path)
    if hasattr(run_or_path, "snapshot_path"):
        setattr(run_or_path, _AUTHORITATIVE_CONFIG_ATTR, config)
    teams = config.get("teams")
    typed_media = bool(
        isinstance(teams, dict)
        and any(
            isinstance(item, dict)
            for team in teams.values()
            for puzzle in team.get("puzzles", ())
            for item in puzzle.get("media", ())
        )
    )
    needs_challenge_alias = (
        config.get("schema_version") == 6 and "challenge_puzzle" not in config
    )
    if not typed_media and not needs_challenge_alias:
        return config

    compatible = dict(config)
    if typed_media:
        compatible_teams = {}
        for team_id, team in config["teams"].items():
            compatible_team = dict(team)
            compatible_puzzles = []
            for puzzle in team["puzzles"]:
                compatible_puzzle = dict(puzzle)
                compatible_puzzle["media"] = [
                    puzzle_media_descriptor(item)["path"]
                    for item in puzzle["media"]
                ]
                compatible_puzzles.append(compatible_puzzle)
            compatible_team["puzzles"] = compatible_puzzles
            compatible_teams[team_id] = compatible_team
        compatible["teams"] = compatible_teams
    if needs_challenge_alias:
        compatible["challenge_puzzle"] = config["challenge_puzzles"]["a"]
    return compatible


core.load_snapshot = _load_snapshot_compatible


def _challenge_puzzle(config, challenge):
    return config["challenge_puzzles"][challenge.initiator_team_id]


def _challenge_phase(challenge, gameplay_ms):
    if challenge.status == "resolved":
        return "resolved", None
    remaining = challenge_grace_remaining_ms(
        challenge.started_gameplay_ms, gameplay_ms
    )
    return ("starting" if remaining > 0 else "active"), remaining


def _latest_challenge(run):
    return Challenge.objects.filter(run=run).order_by("-started_at", "-pk").first()


def _challenge_number(run):
    return Challenge.objects.filter(run=run).count()


def _team_challenge_projection(run, config, team_id, gameplay_ms):
    challenge = _latest_challenge(run)
    if challenge is None:
        return None
    role = "initiator" if challenge.initiator_team_id == team_id else "challenged"
    phase, remaining = _challenge_phase(challenge, gameplay_ms)
    question = None
    if phase == "active":
        item = _challenge_puzzle(config, challenge)
        question = ChallengeQuestionProjection(
            id=item["id"],
            title=item["title"],
            body=item["body"],
            media_urls=tuple(
                reverse(
                    "challenge_media",
                    kwargs={
                        "run_id": run.id,
                        "challenge_id": challenge.id,
                        "asset_path": path,
                    },
                )
                for path in item["media"]
            ),
        )
    return TeamChallengeProjection(
        id=str(challenge.id),
        status=challenge.status,
        role=role,
        phase=phase,
        grace_remaining_ms=remaining,
        question=question,
        winner_team_id=challenge.winner_team_id,
        freeze_applied=challenge.freeze_applied,
    )


def _admin_challenge_projection(run, gameplay_ms):
    challenge = _latest_challenge(run)
    if challenge is None:
        return None
    phase, remaining = _challenge_phase(challenge, gameplay_ms)
    return AdminChallengeProjection(
        id=str(challenge.id),
        status=challenge.status,
        initiator_team_id=challenge.initiator_team_id,
        challenged_team_id=challenge.challenged_team_id,
        question_id=challenge.question_id,
        paid_cost=0,
        phase=phase,
        grace_remaining_ms=remaining,
        challenge_number=_challenge_number(run),
        winner_team_id=challenge.winner_team_id,
        freeze_applied=challenge.freeze_applied,
    )


def _public_challenge_projection(run, config, gameplay_ms):
    challenge = Challenge.objects.filter(run=run, status="active").first()
    if challenge is None:
        return None
    phase, remaining = _challenge_phase(challenge, gameplay_ms)
    title = None
    body = None
    if phase == "active":
        puzzle = _challenge_puzzle(config, challenge)
        title = puzzle["title"]
        body = puzzle["body"]
    return PublicChallengeProjection(
        id=str(challenge.id),
        phase=phase,
        challenge_number=_challenge_number(run),
        initiator_team_id=challenge.initiator_team_id,
        challenged_team_id=challenge.challenged_team_id,
        grace_remaining_ms=remaining,
        title=title,
        body=body,
    )


def _normal_question_projection(run, config, team_id, question):
    if question is None:
        return None
    try:
        item = config["teams"][team_id]["puzzles"][question.number - 1]
    except (KeyError, IndexError, TypeError):
        return question
    media = tuple(
        PuzzleMediaProjection(
            type=descriptor["type"],
            url=reverse(
                "private_media",
                kwargs={
                    "run_id": run.id,
                    "team_id": team_id,
                    "asset_path": descriptor["path"],
                },
            ),
            alt=descriptor["alt"],
        )
        for descriptor in (puzzle_media_descriptor(value) for value in item["media"])
    )
    return replace(
        question,
        media_urls=tuple(entry.url for entry in media),
        media=media,
    )


def _projection(run, team_id, now):
    base = core._projection(run, team_id, now)
    if run is None:
        return base
    authoritative_config = getattr(run, _AUTHORITATIVE_CONFIG_ATTR, None)
    if authoritative_config is None:
        authoritative_config = _CORE_LOAD_SNAPSHOT(run)
    base = replace(
        base,
        question=_normal_question_projection(
            run, authoritative_config, team_id, base.question
        ),
    )
    if authoritative_config.get("schema_version") != 6:
        return base
    return replace(
        base,
        challenge_cost=0,
        challenge=_team_challenge_projection(
            run, authoritative_config, team_id, base.gameplay_elapsed_ms
        ),
    )


def get_team_state(actor, *, now=None):
    now = core._server_now(now)
    with read_snapshot():
        core._verify_actor(actor, "team")
        run = Run.objects.filter(active=True).first()
        return _projection(run, actor.team_id, now)


def get_admin_state(actor, *, now=None):
    now = core._server_now(now)
    state = core.get_admin_state(actor, now=now)
    if state.run_id is None:
        return state
    with read_snapshot():
        run = Run.objects.filter(pk=state.run_id, active=True).first()
        if run is None:
            return state
        config = _load_snapshot_compatible(run)
        if config.get("schema_version") != 6:
            return state
        gameplay_ms = core._gameplay_ms(run, now)
        return replace(
            state,
            gameplay_elapsed_ms=gameplay_ms,
            challenge=_admin_challenge_projection(run, gameplay_ms),
        )


def get_public_state(*, now=None):
    now = core._server_now(now)
    state = core.get_public_state(now=now)
    with read_snapshot():
        run = Run.objects.filter(active=True).first()
        if run is None:
            return state
        config = _load_snapshot_compatible(run)
        if config.get("schema_version") != 6:
            return state
        gameplay_ms = state.gameplay_elapsed_ms
        return replace(
            state,
            challenge=_public_challenge_projection(run, config, gameplay_ms),
        )


def initiate_challenge(actor, command: RunCommand, *, now=None):
    """Consume the caller's free one-use Challenge and start gathering."""

    def apply(run, _request_id, gameplay_ms):
        config = _load_snapshot_compatible(run)
        if config.get("schema_version") != 6:
            raise core.ApplicationError("disallowed_state")
        if Challenge.objects.filter(
            run=run, initiator_team_id=actor.team_id
        ).exists():
            raise core.ApplicationError("challenge_spent")
        initiator = TeamRun.objects.get(run=run, team_id=actor.team_id)
        challenged_id = "b" if actor.team_id == "a" else "a"
        challenged = TeamRun.objects.get(run=run, team_id=challenged_id)
        decision = core.decide_challenge_start(
            global_state=run.global_state,
            challenge_active=Challenge.objects.filter(
                run=run, status="active"
            ).exists(),
            initiator=core._challenge_team_state(initiator),
            challenged=core._challenge_team_state(challenged),
            current_gameplay_ms=gameplay_ms,
            cost=0,
        )
        core._persist_challenge_team_state(initiator, decision.initiator)
        core._persist_challenge_team_state(challenged, decision.challenged)
        puzzle = config["challenge_puzzles"][actor.team_id]
        challenge = Challenge.objects.create(
            run=run,
            initiator_team_id=actor.team_id,
            challenged_team_id=challenged_id,
            question_id=puzzle["id"],
            paid_cost=0,
            started_gameplay_ms=gameplay_ms,
        )
        return (
            "challenge_started",
            run,
            {
                "challenge_id": str(challenge.id),
                "paid_cost": 0,
                "points": {
                    "previous": initiator.points,
                    "delta": 0,
                    "new": initiator.points,
                },
                "opportunity_consumed": decision.opportunity_consumed,
                "started_gameplay_ms": gameplay_ms,
                "activity_state": {"previous": "PUZZLE", "new": "CHALLENGE"},
            },
            actor.team_id,
            challenge.question_id,
        )

    return core._perform(
        actor,
        command,
        "initiate_challenge",
        "team",
        {},
        apply,
        now=now,
    )


def submit_challenge_answer(
    actor, command: SubmitChallengeAnswer, *, now=None
) -> ChallengeAnswerResult:
    now = core._server_now(now)
    request_id = core._uuid(command.request_id)
    run_id = core._uuid(command.run_id)
    challenge_id = core._uuid(command.challenge_id)
    if (
        not isinstance(command.question_id, str)
        or not command.question_id
        or not isinstance(command.answer, str)
        or not command.answer.strip()
        or len(command.answer) > 500
    ):
        raise core.ApplicationError("invalid_input")
    digest = core._digest(
        "submit_challenge_answer",
        actor,
        {
            "run_id": str(run_id),
            "challenge_id": str(challenge_id),
            "question_id": command.question_id,
            "answer": command.answer,
        },
    )
    try:
        with immediate_transaction():
            core._verify_actor(actor, "team")
            prior = CommandReceipt.objects.filter(
                actor_id=actor.user_id, request_id=request_id
            ).first()
            if prior is not None:
                if prior.payload_digest != digest:
                    raise core.ApplicationError("request_conflict")
                restored = core._restore_challenge_answer(prior.result)
                active = Run.objects.filter(pk=run_id, active=True).first()
                if active is not None:
                    return ChallengeAnswerResult(
                        restored.outcome,
                        _projection(active, actor.team_id, now),
                    )
                return restored
            run = Run.objects.filter(pk=run_id, active=True).first()
            if run is None:
                raise core.ApplicationError("stale_run")
            config = _load_snapshot_compatible(run)
            if config.get("schema_version") != 6:
                raise core.ApplicationError("disallowed_state")
            if core._persist_music_timing(run, config, now) == "completed":
                core._event(
                    run,
                    actor,
                    request_id,
                    "music_completed",
                    "completed",
                    changes={
                        "global_state": {
                            "previous": "MUSIC_QUIZ",
                            "new": "ADVENT_QUIZ",
                        }
                    },
                )
            if run.global_state != "ADVENT_QUIZ":
                raise core.ApplicationError("disallowed_state")
            gameplay_ms = core._gameplay_ms(run, now)
            core._reconcile_expired_freezes(run, gameplay_ms)
            challenge = Challenge.objects.filter(
                pk=challenge_id, run=run, status="active"
            ).first()
            if challenge is None:
                raise core.ApplicationError("stale_challenge")
            if challenge_grace_remaining_ms(
                challenge.started_gameplay_ms, gameplay_ms
            ) > 0:
                raise core.ApplicationError("challenge_starting")
            initiator = TeamRun.objects.get(
                run=run, team_id=challenge.initiator_team_id
            )
            challenged = TeamRun.objects.get(
                run=run, team_id=challenge.challenged_team_id
            )
            puzzle = _challenge_puzzle(config, challenge)
            decision = core.resolve_challenge_answer(
                global_state=run.global_state,
                challenge_status=challenge.status,
                current_challenge_id=str(challenge.id),
                submitted_challenge_id=str(challenge_id),
                current_question_id=challenge.question_id,
                submitted_question_id=command.question_id,
                validator_type=puzzle["validator"]["type"],
                expected_answer=puzzle["validator"]["answer"],
                submitted_answer=command.answer,
                answering_team_id=actor.team_id,
                initiator=core._challenge_team_state(initiator),
                challenged=core._challenge_team_state(challenged),
                current_gameplay_ms=gameplay_ms,
            )
            attempt = ChallengeAttempt.objects.create(
                challenge=challenge,
                actor_id=actor.user_id,
                team_id=actor.team_id,
                request_id=request_id,
                question_id=challenge.question_id,
                is_correct=decision.outcome == "won",
            )
            changes = {}
            if decision.outcome == "won":
                core._persist_challenge_team_state(initiator, decision.initiator)
                core._persist_challenge_team_state(challenged, decision.challenged)
                challenge.status = "resolved"
                challenge.winner_team_id = decision.winner_team_id
                challenge.freeze_applied = decision.freeze_applied
                challenge.winning_attempt = attempt
                challenge.resolved_at = now
                challenge.save(
                    update_fields=[
                        "status",
                        "winner_team_id",
                        "freeze_applied",
                        "winning_attempt",
                        "resolved_at",
                    ]
                )
                changes = {
                    "challenge_id": str(challenge.id),
                    "winner_team_id": decision.winner_team_id,
                    "freeze_applied": decision.freeze_applied,
                    "points_delta": decision.points_delta,
                    "advent_progressed": decision.advent_progressed,
                    "fragment_award": decision.fragment_award,
                    "music_triggered": decision.music_triggered,
                }
            result = ChallengeAnswerResult(
                decision.outcome,
                _projection(run, actor.team_id, now),
            )
            CommandReceipt.objects.create(
                run=run,
                actor_id=actor.user_id,
                request_id=request_id,
                action="submit_challenge_answer",
                payload_digest=digest,
                result=asdict(result),
            )
            core._event(
                run,
                actor,
                request_id,
                "submit_challenge_answer",
                decision.outcome,
                team_id=actor.team_id,
                puzzle_id=challenge.question_id,
                changes=changes,
            )
            return result
    except core.DomainError as exc:
        raise core.ApplicationError(exc.code) from exc
    except OperationalError as exc:
        if is_busy_error(exc):
            raise core.ApplicationError("temporarily_busy") from exc
        raise
