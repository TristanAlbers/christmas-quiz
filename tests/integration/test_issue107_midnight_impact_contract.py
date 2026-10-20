import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from quiz.application import force_complete_current, start_game
from quiz.contracts import Actor, AdminPuzzle, StartGame
from quiz.models import AccountRole, TeamRun


class MidnightImpactContractTests(TestCase):
    def setUp(self):
        self.snapshots = TemporaryDirectory()
        self.addCleanup(self.snapshots.cleanup)
        scope = override_settings(QUIZ_SNAPSHOT_ROOT=Path(self.snapshots.name))
        scope.enable()
        self.addCleanup(scope.disable)

        users = get_user_model()
        self.admin_user = users.objects.create_user("issue107-admin")
        self.team_user = users.objects.create_user("issue107-a")
        AccountRole.objects.create(user=self.admin_user, role="admin")
        AccountRole.objects.create(user=self.team_user, role="team", team_id="a")
        self.admin = Actor(self.admin_user.pk, "admin")
        self.run_id = start_game(
            self.admin, StartGame(str(uuid4()), "christmas-2026-demo")
        ).run_id
        TeamRun.objects.filter(run_id=self.run_id, team_id="a").update(points=50)
        self.client.force_login(self.team_user)

    def post_answer(self, request_id, question_id, answer):
        return self.client.post(
            reverse("team_answer"),
            {
                "request_id": request_id,
                "run_id": self.run_id,
                "question_id": question_id,
                "answer": answer,
            },
            HTTP_HX_REQUEST="true",
        )

    def post_action(
        self, action, request_id, question_id="a-1", view_context=None
    ):
        data = {
            "request_id": request_id,
            "run_id": self.run_id,
            "question_id": question_id,
        }
        if view_context is not None:
            data["view_context"] = view_context
        return self.client.post(
            reverse("team_action", args=[action]),
            data,
            HTTP_HX_REQUEST="true",
        )

    def triggers(self, response):
        return json.loads(response.headers["HX-Trigger-After-Swap"])

    def test_correct_answer_emits_exact_committed_door_and_retry_is_suppressed(self):
        request_id = str(uuid4())
        response = self.post_answer(request_id, "a-1", "red")

        self.assertEqual(response.status_code, 200)
        payload = self.triggers(response)["routineFeedbackConfirmed"]
        self.assertEqual(payload["version"], 1)
        self.assertEqual(payload["actionId"], request_id)
        self.assertEqual(payload["runId"], self.run_id)
        self.assertEqual(payload["kind"], "puzzle_solved")
        chocolate_url = payload["puzzle"]["chocolate"]["staticUrl"]
        self.assertRegex(
            chocolate_url,
            r"^/static/quiz/chocolates/engel(?:\.[a-f0-9]{12})?\.png$",
        )
        self.assertEqual(
            payload["eventId"],
            f"{self.run_id}:{request_id}:puzzle_solved",
        )
        self.assertEqual(
            payload["puzzle"],
            {
                "id": "a-1",
                "number": 1,
                "nextNumber": 2,
                "chocolate": {
                    "subject": "engel",
                    "staticUrl": chocolate_url,
                    "width": 1254,
                    "height": 1254,
                    "viewBox": "67 42 1137 1195",
                    "isBroad": False,
                },
            },
        )
        self.assertEqual(
            payload["state"],
            {
                "globalState": "ADVENT_QUIZ",
                "teamState": "PUZZLE",
                "questionId": "a-2",
                "musicPhase": None,
                "challengePhase": None,
                "firstFinisherTeamId": None,
                "gameplayElapsedMs": payload["state"]["gameplayElapsedMs"],
            },
        )
        self.assertGreaterEqual(payload["state"]["gameplayElapsedMs"], 0)

        retry = self.post_answer(request_id, "a-1", "red")
        self.assertEqual(retry.status_code, 200)
        self.assertNotIn("HX-Trigger-After-Swap", retry.headers)
        poll = self.client.get(reverse("team_state"))
        self.assertNotIn("HX-Trigger-After-Swap", poll.headers)

    def test_skip_and_purchases_have_distinct_typed_successes(self):
        hint_id = str(uuid4())
        hint = self.post_action("purchase-hint", hint_id)
        hint_triggers = self.triggers(hint)
        self.assertTrue(hint_triggers["shopPurchaseSucceeded"])
        self.assertEqual(
            hint_triggers["routineFeedbackConfirmed"]["kind"], "hint_purchased"
        )
        self.assertNotIn("puzzle", hint_triggers["routineFeedbackConfirmed"])

        reverse_id = str(uuid4())
        reverse_response = self.post_action("purchase-reverse", reverse_id)
        reverse_triggers = self.triggers(reverse_response)
        self.assertTrue(reverse_triggers["shopPurchaseSucceeded"])
        self.assertEqual(
            reverse_triggers["routineFeedbackConfirmed"]["kind"],
            "reverse_purchased",
        )

        skip_id = str(uuid4())
        skipped = self.post_action("skip", skip_id)
        skip_payload = self.triggers(skipped)["routineFeedbackConfirmed"]
        self.assertEqual(skip_payload["kind"], "puzzle_skipped")
        self.assertEqual(skip_payload["puzzle"]["id"], "a-1")
        self.assertEqual(skip_payload["puzzle"]["number"], 1)
        self.assertEqual(skip_payload["puzzle"]["nextNumber"], 2)
        self.assertEqual(skip_payload["puzzle"]["chocolate"]["subject"], "engel")

        retry = self.post_action("skip", skip_id)
        self.assertNotIn("HX-Trigger-After-Swap", retry.headers)

    def test_failures_and_music_takeover_emit_no_routine_feedback(self):
        wrong = self.post_answer(str(uuid4()), "a-1", "wrong")
        self.assertEqual(wrong.status_code, 200)
        self.assertNotIn("HX-Trigger-After-Swap", wrong.headers)

        TeamRun.objects.filter(run_id=self.run_id, team_id="a").update(points=0)
        rejected = self.post_action("purchase-hint", str(uuid4()))
        self.assertEqual(rejected.status_code, 409)
        self.assertNotIn("HX-Trigger-After-Swap", rejected.headers)

        for number in range(1, 13):
            force_complete_current(
                self.admin,
                AdminPuzzle(
                    str(uuid4()), self.run_id, "a", f"a-{number}"
                ),
            )
        music = self.post_answer(str(uuid4()), "a-13", "music")
        self.assertEqual(music.status_code, 200)
        self.assertNotIn("HX-Trigger-After-Swap", music.headers)

    @override_settings(
        STORAGES={
            "staticfiles": {
                "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
            }
        }
    )
    def test_shop_purchase_preserves_only_a_matching_question_pane(self):
        page = self.client.get(reverse("team"))
        view_context = page.context["view_context"]
        self.assertContains(
            page,
            'id="team-shop-dialog"',
        )
        self.assertContains(page, 'hx-include="#view-context"')

        for action, kind in (
            ("purchase-hint", "hint_purchased"),
            ("purchase-reverse", "reverse_purchased"),
        ):
            with self.subTest(action=action):
                response = self.post_action(
                    action, str(uuid4()), view_context=view_context
                )
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, 'id="question-pane"')
                self.assertContains(
                    response,
                    'id="team-resource-values"',
                )
                self.assertEqual(
                    self.triggers(response)["routineFeedbackConfirmed"]["kind"],
                    kind,
                )

    def test_shop_purchase_replaces_pane_for_missing_or_stale_context(self):
        missing = self.post_action("purchase-hint", str(uuid4()))
        self.assertEqual(missing.status_code, 200)
        self.assertContains(missing, 'id="question-pane"')

        stale = self.post_action(
            "purchase-reverse", str(uuid4()), view_context="stale-view"
        )
        self.assertEqual(stale.status_code, 200)
        self.assertContains(stale, 'id="question-pane"')

