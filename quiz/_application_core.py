"""Authoritative synchronous use cases for the first persisted game slice."""

import hashlib
import json
import uuid
from dataclasses import asdict

from django.contrib.auth import get_user_model
from django.db import OperationalError
from django.urls import reverse
from django.utils import timezone

from quiz.configuration import (
    InvalidPackage,
    discover_packages,
    load_snapshot,
    stage_snapshot,
)
from quiz.contracts import (
    Actor,
    AdminChallengeProjection,
    AdminPoints,
    AdminProjection,
    AdminPuzzle,
    AdminTeam,
    AdminTeamProjection,
    AdventDoorProjection,
    AdventProgressProjection,
    AnswerResult,
    ApplicationError,
    ChallengeAnswerResult,
    ChallengeQuestionProjection,
    CommandResult,
    MusicAnswerResult,
    MusicProjection,
    MusicScoreProjection,
    PackageProjection,
    PublicProjection,
    PublicTeamProgressProjection,
    QuestionProjection,
    RunCommand,
    StartGame,
    StartResult,
    SubmitAnswer,
    SubmitChallengeAnswer,
    SubmitMusicAnswer,
    TeamChallengeProjection,
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
    pay_skip,
)
from quiz.domain.phase2 import (
    purchase_hint as decide_hint_purchase,
)
from quiz.domain.phase2 import (
    reveal_hint as decide_hint_reveal,
)
from quiz.domain.phase3 import (
    EffectTeamState,
    GameplayClock,
    apply_direct_freeze,
    effective_gameplay_ms,
    freeze_remaining_ms,
    pause_gameplay_clock,
    reconcile_freeze,
    remove_freeze,
    resolve_freeze_attack,
    resume_gameplay_clock,
)
from quiz.domain.phase3 import (
    purchase_uno_reverse as decide_reverse_purchase,
)
from quiz.domain.phase4 import (
    MUSIC_QUESTION_TOTAL,
    MusicClock,
    UnderlyingTeamState,
    begin_music_interruption,
    effective_music_ms,
    music_phase_elapsed_ms,
    pause_music_interruption,
    reconcile_music_timing,
    resolve_music_answer,
    resume_music_interruption,
)
from quiz.domain.phase4 import (
    MusicScore as DomainMusicScore,
)
from quiz.domain.phase6 import (
    ChallengeTeamState,
    challenge_eligibility,
    resolve_challenge_answer,
)
from quiz.domain.phase6 import (
    initiate_challenge as decide_challenge_start,
)
from quiz.models import (
    AccountRole,
    AnswerReceipt,
    Attempt,
    AuditEvent,
    Challenge,
    ChallengeAttempt,
    CommandReceipt,
    FirstFinisher,
    FragmentAward,
    HintReveal,
    MusicAttempt,
    MusicQuestionResult,
    MusicQuiz,
    MusicScore,
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


def _server_now(now):
    value = timezone.now() if now is None else now
    # Reuse the pure clock validation so every injected clock follows one rule.
    try:
        effective_gameplay_ms(0, None, value)
    except DomainError as exc:
        raise ApplicationError(exc.code) from exc
    return value


def _gameplay_ms(run: Run, now) -> int:
    return effective_gameplay_ms(run.gameplay_elapsed_ms, run.advent_clock_anchor, now)


def _underlying_teams(run: Run) -> tuple[UnderlyingTeamState, ...]:
    return tuple(
        UnderlyingTeamState(
            row.team_id,
            row.activity_state,
            row.freeze_started_gameplay_ms,
        )
        for row in TeamRun.objects.filter(run=run).order_by("team_id")
    )


def _music_timing(run: Run, config: dict, now):
    music = MusicQuiz.objects.filter(run=run).first()
    if music is None or run.global_state == "FINISHED":
        return None, None
    decision = reconcile_music_timing(
        global_state=run.global_state,
        pause_resume_target=run.pause_resume_target,
        phase=music.phase,
        music_clock=MusicClock(
            music.music_elapsed_ms,
            music.music_clock_anchor,
        ),
        advent_clock=GameplayClock(
            run.gameplay_elapsed_ms,
            run.advent_clock_anchor,
        ),
        final_results_started_ms=music.final_results_started_ms,
        final_results_duration_ms=config["music_score_display_duration_ms"],
        now=now,
    )
    return music, decision


def _effective_run_state(run: Run, config: dict, now):
    music, timing = _music_timing(run, config, now)
    if timing is None:
        return run.global_state, _gameplay_ms(run, now), music, timing
    gameplay_ms = effective_gameplay_ms(
        timing.advent_clock.accumulated_ms,
        timing.advent_clock.anchor,
        now,
    )
    return timing.global_state, gameplay_ms, music, timing


def _persist_music_timing(run: Run, config: dict, now) -> bool:
    """Persist a logically expired final display inside an existing writer."""
    music, timing = _music_timing(run, config, now)
    if music is None or timing.phase != "completed" or music.phase == "completed":
        return False
    run.global_state = timing.global_state
    run.pause_resume_target = None
    run.gameplay_elapsed_ms = timing.advent_clock.accumulated_ms
    run.advent_clock_anchor = timing.advent_clock.anchor
    run.save(
        update_fields=[
            "global_state",
            "pause_resume_target",
            "gameplay_elapsed_ms",
            "advent_clock_anchor",
        ]
    )
    music.phase = timing.phase
    music.music_elapsed_ms = timing.music_clock.accumulated_ms
    music.music_clock_anchor = timing.music_clock.anchor
    music.save(update_fields=["phase", "music_elapsed_ms", "music_clock_anchor"])
    return True


def _music_projection(run, config, music, timing, now, *, consumer):
    if music is None or timing is None or timing.phase == "completed":
        return None
    scores = tuple(
        MusicScoreProjection(row.team_id, row.score)
        for row in MusicScore.objects.filter(run=run).order_by("team_id")
    )
    question_id = None
    question_number = music.current_question_number
    title = None
    body = None
    elapsed_ms = None
    audio_url = None
    if timing.phase == "question" and question_number is not None:
        question = config["music_questions"][question_number - 1]
        if consumer in {"team", "admin"}:
            question_id = question["id"]
        title = question["title"]
        body = question["body"]
        phase_started_ms = music.current_question_started_ms
        elapsed_ms = music_phase_elapsed_ms(
            effective_music_ms(
                timing.music_clock.accumulated_ms,
                timing.music_clock.anchor,
                now,
            ),
            phase_started_ms,
        )
        if (
            consumer in {"public", "admin"}
            and run.global_state == "MUSIC_QUIZ"
            and question.get("audio") is not None
        ):
            audio_url = reverse("current_music_audio", kwargs={"run_id": run.id})
    return MusicProjection(
        phase=timing.phase,
        question_id=question_id,
        question_number=question_number,
        question_total=MUSIC_QUESTION_TOTAL,
        title=title,
        body=body,
        scores=scores,
        question_elapsed_ms=elapsed_ms,
        final_results_remaining_ms=timing.final_results_remaining_ms,
        previous_winner_team_id=music.previous_winner_team,
        audio_url=audio_url,
    )


def _effect_state(team: TeamRun) -> EffectTeamState:
    return EffectTeamState(
        activity_state=team.activity_state,
        points=team.points,
        freeze_started_ms=team.freeze_started_gameplay_ms,
        uno_reverse_active=team.reverse_active,
    )


def _challenge_team_state(team: TeamRun) -> ChallengeTeamState:
    return ChallengeTeamState(
        team_id=team.team_id,
        activity_state=team.activity_state,
        points=team.points,
        opportunity_available=team.challenge_available,
        freeze_started_ms=team.freeze_started_gameplay_ms,
        uno_reverse_active=team.reverse_active,
    )


def _persist_challenge_team_state(team: TeamRun, state: ChallengeTeamState) -> None:
    team.activity_state = state.activity_state
    team.points = state.points
    team.challenge_available = state.opportunity_available
    team.freeze_started_gameplay_ms = state.freeze_started_ms
    team.reverse_active = state.uno_reverse_active
    team.save(
        update_fields=[
            "activity_state",
            "points",
            "challenge_available",
            "freeze_started_gameplay_ms",
            "reverse_active",
        ]
    )


def _latest_challenge(run: Run) -> Challenge | None:
    return Challenge.objects.filter(run=run).order_by("-started_at", "-pk").first()


def _team_challenge_projection(run, config, team_id):
    challenge = _latest_challenge(run)
    if challenge is None:
        return None
    role = "initiator" if challenge.initiator_team_id == team_id else "challenged"
    question = None
    if challenge.status == "active":
        item = config["challenge_puzzle"]
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
        question=question,
        winner_team_id=challenge.winner_team_id,
        freeze_applied=challenge.freeze_applied,
    )


