"""Phase 1 durability, immutable snapshot, and receipt regression tests."""

import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connections
from django.test import TransactionTestCase, override_settings
from django.urls import reverse

from quiz.application import get_team_state, start_game, submit_answer
from quiz.contracts import Actor, ApplicationError, StartGame, SubmitAnswer
from quiz.models import AccountRole, AnswerReceipt, Attempt, AuditEvent, FragmentAward


class FirstSliceRecoveryTests(TransactionTestCase):
    def setUp(self):
        self.runtime = TemporaryDirectory()
        self.addCleanup(self.runtime.cleanup)
        runtime = Path(self.runtime.name)
        games_root = runtime / "games"
        shutil.copytree(
            settings.BASE_DIR / "games" / "christmas-2026-demo",
            games_root / "christmas-2026-demo",
        )
        self.package_root = games_root / "christmas-2026-demo"
        scope = override_settings(
            QUIZ_GAMES_ROOT=games_root,
            QUIZ_SNAPSHOT_ROOT=runtime / "snapshots",
        )
        scope.enable()
        self.addCleanup(scope.disable)

        users = get_user_model()
        self.admin = users.objects.create_user("recovery-admin", password="admin-pin")
        self.a = users.objects.create_user("recovery-a", password="a-pin")
        AccountRole.objects.create(user=self.admin, role="admin")
        AccountRole.objects.create(user=self.a, role="team", team_id="a")
        self.admin_actor = Actor(self.admin.pk, "admin")
        self.a_actor = Actor(self.a.pk, "team", "a")
        self.run_id = start_game(
            self.admin_actor, StartGame(str(uuid4()), "christmas-2026-demo")
        ).run_id

    def test_source_configuration_and_media_deletion_do_not_change_active_run(self):
        self.client.force_login(self.a)
        media_url = reverse(
            "private_media",
            kwargs={
                "run_id": self.run_id,
                "team_id": "a",
                "asset_path": "a/star.png",
            },
        )
        original_media = b"".join(self.client.get(media_url).streaming_content)
        before = get_team_state(self.a_actor)
        self.assertEqual(before.question.id, "a-1")

        source_json = self.package_root / "game.json"
        altered = json.loads(source_json.read_text())
        altered["teams"]["a"]["puzzles"][0]["body"] = "Changed after Start"
        altered["teams"]["a"]["puzzles"][0]["validator"]["answer"] = "green"
        altered["teams"]["a"]["puzzles"][0]["reward_points"] = 999
        source_json.write_text(json.dumps(altered))
        (self.package_root / "a" / "star.png").write_bytes(b"changed")
        shutil.rmtree(self.package_root)
        connections.close_all()

        after = get_team_state(self.a_actor)
        self.assertEqual(after.question.body, before.question.body)
        self.assertEqual(
            b"".join(self.client.get(media_url).streaming_content), original_media
        )
        result = submit_answer(
            self.a_actor,
            SubmitAnswer(str(uuid4()), self.run_id, "a-1", "red"),
        )
        self.assertEqual(result.outcome, "completed")
        self.assertEqual(result.state.points, 7)
        self.assertEqual(result.state.question.id, "a-2")
        event = AuditEvent.objects.get(team_id="a")
        with self.assertRaises(ValueError):
            event.delete()
        with self.assertRaises(ValueError):
            event.save()
        self.assertTrue(AuditEvent.objects.filter(pk=event.pk).exists())

    def test_reload_recovers_wrong_attempt_and_receipt_retries_do_not_reaward(self):
        wrong_id = str(uuid4())
        wrong = SubmitAnswer(wrong_id, self.run_id, "a-1", "blue")
        self.assertEqual(submit_answer(self.a_actor, wrong).outcome, "incorrect")
        connections.close_all()
        self.assertEqual(get_team_state(self.a_actor).current_number, 1)
        self.assertEqual(Attempt.objects.count(), 1)
        self.assertEqual(submit_answer(self.a_actor, wrong).outcome, "incorrect")
        self.assertEqual(Attempt.objects.count(), 1)

        correct = SubmitAnswer(str(uuid4()), self.run_id, "a-1", "red")
        first = submit_answer(self.a_actor, correct)
        connections.close_all()
        retry = submit_answer(self.a_actor, correct)
        self.assertEqual(retry.outcome, first.outcome)
        self.assertEqual(retry.state.question.id, "a-2")
        self.assertEqual(get_team_state(self.a_actor).points, 7)
        self.assertEqual(Attempt.objects.count(), 2)

        with self.assertRaises(ApplicationError) as conflict:
            submit_answer(
                self.a_actor,
                SubmitAnswer(correct.request_id, self.run_id, "a-1", "green"),
            )
        self.assertEqual(conflict.exception.code, "request_conflict")
        with self.assertRaises(ApplicationError) as stale_question:
            submit_answer(
                self.a_actor,
                SubmitAnswer(str(uuid4()), self.run_id, "a-1", "red"),
            )
        self.assertEqual(stale_question.exception.code, "stale_question")
        with self.assertRaises(ApplicationError) as stale_run:
            submit_answer(
                self.a_actor,
                SubmitAnswer(str(uuid4()), str(uuid4()), "a-2", "3"),
            )
        self.assertEqual(stale_run.exception.code, "stale_run")
        self.assertEqual(Attempt.objects.count(), 2)

    def test_audit_failure_rolls_back_entire_correct_completion(self):
        command = SubmitAnswer(str(uuid4()), self.run_id, "a-1", "red")
        def fail_audit(*args, **kwargs):
            raise RuntimeError("injected audit storage failure")

        with (
            patch.object(AuditEvent.objects, "create", side_effect=fail_audit),
            self.assertRaisesRegex(RuntimeError, "injected audit"),
        ):
            submit_answer(self.a_actor, command)

        self.assertEqual(Attempt.objects.count(), 0)
        self.assertEqual(AnswerReceipt.objects.count(), 0)
        self.assertEqual(FragmentAward.objects.count(), 0)
        state = get_team_state(self.a_actor)
        self.assertEqual(state.current_number, 1)
        self.assertEqual(state.points, 3)
        self.assertEqual(state.fragments, ())
        self.assertEqual(AuditEvent.objects.count(), 1)  # Start only.

        # A failed command has no receipt and is safe to retry with the same ID.
        result = submit_answer(self.a_actor, command)
        self.assertEqual(result.outcome, "completed")
        self.assertEqual(result.state.points, 7)
        self.assertEqual(Attempt.objects.count(), 1)
