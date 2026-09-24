"""Persistent facts for the first authenticated game slice."""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class AccountRole(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    role = models.CharField(
        max_length=8, choices=[("team", "Team"), ("admin", "Admin")]
    )
    team_id = models.CharField(max_length=1, null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(Q(role="team") & Q(team_id__in=["a", "b"]))
                | (Q(role="admin") & Q(team_id__isnull=True)),
                name="valid_account_role",
            ),
            models.UniqueConstraint(
                fields=["team_id"],
                condition=Q(role="team"),
                name="one_account_per_team",
            ),
        ]


class Run(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    active = models.BooleanField(default=True)
    global_state = models.CharField(max_length=24)
    package_id = models.CharField(max_length=100)
    snapshot_path = models.CharField(max_length=500)
    snapshot_digest = models.CharField(max_length=64)
    gameplay_elapsed_ms = models.BigIntegerField(default=0)
    advent_clock_anchor = models.DateTimeField(null=True, blank=True)
    pause_resume_target = models.CharField(max_length=24, null=True, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["active"], condition=Q(active=True), name="one_active_run"
            ),
            models.CheckConstraint(
                condition=Q(gameplay_elapsed_ms__gte=0),
                name="gameplay_elapsed_nonnegative",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        global_state="PAUSED",
                        pause_resume_target__in=["ADVENT_QUIZ", "MUSIC_QUIZ"],
                    )
                    | (~Q(global_state="PAUSED") & Q(pause_resume_target__isnull=True))
                ),
                name="pause_resume_target_state_pair",
            ),
        ]


class TeamRun(models.Model):
    run = models.ForeignKey(Run, on_delete=models.PROTECT)
    team_id = models.CharField(max_length=1)
    activity_state = models.CharField(max_length=24)
    current_number = models.PositiveSmallIntegerField(default=1)
    points = models.IntegerField(default=0)
    hint_tokens = models.IntegerField(default=0)
    freeze_started_gameplay_ms = models.BigIntegerField(null=True, blank=True)
    reverse_active = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["run", "team_id"], name="unique_team_run"),
            models.CheckConstraint(
                condition=Q(team_id__in=["a", "b"]), name="valid_team_run_id"
            ),
            models.CheckConstraint(
                condition=Q(points__gte=0), name="team_points_nonnegative"
            ),
            models.CheckConstraint(
                condition=Q(hint_tokens__gte=0), name="hint_tokens_nonnegative"
            ),
            models.CheckConstraint(
                condition=Q(current_number__gte=1), name="current_number_positive"
            ),
            models.CheckConstraint(
                condition=Q(freeze_started_gameplay_ms__isnull=True)
                | Q(freeze_started_gameplay_ms__gte=0),
                name="freeze_start_nonnegative",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        activity_state="FREEZE",
                        freeze_started_gameplay_ms__isnull=False,
                    )
                    | (
                        ~Q(activity_state="FREEZE")
                        & Q(freeze_started_gameplay_ms__isnull=True)
                    )
                ),
                name="freeze_state_start_paired",
            ),
        ]


class PuzzleProgress(models.Model):
    run = models.ForeignKey(Run, on_delete=models.PROTECT)
    team_id = models.CharField(max_length=1)
    puzzle_id = models.CharField(max_length=100)
    number = models.PositiveSmallIntegerField()
    completed = models.BooleanField(default=False)
    completion_route = models.CharField(max_length=24, blank=True)
    reward_awarded = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["run", "team_id", "puzzle_id"], name="unique_puzzle_progress"
            ),
            models.UniqueConstraint(
                fields=["run", "team_id", "number"], name="unique_puzzle_number"
            ),
            models.CheckConstraint(
                condition=Q(team_id__in=["a", "b"]), name="valid_progress_team"
            ),
            models.CheckConstraint(
                condition=Q(number__gte=1), name="puzzle_number_positive"
            ),
        ]


class Attempt(models.Model):
    run = models.ForeignKey(Run, on_delete=models.PROTECT)
    team_id = models.CharField(max_length=1)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    puzzle_id = models.CharField(max_length=100)
    number = models.PositiveSmallIntegerField()
    is_correct = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(team_id__in=["a", "b"]), name="valid_attempt_team"
            )
        ]


class FragmentAward(models.Model):
    run = models.ForeignKey(Run, on_delete=models.PROTECT)
    team_id = models.CharField(max_length=1)
    puzzle_id = models.CharField(max_length=100)
    fragment = models.TextField()
    awarded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["run", "team_id", "puzzle_id"], name="unique_fragment_award"
            ),
            models.CheckConstraint(
                condition=Q(team_id__in=["a", "b"]), name="valid_fragment_team"
            ),
        ]


class StartReceipt(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    request_id = models.UUIDField()
    payload_digest = models.CharField(max_length=64)
    run = models.ForeignKey(Run, on_delete=models.PROTECT)
    result = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["actor", "request_id"], name="unique_start_receipt"
            )
        ]


class AnswerReceipt(models.Model):
    run = models.ForeignKey(Run, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    request_id = models.UUIDField()
    payload_digest = models.CharField(max_length=64)
    result = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["run", "actor", "request_id"], name="unique_answer_receipt"
            )
        ]


class CommandReceipt(models.Model):
    """Committed result for one phase-2 command by an authenticated actor."""

    run = models.ForeignKey(Run, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    request_id = models.UUIDField()
    action = models.CharField(max_length=40)
    payload_digest = models.CharField(max_length=64)
    result = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["actor", "request_id"], name="unique_command_receipt"
            )
        ]