def _admin_challenge_projection(run):
    challenge = _latest_challenge(run)
    if challenge is None:
        return None
    return AdminChallengeProjection(
        id=str(challenge.id),
        status=challenge.status,
        initiator_team_id=challenge.initiator_team_id,
        challenged_team_id=challenge.challenged_team_id,
        question_id=challenge.question_id,
        paid_cost=challenge.paid_cost,
        winner_team_id=challenge.winner_team_id,
        freeze_applied=challenge.freeze_applied,
    )


def _persist_effect_state(team: TeamRun, state: EffectTeamState) -> None:
    team.activity_state = state.activity_state
    team.points = state.points
    team.freeze_started_gameplay_ms = state.freeze_started_ms
    team.reverse_active = state.uno_reverse_active
    team.save(
        update_fields=[
            "activity_state",
            "points",
            "freeze_started_gameplay_ms",
            "reverse_active",
        ]
    )


def _reconcile_expired_freezes(run: Run, gameplay_ms: int) -> None:
    """Persist logical expiries only inside an existing writer transaction."""
    for team in TeamRun.objects.filter(run=run, activity_state="FREEZE"):
        state = reconcile_freeze(
            team.activity_state, team.freeze_started_gameplay_ms, gameplay_ms
        )
        if state.activity_state != team.activity_state:
            team.activity_state = state.activity_state
            team.freeze_started_gameplay_ms = state.freeze_started_ms
            team.save(update_fields=["activity_state", "freeze_started_gameplay_ms"])


def _advent_progress(team: TeamRun, completed: tuple[int, ...]):
    completed_set = set(completed)
    is_finished = team.activity_state == "FINISHED"
    current_number = (
        None
        if is_finished or team.current_number in completed_set
        else team.current_number
    )
    doors = tuple(
        AdventDoorProjection(
            number,
            (
                "completed"
                if number in completed_set
                else "current"
                if number == current_number
                else "future"
            ),
        )
        for number in range(1, 26)
    )
    return AdventProgressProjection(
        doors=doors,
        completed_count=len(completed_set),
        current_number=current_number,
        is_finished=is_finished,
    )


def _first_finisher_team_id(run: Run) -> str | None:
    claim = FirstFinisher.objects.filter(run=run).only("team_id").first()
    return claim.team_id if claim is not None else None


