"""Regression coverage for issue #43 public Freeze projection boundaries."""

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from quiz.application import (
    admin_freeze,
    force_complete_current,
    get_public_state,
    get_team_state,
    initiate_challenge,
    start_game,
    submit_music_answer,
)
from quiz.contracts import (
    Actor,
    AdminPuzzle,
    AdminTeam,
    RunCommand,
    StartGame,
    SubmitMusicAnswer,
)
from quiz.models import AccountRole, Run

NOW = datetime(2026, 12, 24, 18, 0, tzinfo=timezone.utc)
MUSIC_ANSWERS = (
    "jingle bells",
    "silent night",
    "white christmas",
    "feliz navidad",
    "last christmas",
    "santa baby",
    "winter wonderland",
    "let it snow",
    "the christmas song",
    "rudolph",
    "deck the halls",
)


class Issue43PublicFreezeProjectionTests(TestCase):
    def setUp(self):
        self.snapshots = TemporaryDirectory()
        self.addCleanup(self.snapshots.cleanup)
        scope = override_settings(QUIZ_SNAPSHOT_ROOT=Path(self.snapshots.name))
        scope.enable()
        self.addCleanup(scope.disable)

        users = get_user_model()
        admin_user = users.objects.create_user("issue43-projection-admin")
        a_user = users.objects.create_user("issue43-projection-a")
        b_user = users.objects.create_user("issue43-projection-b")
        AccountRole.objects.create(user=admin_user, role="admin")
        AccountRole.objects.create(user=a_user, role="team", team_id="a")
        AccountRole.objects.create(user=b_user, role="team", team_id="b")
        self.admin = Actor(admin_user.pk, "admin")
        self.a = Actor(a_user.pk, "team", "a")
        self.b = Actor(b_user.pk, "team", "b")
        self.run_id = start_game(
            self.admin,
            StartGame(str(uuid4()), "christmas-2026-demo"),
            now=NOW,
        ).run_id

    def _force_a_through(self, number, *, now=NOW):
        for puzzle_number in range(1, number + 1):
            force_complete_current(
                self.admin,
                AdminPuzzle(
                    str(uuid4()),
                    self.run_id,
                    "a",
                    f"a-{puzzle_number}",
                ),
                now=now,
            )

    def _start_music_with_frozen_b(self):
        self._force_a_through(12)
        admin_freeze(
            self.admin,
            AdminTeam(str(uuid4()), self.run_id, "b"),
            now=NOW + timedelta(seconds=10),
        )
        force_complete_current(
            self.admin,
            AdminPuzzle(str(uuid4()), self.run_id, "a", "a-13"),
            now=NOW + timedelta(seconds=20),
        )

    def test_takeover_projections_omit_advent_only_freeze_field(self):
        initiate_challenge(
            self.a,
            RunCommand(str(uuid4()), self.run_id),
            now=NOW + timedelta(seconds=1),
        )
        public = get_public_state(now=NOW + timedelta(seconds=1))
        self.assertIsNotNone(public.challenge)
        for team in asdict(public)["teams"]:
            self.assertNotIn("is_frozen", team)

    def test_read_only_music_completion_uses_effective_clock_for_freeze(self):
        self._start_music_with_frozen_b()

        music_public = get_public_state(now=NOW + timedelta(seconds=80))
        self.assertIsNotNone(music_public.music)
        for team in asdict(music_public)["teams"]:
            self.assertNotIn("is_frozen", team)

        answer_time = NOW + timedelta(seconds=80)
        for number, answer in enumerate(MUSIC_ANSWERS, start=1):
            submit_music_answer(
                self.a,
                SubmitMusicAnswer(
                    str(uuid4()),
                    self.run_id,
                    f"music-{number}",
                    answer,
                ),
                now=answer_time + timedelta(seconds=number),
            )

        final_time = answer_time + timedelta(seconds=len(MUSIC_ANSWERS))
        final_public = get_public_state(now=final_time)
        self.assertEqual(final_public.music.phase, "final_results")
        for team in asdict(final_public)["teams"]:
            self.assertNotIn("is_frozen", team)

        late = final_time + timedelta(seconds=360)
        team_b = get_team_state(self.b, now=late)
        self.assertEqual(team_b.global_state, "ADVENT_QUIZ")
        self.assertNotEqual(team_b.team_state, "FREEZE")

        # The transition above is deliberately read-only: persisted state still
        # says Music while the effective projection has logically resumed Advent.
        persisted = Run.objects.get(pk=self.run_id)
        self.assertEqual(persisted.global_state, "MUSIC_QUIZ")

        public = get_public_state(now=late)
        self.assertEqual(public.global_state, "ADVENT_QUIZ")
        self.assertIsNone(public.music)
        team_b_public = next(team for team in public.teams if team.team_id == "b")
        self.assertFalse(team_b_public.is_frozen)
        self.assertGreater(public.gameplay_elapsed_ms, 300_000)