class HintReveal(models.Model):
    """One durable reveal per team and puzzle; text remains in the run snapshot."""

    run = models.ForeignKey(Run, on_delete=models.PROTECT)
    team_id = models.CharField(max_length=1)
    puzzle_id = models.CharField(max_length=100)
    source = models.CharField(
        max_length=8, choices=[("player", "Player"), ("admin", "Admin")]
    )
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    request_id = models.UUIDField()
    revealed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["run", "team_id", "puzzle_id"], name="unique_hint_reveal"
            ),
            models.CheckConstraint(
                condition=Q(team_id__in=["a", "b"]), name="valid_hint_team"
            ),
        ]


class AuditEvent(models.Model):
    """Append-only history through the supported application API."""

    created_at = models.DateTimeField(auto_now_add=True)
    run = models.ForeignKey(Run, on_delete=models.PROTECT)
    request_id = models.UUIDField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    actor_role = models.CharField(max_length=8)
    team_id = models.CharField(max_length=1, null=True, blank=True)
    action = models.CharField(max_length=40)
    result = models.CharField(max_length=40)
    puzzle_id = models.CharField(max_length=100, blank=True)
    changes = models.JSONField(default=dict)

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("Audit events are immutable")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Audit events cannot be deleted")


class FirstFinisher(models.Model):
    """Immutable, one-per-run fact recording the first team to finish."""

    run = models.OneToOneField(
        Run,
        on_delete=models.PROTECT,
        related_name="first_finisher",
    )
    team_id = models.CharField(max_length=1)
    finished_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(team_id__in=["a", "b"]),
                name="valid_first_finisher_team",
            )
        ]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("First-finisher facts are immutable")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("First-finisher facts cannot be deleted")


class MusicQuiz(models.Model):
    """Durable one-per-run Music trigger and recoverable interruption clock."""

    run = models.OneToOneField(Run, on_delete=models.PROTECT, related_name="music_quiz")
    phase = models.CharField(max_length=16)
    current_question_number = models.PositiveSmallIntegerField(null=True, blank=True)
    current_question_started_ms = models.BigIntegerField(
        default=0, null=True, blank=True
    )
    music_elapsed_ms = models.BigIntegerField(default=0)
    music_clock_anchor = models.DateTimeField(null=True, blank=True)
    final_results_started_ms = models.BigIntegerField(null=True, blank=True)
    previous_winner_team = models.CharField(max_length=1, null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(music_elapsed_ms__gte=0),
                name="music_elapsed_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(current_question_started_ms__isnull=True)
                | Q(current_question_started_ms__gte=0),
                name="music_question_start_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(previous_winner_team__isnull=True)
                | Q(previous_winner_team__in=["a", "b"]),
                name="valid_music_previous_winner",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        phase="question",
                        current_question_number__isnull=False,
                        current_question_number__gte=1,
                        current_question_number__lte=11,
                        current_question_started_ms__isnull=False,
                        final_results_started_ms__isnull=True,
                    )
                    | Q(
                        phase="final_results",
                        current_question_number__isnull=True,
                        current_question_started_ms__isnull=True,
                        final_results_started_ms__isnull=False,
                        final_results_started_ms__gte=0,
                    )
                    | Q(
                        phase="completed",
                        current_question_number__isnull=True,
                        current_question_started_ms__isnull=True,
                        final_results_started_ms__isnull=False,
                        final_results_started_ms__gte=0,
                        music_clock_anchor__isnull=True,
                    )
                ),
                name="valid_music_phase_state",
            ),
        ]


class MusicScore(models.Model):
    run = models.ForeignKey(Run, on_delete=models.PROTECT)
    team_id = models.CharField(max_length=1)
    score = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["run", "team_id"], name="unique_music_score"
            ),
            models.CheckConstraint(
                condition=Q(team_id__in=["a", "b"]), name="valid_music_score_team"
            ),
            models.CheckConstraint(
                condition=Q(score__lte=11), name="music_score_at_most_eleven"
            ),
        ]


class MusicAttempt(models.Model):
    """Append-only accepted-current-question attempt."""

    run = models.ForeignKey(Run, on_delete=models.PROTECT)
    team_id = models.CharField(max_length=1)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    request_id = models.UUIDField()
    question_number = models.PositiveSmallIntegerField()
    question_id = models.CharField(max_length=100)
    is_correct = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["run", "actor", "request_id"],
                name="unique_music_attempt_request",
            ),
            models.UniqueConstraint(
                fields=["run", "question_number"],
                condition=Q(is_correct=True),
                name="unique_correct_music_attempt",
            ),
            models.CheckConstraint(
                condition=Q(team_id__in=["a", "b"]),
                name="valid_music_attempt_team",
            ),
            models.CheckConstraint(
                condition=Q(question_number__gte=1, question_number__lte=11),
                name="valid_music_attempt_number",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("Music attempts are immutable")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Music attempts cannot be deleted")


class MusicQuestionResult(models.Model):
    """Immutable winner fact; uniqueness is the storage-level race guard."""

    run = models.ForeignKey(Run, on_delete=models.PROTECT)
    question_number = models.PositiveSmallIntegerField()
    question_id = models.CharField(max_length=100)
    winner_team_id = models.CharField(max_length=1)
    reward_points = models.PositiveIntegerField()
    winning_attempt = models.OneToOneField(MusicAttempt, on_delete=models.PROTECT)
    resolved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["run", "question_number"],
                name="unique_music_question_number",
            ),
            models.UniqueConstraint(
                fields=["run", "question_id"], name="unique_music_question_id"
            ),
            models.CheckConstraint(
                condition=Q(winner_team_id__in=["a", "b"]),
                name="valid_music_winner_team",
            ),
            models.CheckConstraint(
                condition=Q(question_number__gte=1, question_number__lte=11),
                name="valid_music_result_number",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("Music question results are immutable")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Music question results cannot be deleted")