def _projection(run: Run | None, team_id: str, now=None) -> TeamProjection:
    if run is None:
        return TeamProjection(None, "READY", "READY", 0, None, (), (), None)
    now = _server_now(now)
    team = TeamRun.objects.get(run=run, team_id=team_id)
    config = load_snapshot(run)
    global_state, gameplay_ms, music, timing = _effective_run_state(run, config, now)
    effective = reconcile_freeze(
        team.activity_state, team.freeze_started_gameplay_ms, gameplay_ms
    )
    challenge_supported = config.get("schema_version") == 6
    challenge_available = challenge_supported and team.challenge_available
    challenge_cost = config.get("challenge_cost")
    can_initiate_challenge = False
    challenge_ineligible_reason = None
    challenge_projection = None
    if challenge_supported:
        opponent = TeamRun.objects.get(
            run=run, team_id="b" if team_id == "a" else "a"
        )
        eligibility = challenge_eligibility(
            global_state=global_state,
            challenge_active=Challenge.objects.filter(
                run=run, status="active"
            ).exists(),
            initiator=_challenge_team_state(team),
            challenged=_challenge_team_state(opponent),
            current_gameplay_ms=gameplay_ms,
            cost=challenge_cost,
        )
        can_initiate_challenge = eligibility.can_initiate
        challenge_ineligible_reason = eligibility.reason
        challenge_projection = _team_challenge_projection(run, config, team_id)
    remaining = (
        freeze_remaining_ms(effective.freeze_started_ms, gameplay_ms)
        if effective.activity_state == "FREEZE"
        else None
    )
    progress = list(PuzzleProgress.objects.filter(run=run, team_id=team_id))
    completed = tuple(sorted(row.number for row in progress if row.completed))
    fragments = tuple(
        FragmentAward.objects.filter(run=run, team_id=team_id)
        .order_by("awarded_at", "pk")
        .values_list("fragment", flat=True)
    )
    question = None
    if global_state == "ADVENT_QUIZ" and effective.activity_state == "PUZZLE":
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
        global_state=global_state,
        team_state=effective.activity_state,
        points=team.points,
        current_number=team.current_number,
        completed_numbers=completed,
        fragments=fragments,
        question=question,
        hint_tokens=team.hint_tokens,
        hint_cost=config.get("hint_cost"),
        skip_cost=config.get("skip_cost"),
        freeze_cost=config.get("freeze_cost"),
        uno_reverse_cost=config.get("uno_reverse_cost"),
        uno_reverse_active=team.reverse_active,
        freeze_remaining_ms=remaining,
        music=_music_projection(run, config, music, timing, now, consumer="team"),
        advent_progress=_advent_progress(team, completed),
        first_finisher_team_id=_first_finisher_team_id(run),
        gameplay_elapsed_ms=gameplay_ms,
        challenge_available=challenge_available,
        challenge_cost=challenge_cost,
        can_initiate_challenge=can_initiate_challenge,
        challenge_ineligible_reason=challenge_ineligible_reason,
        challenge=challenge_projection,
    )


def _restore_team_projection(value: dict) -> TeamProjection:
    data = value.copy()
    data["completed_numbers"] = tuple(data["completed_numbers"])
    data["fragments"] = tuple(data["fragments"])
    if data["question"] is not None:
        question = data["question"].copy()
        question["media_urls"] = tuple(question["media_urls"])
        data["question"] = QuestionProjection(**question)
    if data.get("music") is not None:
        music = data["music"].copy()
        music["scores"] = tuple(
            MusicScoreProjection(**score) for score in music["scores"]
        )
        data["music"] = MusicProjection(**music)
    if data.get("advent_progress") is not None:
        advent = data["advent_progress"].copy()
        advent["doors"] = tuple(
            AdventDoorProjection(**door) for door in advent["doors"]
        )
        data["advent_progress"] = AdventProgressProjection(**advent)
    if data.get("challenge") is not None:
        challenge = data["challenge"].copy()
        if challenge.get("question") is not None:
            question = challenge["question"].copy()
            question["media_urls"] = tuple(question["media_urls"])
            challenge["question"] = ChallengeQuestionProjection(**question)
        data["challenge"] = TeamChallengeProjection(**challenge)
    return TeamProjection(**data)


def _restore_answer(value: dict) -> AnswerResult:
    return AnswerResult(value["outcome"], _restore_team_projection(value["state"]))


def _restore_music_answer(value: dict) -> MusicAnswerResult:
    return MusicAnswerResult(value["outcome"], _restore_team_projection(value["state"]))


def _restore_challenge_answer(value: dict) -> ChallengeAnswerResult:
    return ChallengeAnswerResult(
        value["outcome"], _restore_team_projection(value["state"])
    )


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


def _start_music_if_needed(run, actor, request_id, config, now) -> bool:
    if config.get("schema_version") not in (4, 5, 6):
        raise ApplicationError("disallowed_state")
    decision = begin_music_interruption(
        global_state=run.global_state,
        already_triggered=MusicQuiz.objects.filter(run=run).exists(),
        advent_clock=GameplayClock(
            run.gameplay_elapsed_ms,
            run.advent_clock_anchor,
        ),
        underlying_teams=_underlying_teams(run),
        now=now,
    )
    if not decision.triggered:
        return False
    run.global_state = decision.global_state
    run.gameplay_elapsed_ms = decision.advent_clock.accumulated_ms
    run.advent_clock_anchor = decision.advent_clock.anchor
    run.pause_resume_target = decision.pause_resume_target
    run.save(
        update_fields=[
            "global_state",
            "gameplay_elapsed_ms",
            "advent_clock_anchor",
            "pause_resume_target",
        ]
    )
    MusicQuiz.objects.create(
        run=run,
        phase="question",
        current_question_number=1,
        current_question_started_ms=0,
        music_elapsed_ms=decision.music_clock.accumulated_ms,
        music_clock_anchor=decision.music_clock.anchor,
    )
    # Save individually: persistence validation intentionally relies on normal
    # model creation rather than bypassing it with bulk_create.
    MusicScore.objects.create(run=run, team_id="a")
    MusicScore.objects.create(run=run, team_id="b")
    _event(
        run,
        actor,
        request_id,
        "music_started",
        "started",
        changes={
            "global_state": {
                "previous": "ADVENT_QUIZ",
                "new": "MUSIC_QUIZ",
            },
            "trigger_puzzle": 13,
        },
    )
    return True


def _complete_current(
    run,
    actor,
    request_id,
    team_id,
    team,
    config,
    puzzles,
    puzzle,
    progress,
    current,
    route,
    *,
    cost=0,
    now,
):
    if puzzle["number"] == 13 and config.get("schema_version") not in (4, 5, 6):
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
    other_team_finished = (
        TeamRun.objects.filter(
            run=run,
            activity_state="FINISHED",
        )
        .exclude(team_id=team_id)
        .exists()
    )
    decision = (
        pay_skip(
            state,
            completion,
            cost,
            other_team_finished=other_team_finished,
        )
        if route == "skip"
        else complete_puzzle(
            state,
            completion,
            route,
            other_team_finished=other_team_finished,
        )
    )
    prior_points = team.points
    prior_number = team.current_number
    reward = 0 if current.reward_awarded else puzzle["reward_points"]
    current.completed = True
    current.completion_route = decision.route
    current.reward_awarded = True
    current.completed_at = now
    current.save(
        update_fields=[
            "completed",
            "completion_route",
            "reward_awarded",
            "completed_at",
        ]
    )
    team.points = decision.state.points
    team.current_number = decision.state.current_number
    team.activity_state = decision.state.team_state
    team.save(update_fields=["points", "current_number", "activity_state"])
    if decision.fragment_award is not None:
        FragmentAward.objects.create(
            run=run,
            team_id=team_id,
            puzzle_id=puzzle["id"],
            fragment=decision.fragment_award,
        )
    music_triggered = (
        _start_music_if_needed(run, actor, request_id, config, now)
        if puzzle["number"] == 13
        else False
    )
    if decision.claim_first_finisher:
        FirstFinisher.objects.create(run=run, team_id=team_id)
    if decision.game_finished:
        run.global_state = "FINISHED"
        run.gameplay_elapsed_ms = _gameplay_ms(run, now)
        run.advent_clock_anchor = None
        run.pause_resume_target = None
        run.save(
            update_fields=[
                "global_state",
                "gameplay_elapsed_ms",
                "advent_clock_anchor",
                "pause_resume_target",
            ]
        )
    if decision.team_finished:
        _event(
            run,
            actor,
            request_id,
            "team_finished",
            "finished",
            team_id=team_id,
            puzzle_id=puzzle["id"],
        )
    if decision.claim_first_finisher:
        _event(
            run,
            actor,
            request_id,
            "first_finisher",
            "claimed",
            team_id=team_id,
            puzzle_id=puzzle["id"],
        )
    if decision.game_finished:
        _event(
            run,
            actor,
            request_id,
            "game_finished",
            "finished",
            team_id=team_id,
            puzzle_id=puzzle["id"],
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
        "music_triggered": music_triggered,
        "team_finished": decision.team_finished,
        "first_finisher": decision.claim_first_finisher,
        "game_finished": decision.game_finished,
    }


def get_team_state(actor: Actor, *, now=None) -> TeamProjection:
    now = _server_now(now)
    with read_snapshot():
        _verify_actor(actor, "team")
        return _projection(Run.objects.filter(active=True).first(), actor.team_id, now)


def get_admin_status(actor: Actor) -> StartResult | None:
    with read_snapshot():
        _verify_actor(actor, "admin")
        run = Run.objects.filter(active=True).first()
        return StartResult(str(run.id), run.global_state) if run else None


def get_admin_state(actor: Actor, *, now=None) -> AdminProjection:
    now = _server_now(now)
    with read_snapshot():
        _verify_actor(actor, "admin")
        run = Run.objects.filter(active=True).first()
        if run is not None:
            config = load_snapshot(run)
            global_state, gameplay_ms, music, timing = _effective_run_state(
                run, config, now
            )
            teams = []
            for team_id in ("a", "b"):
                row = TeamRun.objects.get(run=run, team_id=team_id)
                effective = reconcile_freeze(
                    row.activity_state, row.freeze_started_gameplay_ms, gameplay_ms
                )
                remaining = (
                    freeze_remaining_ms(effective.freeze_started_ms, gameplay_ms)
                    if effective.activity_state == "FREEZE"
                    else None
                )
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
                teams.append(
                    AdminTeamProjection(
                        team_id=team_id,
                        activity_state=effective.activity_state,
                        points=row.points,
                        hint_tokens=row.hint_tokens,
                        current_number=row.current_number,
                        current_question_id=puzzle["id"] if puzzle else None,
                        completed_numbers=completed_numbers,
                        hint_revealed=bool(
                            puzzle
                            and HintReveal.objects.filter(
                                run=run, team_id=team_id, puzzle_id=puzzle["id"]
                            ).exists()
                        ),
                        uno_reverse_active=row.reverse_active,
                        freeze_remaining_ms=remaining,
                        advent_progress=_advent_progress(row, completed_numbers),
                        challenge_available=(
                            config.get("schema_version") == 6
                            and row.challenge_available
                        ),
                    )
                )
            return AdminProjection(
                str(run.id),
                global_state,
                run.package_id,
                tuple(teams),
                music=_music_projection(
                    run, config, music, timing, now, consumer="admin"
                ),
                first_finisher_team_id=_first_finisher_team_id(run),
                gameplay_elapsed_ms=gameplay_ms,
                challenge=(
                    _admin_challenge_projection(run)
                    if config.get("schema_version") == 6
                    else None
                ),
            )

    # Source discovery is intentionally outside the database snapshot. It is
    # read-only filesystem work and a later Start rechecks the active-run guard.
    try:
        packages = tuple(
            PackageProjection(item.package_id, item.startable, item.diagnostic)
            for item in discover_packages()
        )
        discovery_error = None
    except InvalidPackage as exc:
        packages = ()
        discovery_error = str(exc)
    return AdminProjection(
        None,
        "READY",
        None,
        (),
        packages=packages,
        discovery_error=discovery_error,
    )


def get_public_state(*, now=None) -> PublicProjection:
    now = _server_now(now)
    with read_snapshot():
        run = Run.objects.filter(active=True).first()
        if run is None:
            return PublicProjection("READY")
        config = load_snapshot(run)
        global_state, _gameplay_ms_value, music, timing = _effective_run_state(
            run, config, now
        )
        return PublicProjection(
            global_state,
            _music_projection(run, config, music, timing, now, consumer="public"),
            tuple(
                PublicTeamProgressProjection(
                    team.team_id,
                    _advent_progress(
                        team,
                        tuple(
                            PuzzleProgress.objects.filter(
                                run=run,
                                team_id=team.team_id,
                                completed=True,
                            ).values_list("number", flat=True)
                        ),
                    ),
                )
                for team in TeamRun.objects.filter(run=run).order_by("team_id")
            ),
            _first_finisher_team_id(run),
            _gameplay_ms_value,
        )


def start_game(actor: Actor, command: StartGame, *, now=None) -> StartResult:
    now = _server_now(now)
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
                advent_clock_anchor=now,
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


def submit_answer(actor: Actor, command: SubmitAnswer, *, now=None) -> AnswerResult:
    now = _server_now(now)
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
                restored = _restore_answer(receipt.result)
                active = Run.objects.filter(pk=run_id, active=True).first()
                if active is not None:
                    # Preserve the recorded outcome while never replaying puzzle
                    # or hint content that has since become inaccessible.
                    return AnswerResult(
                        restored.outcome, _projection(active, actor.team_id, now)
                    )
                return restored
            run = Run.objects.filter(pk=run_id, active=True).first()
            if run is None:
                raise ApplicationError("stale_run")
            config = load_snapshot(run)
            if _persist_music_timing(run, config, now):
                _event(
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
            gameplay_ms = _gameplay_ms(run, now)
            _reconcile_expired_freezes(run, gameplay_ms)
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
                    run,
                    actor,
                    request_id,
                    actor.team_id,
                    team,
                    config,
                    puzzles,
                    puzzle,
                    progress,
                    current,
                    "correct_answer",
                    now=now,
                )
                outcome = "completed"
            else:
                changes = {}
                outcome = "incorrect"
            result = AnswerResult(outcome, _projection(run, actor.team_id, now))
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


def submit_music_answer(
    actor: Actor, command: SubmitMusicAnswer, *, now=None
) -> MusicAnswerResult:
    now = _server_now(now)
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
        "submit_music_answer",
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
            prior = CommandReceipt.objects.filter(
                actor_id=actor.user_id, request_id=request_id
            ).first()
            if prior is not None:
                if prior.payload_digest != digest:
                    raise ApplicationError("request_conflict")
                restored = _restore_music_answer(prior.result)
                active = Run.objects.filter(pk=run_id, active=True).first()
                if active is not None:
                    return MusicAnswerResult(
                        restored.outcome,
                        _projection(active, actor.team_id, now),
                    )
                return restored
            run = Run.objects.filter(pk=run_id, active=True).first()
            if run is None:
                raise ApplicationError("stale_run")
            config = load_snapshot(run)
            if config.get("schema_version") not in (4, 5, 6):
                raise ApplicationError("disallowed_state")
            _persist_music_timing(run, config, now)
            music = MusicQuiz.objects.get(run=run)
            number = music.current_question_number
            if number is None:
                raise ApplicationError("disallowed_state")
            question = config["music_questions"][number - 1]
            current_music_ms = effective_music_ms(
                music.music_elapsed_ms,
                music.music_clock_anchor,
                now,
            )
            scores = tuple(
                DomainMusicScore(row.team_id, row.score)
                for row in MusicScore.objects.filter(run=run).order_by("team_id")
            )
            team = TeamRun.objects.get(run=run, team_id=actor.team_id)
            decision = resolve_music_answer(
                global_state=run.global_state,
                phase=music.phase,
                current_question_id=question["id"],
                submitted_question_id=command.question_id,
                current_question_number=number,
                validator_type=question["validator"]["type"],
                expected_answer=question["validator"]["answer"],
                submitted_answer=command.answer,
                team_id=actor.team_id,
                scores=scores,
                team_points=team.points,
                reward_points=config["music_question_reward"],
                current_music_ms=current_music_ms,
            )
            attempt = MusicAttempt.objects.create(
                run=run,
                team_id=actor.team_id,
                actor_id=actor.user_id,
                request_id=request_id,
                question_number=number,
                question_id=question["id"],
                is_correct=decision.outcome == "won",
            )
            changes = {}
            if decision.outcome == "won":
                MusicQuestionResult.objects.create(
                    run=run,
                    question_number=number,
                    question_id=question["id"],
                    winner_team_id=actor.team_id,
                    reward_points=decision.points_delta,
                    winning_attempt=attempt,
                )
                score = MusicScore.objects.get(run=run, team_id=actor.team_id)
                before_score = score.score
                score.score += decision.score_delta
                score.save(update_fields=["score"])
                before_points = team.points
                team.points = decision.team_points
                team.save(update_fields=["points"])
                music.phase = decision.phase
                music.current_question_number = decision.current_question_number
                music.current_question_started_ms = (
                    current_music_ms if decision.phase == "question" else None
                )
                music.final_results_started_ms = decision.final_results_started_ms
                music.previous_winner_team = decision.winner_team_id
                music.save(
                    update_fields=[
                        "phase",
                        "current_question_number",
                        "current_question_started_ms",
                        "final_results_started_ms",
                        "previous_winner_team",
                    ]
                )
                changes = {
                    "music_score": {
                        "previous": before_score,
                        "delta": decision.score_delta,
                        "new": score.score,
                    },
                    "points": {
                        "previous": before_points,
                        "delta": decision.points_delta,
                        "new": team.points,
                    },
                    "question_number": {
                        "previous": number,
                        "new": decision.current_question_number,
                    },
                    "music_phase": decision.phase,
                }
            result = MusicAnswerResult(
                decision.outcome,
                _projection(run, actor.team_id, now),
            )
            CommandReceipt.objects.create(
                run=run,
                actor_id=actor.user_id,
                request_id=request_id,
                action="submit_music_answer",
                payload_digest=digest,
                result=asdict(result),
            )
            _event(
                run,
                actor,
                request_id,
                "music_answer",
                decision.outcome,
                team_id=actor.team_id,
                puzzle_id=question["id"],
                changes=changes,
            )
            return result
    except DomainError as exc:
        raise ApplicationError(exc.code) from exc
    except OperationalError as exc:
        if is_busy_error(exc):
            raise ApplicationError("temporarily_busy") from exc
        raise


def initiate_challenge(
    actor: Actor, command: RunCommand, *, now=None
) -> CommandResult:
    """Atomically spend the caller's one Challenge opportunity and start it."""

    def apply(run, _request_id, gameplay_ms):
        config = load_snapshot(run)
        if config.get("schema_version") != 6:
            raise ApplicationError("disallowed_state")
        initiator = TeamRun.objects.get(run=run, team_id=actor.team_id)
        challenged_id = "b" if actor.team_id == "a" else "a"
        challenged = TeamRun.objects.get(run=run, team_id=challenged_id)
        decision = decide_challenge_start(
            global_state=run.global_state,
            challenge_active=Challenge.objects.filter(
                run=run, status="active"
            ).exists(),
            initiator=_challenge_team_state(initiator),
            challenged=_challenge_team_state(challenged),
            current_gameplay_ms=gameplay_ms,
            cost=config["challenge_cost"],
        )
        _persist_challenge_team_state(initiator, decision.initiator)
        _persist_challenge_team_state(challenged, decision.challenged)
        challenge = Challenge.objects.create(
            run=run,
            initiator_team_id=actor.team_id,
            challenged_team_id=challenged_id,
            question_id=config["challenge_puzzle"]["id"],
            paid_cost=config["challenge_cost"],
        )
        return (
            "challenge_started",
            run,
            {
                "challenge_id": str(challenge.id),
                "paid_cost": config["challenge_cost"],
                "points": {
                    "previous": initiator.points - decision.points_delta,
                    "delta": decision.points_delta,
                    "new": initiator.points,
                },
                "opportunity_consumed": decision.opportunity_consumed,
                "activity_state": {"previous": "PUZZLE", "new": "CHALLENGE"},
            },
            actor.team_id,
            challenge.question_id,
        )

    return _perform(
        actor,
        command,
        "initiate_challenge",
        "team",
        {},
        apply,
        now=now,
    )


def submit_challenge_answer(
    actor: Actor, command: SubmitChallengeAnswer, *, now=None
) -> ChallengeAnswerResult:
    now = _server_now(now)
    request_id = _uuid(command.request_id)
    run_id = _uuid(command.run_id)
    challenge_id = _uuid(command.challenge_id)
    if (
        not isinstance(command.question_id, str)
        or not command.question_id
        or not isinstance(command.answer, str)
        or not command.answer.strip()
        or len(command.answer) > 500
    ):
        raise ApplicationError("invalid_input")
    digest = _digest(
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
            _verify_actor(actor, "team")
            prior = CommandReceipt.objects.filter(
                actor_id=actor.user_id, request_id=request_id
            ).first()
            if prior is not None:
                if prior.payload_digest != digest:
                    raise ApplicationError("request_conflict")
                restored = _restore_challenge_answer(prior.result)
                active = Run.objects.filter(pk=run_id, active=True).first()
                if active is not None:
                    return ChallengeAnswerResult(
                        restored.outcome,
                        _projection(active, actor.team_id, now),
                    )
                return restored
            run = Run.objects.filter(pk=run_id, active=True).first()
            if run is None:
                raise ApplicationError("stale_run")
            config = load_snapshot(run)
            if config.get("schema_version") != 6:
                raise ApplicationError("disallowed_state")
            if _persist_music_timing(run, config, now):
                _event(
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
            gameplay_ms = _gameplay_ms(run, now)
            _reconcile_expired_freezes(run, gameplay_ms)
            challenge = Challenge.objects.filter(
                pk=challenge_id, run=run, status="active"
            ).first()
            if challenge is None:
                raise ApplicationError("stale_challenge")
            initiator = TeamRun.objects.get(
                run=run, team_id=challenge.initiator_team_id
            )
            challenged = TeamRun.objects.get(
                run=run, team_id=challenge.challenged_team_id
            )
            puzzle = config["challenge_puzzle"]
            decision = resolve_challenge_answer(
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
                initiator=_challenge_team_state(initiator),
                challenged=_challenge_team_state(challenged),
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
                _persist_challenge_team_state(initiator, decision.initiator)
                _persist_challenge_team_state(challenged, decision.challenged)
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
            _event(
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
    except DomainError as exc:
        raise ApplicationError(exc.code) from exc
    except OperationalError as exc:
        if is_busy_error(exc):
            raise ApplicationError("temporarily_busy") from exc
        raise


def _perform(actor, command, action, role, payload, apply, *, now=None):
    """One writer transaction for a phase-2 action, receipt, and audit event."""
    now = _server_now(now)
    request_id, run_id, digest = _command_identity(actor, command, action, payload)
    try:
        with immediate_transaction():
            _verify_actor(actor, role)
            prior = _receipt(actor, request_id, digest)
            if prior is not None:
                return prior
            run = _active_run(run_id)
            config = load_snapshot(run)
            if _persist_music_timing(run, config, now):
                _event(
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
            gameplay_ms = _gameplay_ms(run, now)
            _reconcile_expired_freezes(run, gameplay_ms)
            outcome, result_run, changes, team_id, puzzle_id = apply(
                run, request_id, gameplay_ms
            )
            result = _command_result(outcome, result_run)
            _save_receipt(run, actor, request_id, action, digest, result)
            _event(
                run,
                actor,
                request_id,
                action,
                outcome,
                team_id=team_id,
                puzzle_id=puzzle_id,
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


def pause_game(actor: Actor, command: RunCommand, *, now=None) -> CommandResult:
    now = _server_now(now)

    def apply(run, _request_id, _gameplay_ms):
        previous = run.global_state
        if previous == "MUSIC_QUIZ":
            music = MusicQuiz.objects.get(run=run)
            transition = pause_music_interruption(
                global_state=previous,
                advent_clock=GameplayClock(
                    run.gameplay_elapsed_ms, run.advent_clock_anchor
                ),
                music_clock=MusicClock(
                    music.music_elapsed_ms, music.music_clock_anchor
                ),
                underlying_teams=_underlying_teams(run),
                now=now,
            )
            music.music_elapsed_ms = transition.music_clock.accumulated_ms
            music.music_clock_anchor = transition.music_clock.anchor
            music.save(update_fields=["music_elapsed_ms", "music_clock_anchor"])
            advent_clock = transition.advent_clock
            resume_target = transition.pause_resume_target
        else:
            advent_transition = pause_gameplay_clock(
                previous,
                run.gameplay_elapsed_ms,
                run.advent_clock_anchor,
                now,
            )
            advent_clock = advent_transition.clock
            resume_target = "ADVENT_QUIZ"
        run.global_state = "PAUSED"
        run.gameplay_elapsed_ms = advent_clock.accumulated_ms
        run.advent_clock_anchor = advent_clock.anchor
        run.pause_resume_target = resume_target
        run.save(
            update_fields=[
                "global_state",
                "gameplay_elapsed_ms",
                "advent_clock_anchor",
                "pause_resume_target",
            ]
        )
        return (
            "paused",
            run,
            {"global_state": {"previous": previous, "new": run.global_state}},
            None,
            "",
        )

    return _perform(actor, command, "pause", "admin", {}, apply, now=now)


def resume_game(actor: Actor, command: RunCommand, *, now=None) -> CommandResult:
    now = _server_now(now)

    def apply(run, _request_id, _gameplay_ms):
        previous = run.global_state
        target = run.pause_resume_target
        if target == "MUSIC_QUIZ":
            music = MusicQuiz.objects.get(run=run)
            transition = resume_music_interruption(
                global_state=previous,
                pause_resume_target=target,
                advent_clock=GameplayClock(
                    run.gameplay_elapsed_ms, run.advent_clock_anchor
                ),
                music_clock=MusicClock(
                    music.music_elapsed_ms, music.music_clock_anchor
                ),
                underlying_teams=_underlying_teams(run),
                now=now,
            )
            music.music_elapsed_ms = transition.music_clock.accumulated_ms
            music.music_clock_anchor = transition.music_clock.anchor
            music.save(update_fields=["music_elapsed_ms", "music_clock_anchor"])
            resumed_state = transition.global_state
            advent_clock = transition.advent_clock
        else:
            advent_transition = resume_gameplay_clock(
                previous,
                run.gameplay_elapsed_ms,
                run.advent_clock_anchor,
                now,
            )
            resumed_state = advent_transition.global_state
            advent_clock = advent_transition.clock
        run.global_state = resumed_state
        run.gameplay_elapsed_ms = advent_clock.accumulated_ms
        run.advent_clock_anchor = advent_clock.anchor
        run.pause_resume_target = None
        run.save(
            update_fields=[
                "global_state",
                "gameplay_elapsed_ms",
                "advent_clock_anchor",
                "pause_resume_target",
            ]
        )
        return (
            "resumed",
            run,
            {"global_state": {"previous": previous, "new": run.global_state}},
            None,
            "",
        )

    return _perform(actor, command, "resume", "admin", {}, apply, now=now)


def adjust_points(actor: Actor, command: AdminPoints, *, now=None) -> CommandResult:
    if (
        command.team_id not in ("a", "b")
        or type(command.delta) is not int
        or command.delta == 0
    ):
        raise ApplicationError("invalid_input")

    def apply(run, _request_id, _gameplay_ms):
        if run.global_state not in ("ADVENT_QUIZ", "PAUSED"):
            raise ApplicationError("disallowed_state")
        team = TeamRun.objects.get(run=run, team_id=command.team_id)
        before = team.points
        team.points = decide_points(before, command.delta)
        team.save(update_fields=["points"])
        return (
            "adjusted",
            run,
            {
                "points": {
                    "previous": before,
                    "delta": command.delta,
                    "new": team.points,
                }
            },
            command.team_id,
            "",
        )

    return _perform(
        actor,
        command,
        "adjust_points",
        "admin",
        {"team_id": command.team_id, "delta": command.delta},
        apply,
        now=now,
    )


def purchase_hint(actor: Actor, command: RunCommand, *, now=None) -> CommandResult:
    def apply(run, _request_id, _gameplay_ms):
        team = TeamRun.objects.get(run=run, team_id=actor.team_id)
        config = load_snapshot(run)
        if "hint_cost" not in config:
            raise ApplicationError("disallowed_state")
        before = team.points
        before_tokens = team.hint_tokens
        team.points, team.hint_tokens = decide_hint_purchase(
            run.global_state,
            team.activity_state,
            team.points,
            team.hint_tokens,
            config["hint_cost"],
        )
        team.save(update_fields=["points", "hint_tokens"])
        return (
            "purchased",
            run,
            {
                "points": {
                    "previous": before,
                    "delta": team.points - before,
                    "new": team.points,
                },
                "hint_tokens": {"previous": before_tokens, "new": team.hint_tokens},
            },
            actor.team_id,
            "",
        )

    return _perform(actor, command, "purchase_hint", "team", {}, apply, now=now)


def _reveal(
    actor: Actor, command: AdminPuzzle | TeamPuzzle, *, admin: bool, now=None
) -> CommandResult:
    if admin and command.team_id not in ("a", "b"):
        raise ApplicationError("invalid_input")
    if not isinstance(command.question_id, str) or not command.question_id:
        raise ApplicationError("invalid_input")
    team_id = command.team_id if admin else actor.team_id
    action = "provide_hint" if admin else "use_hint"

    def apply(run, request_id, _gameplay_ms):
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
            run.global_state,
            team.activity_state,
            team.current_number,
            puzzle["number"],
            team.hint_tokens,
            revealed,
            admin=admin,
        )
        if not newly:
            # A fresh repeat is a no-op, without another reveal audit event.
            return "already_revealed", run, {}, team_id, puzzle["id"]
        team.save(update_fields=["hint_tokens"])
        HintReveal.objects.create(
            run=run,
            team_id=team_id,
            puzzle_id=puzzle["id"],
            source="admin" if admin else "player",
            actor_id=actor.user_id,
            request_id=request_id,
        )
        return (
            "revealed",
            run,
            {
                "hint_tokens": {"previous": before, "new": team.hint_tokens},
                "hint_revealed": {"previous": False, "new": True},
            },
            team_id,
            puzzle["id"],
        )

    return _perform(
        actor,
        command,
        action,
        "admin" if admin else "team",
        {
            **({"team_id": team_id} if admin else {}),
            "question_id": command.question_id,
        },
        apply,
        now=now,
    )


def use_hint(actor: Actor, command: TeamPuzzle, *, now=None) -> CommandResult:
    return _reveal(actor, command, admin=False, now=now)


def provide_hint(actor: Actor, command: AdminPuzzle, *, now=None) -> CommandResult:
    return _reveal(actor, command, admin=True, now=now)


def _complete_action(
    actor: Actor, command: AdminPuzzle | TeamPuzzle, *, admin: bool, now=None
) -> CommandResult:
    if admin and command.team_id not in ("a", "b"):
        raise ApplicationError("invalid_input")
    if not isinstance(command.question_id, str) or not command.question_id:
        raise ApplicationError("invalid_input")
    team_id = command.team_id if admin else actor.team_id
    action = "force_complete" if admin else "skip"

    def apply(run, request_id, _gameplay_ms):
        team, config, puzzles, puzzle, progress, current = _current_puzzle(
            run, team_id, command.question_id
        )
        cost = 0
        if not admin:
            if "skip_cost" not in config:
                raise ApplicationError("disallowed_state")
            cost = config["skip_cost"]
        changes = _complete_current(
            run,
            actor,
            request_id,
            team_id,
            team,
            config,
            puzzles,
            puzzle,
            progress,
            current,
            "admin_force" if admin else "skip",
            cost=cost,
            now=_server_now(now),
        )
        return "completed", run, changes, team_id, puzzle["id"]

    return _perform(
        actor,
        command,
        action,
        "admin" if admin else "team",
        {
            **({"team_id": team_id} if admin else {}),
            "question_id": command.question_id,
        },
        apply,
        now=now,
    )


def skip_current(actor: Actor, command: TeamPuzzle, *, now=None) -> CommandResult:
    return _complete_action(actor, command, admin=False, now=now)


def force_complete_current(
    actor: Actor, command: AdminPuzzle, *, now=None
) -> CommandResult:
    return _complete_action(actor, command, admin=True, now=now)


def freeze_opponent(actor: Actor, command: RunCommand, *, now=None) -> CommandResult:
    """Immediately buy and apply one Freeze attack to the opposing team."""

    def apply(run, request_id, gameplay_ms):
        config = load_snapshot(run)
        if "freeze_cost" not in config:
            raise ApplicationError("disallowed_state")
        attacker = TeamRun.objects.get(run=run, team_id=actor.team_id)
        target_id = "b" if actor.team_id == "a" else "a"
        target = TeamRun.objects.get(run=run, team_id=target_id)
        before_points = attacker.points
        target_had_reverse = target.reverse_active
        decision = resolve_freeze_attack(
            run.global_state,
            _effect_state(attacker),
            _effect_state(target),
            gameplay_ms,
            config["freeze_cost"],
        )
        _persist_effect_state(attacker, decision.attacker)
        _persist_effect_state(target, decision.target)
        frozen_team = actor.team_id if decision.reversed else target_id
        if decision.reversed:
            _event(
                run,
                actor,
                request_id,
                "uno_reverse_consumed",
                "consumed",
                team_id=target_id,
                changes={"uno_reverse_active": {"previous": True, "new": False}},
            )
        return (
            "reversed" if decision.reversed else "frozen",
            run,
            {
                "points": {
                    "previous": before_points,
                    "delta": decision.points_delta,
                    "new": decision.attacker.points,
                },
                "target_team": target_id,
                "frozen_team": frozen_team,
                "reversed": decision.reversed,
                "target_reverse": {
                    "previous": target_had_reverse,
                    "new": decision.target.uno_reverse_active,
                },
                "freeze_started_gameplay_ms": gameplay_ms,
            },
            actor.team_id,
            "",
        )

    return _perform(actor, command, "freeze_attack", "team", {}, apply, now=now)


def purchase_uno_reverse(
    actor: Actor, command: RunCommand, *, now=None
) -> CommandResult:
    def apply(run, _request_id, gameplay_ms):
        config = load_snapshot(run)
        if "uno_reverse_cost" not in config:
            raise ApplicationError("disallowed_state")
        team = TeamRun.objects.get(run=run, team_id=actor.team_id)
        before_points = team.points
        decision = decide_reverse_purchase(
            run.global_state,
            _effect_state(team),
            gameplay_ms,
            config["uno_reverse_cost"],
        )
        _persist_effect_state(team, decision.team)
        return (
            "purchased",
            run,
            {
                "points": {
                    "previous": before_points,
                    "delta": decision.points_delta,
                    "new": decision.team.points,
                },
                "uno_reverse_active": {"previous": False, "new": True},
            },
            actor.team_id,
            "",
        )

    return _perform(actor, command, "purchase_uno_reverse", "team", {}, apply, now=now)


def _admin_freeze_action(
    actor: Actor, command: AdminTeam, *, remove: bool, now=None
) -> CommandResult:
    if command.team_id not in ("a", "b"):
        raise ApplicationError("invalid_input")
    action = "admin_unfreeze" if remove else "admin_freeze"

    def apply(run, _request_id, gameplay_ms):
        if run.pause_resume_target == "MUSIC_QUIZ":
            raise ApplicationError("disallowed_state")
        team = TeamRun.objects.get(run=run, team_id=command.team_id)
        decision = (
            remove_freeze(run.global_state, _effect_state(team), gameplay_ms)
            if remove
            else apply_direct_freeze(run.global_state, _effect_state(team), gameplay_ms)
        )
        _persist_effect_state(team, decision.team)
        return (
            "unfrozen" if remove else "frozen",
            run,
            {
                "activity_state": {
                    "previous": "FREEZE" if remove else "PUZZLE",
                    "new": decision.team.activity_state,
                },
                "freeze_started_gameplay_ms": decision.team.freeze_started_ms,
            },
            command.team_id,
            "",
        )

    return _perform(
        actor,
        command,
        action,
        "admin",
        {"team_id": command.team_id},
        apply,
        now=now,
    )


def admin_freeze(actor: Actor, command: AdminTeam, *, now=None) -> CommandResult:
    return _admin_freeze_action(actor, command, remove=False, now=now)


def admin_unfreeze(actor: Actor, command: AdminTeam, *, now=None) -> CommandResult:
    return _admin_freeze_action(actor, command, remove=True, now=now)


def reset_game(actor: Actor, command: RunCommand, *, now=None) -> CommandResult:
    def apply(run, _request_id, gameplay_ms):
        previous = run.global_state
        music = MusicQuiz.objects.filter(run=run).first()
        if music is not None and music.music_clock_anchor is not None:
            music.music_elapsed_ms = effective_music_ms(
                music.music_elapsed_ms,
                music.music_clock_anchor,
                _server_now(now),
            )
            music.music_clock_anchor = None
            music.save(update_fields=["music_elapsed_ms", "music_clock_anchor"])
        run.active = False
        run.global_state = "READY"
        run.gameplay_elapsed_ms = gameplay_ms
        run.advent_clock_anchor = None
        run.pause_resume_target = None
        run.save(
            update_fields=[
                "active",
                "global_state",
                "gameplay_elapsed_ms",
                "advent_clock_anchor",
                "pause_resume_target",
            ]
        )
        return (
            "reset",
            run,
            {
                "global_state": {"previous": previous, "new": "READY"},
                "active": {"previous": True, "new": False},
            },
            None,
            "",
        )

    return _perform(actor, command, "reset", "admin", {}, apply, now=now)
