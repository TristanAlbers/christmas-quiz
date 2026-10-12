"""Challenge snapshot media authorization and context isolation."""

from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from quiz.configuration import snapshot_challenge_media_path, stage_snapshot
from quiz.models import AccountRole, Challenge, Run
from tests.integration.test_phase6_storage import phase6_config, write_package


class PhaseSixChallengeMediaSecurityTests(TestCase):
    def test_only_active_context_participants_and_admin_receive_declared_media(self):
        users = get_user_model()
        team_user = users.objects.create_user("phase6-media-team")
        admin_user = users.objects.create_user("phase6-media-admin")
        AccountRole.objects.create(user=team_user, role="team", team_id="a")
        AccountRole.objects.create(user=admin_user, role="admin")
        with TemporaryDirectory() as directory:
            root = Path(directory)
            games = root / "games"
            write_package(games, phase6_config())
            with override_settings(
                QUIZ_GAMES_ROOT=games,
                QUIZ_SNAPSHOT_ROOT=root / "snapshots",
            ):
                staged = stage_snapshot("phase6")
                run = Run.objects.create(
                    global_state="ADVENT_QUIZ",
                    package_id="phase6",
                    snapshot_path=staged.path,
                    snapshot_digest=staged.digest,
                )
                challenge = Challenge.objects.create(
                    run=run,
                    initiator_team_id="a",
                    challenged_team_id="b",
                    question_id="challenge-a",
                    paid_cost=0,
                    started_gameplay_ms=0,
                )

                participant = snapshot_challenge_media_path(
                    run,
                    challenge,
                    actor_role="team",
                    actor_team_id="a",
                    relative_path="challenge/a.png",
                )
                opponent = snapshot_challenge_media_path(
                    run,
                    challenge,
                    actor_role="team",
                    actor_team_id="b",
                    relative_path="challenge/a.png",
                )
                admin = snapshot_challenge_media_path(
                    run,
                    challenge,
                    actor_role="admin",
                    actor_team_id=None,
                    relative_path="challenge/a.png",
                )
                denied = (
                    snapshot_challenge_media_path(
                        run,
                        challenge,
                        actor_role="team",
                        actor_team_id=None,
                        relative_path="challenge/a.png",
                    ),
                    snapshot_challenge_media_path(
                        run,
                        challenge,
                        actor_role="public",
                        actor_team_id=None,
                        relative_path="challenge/a.png",
                    ),
                    snapshot_challenge_media_path(
                        run,
                        challenge,
                        actor_role="team",
                        actor_team_id="a",
                        relative_path="challenge/b.png",
                    ),
                )

                self.assertEqual(participant.read_bytes(), b"challenge-media-a")
                self.assertEqual(opponent.read_bytes(), b"challenge-media-a")
                self.assertEqual(admin.read_bytes(), b"challenge-media-a")
                self.assertEqual(denied, (None, None, None))

                run.global_state = "PAUSED"
                paused_participant = snapshot_challenge_media_path(
                    run,
                    challenge,
                    actor_role="team",
                    actor_team_id="a",
                    relative_path="challenge/a.png",
                )
                paused_admin = snapshot_challenge_media_path(
                    run,
                    challenge,
                    actor_role="admin",
                    actor_team_id=None,
                    relative_path="challenge/a.png",
                )
                paused_public = snapshot_challenge_media_path(
                    run,
                    challenge,
                    actor_role="public",
                    actor_team_id=None,
                    relative_path="challenge/a.png",
                )
                self.assertEqual(
                    paused_participant.read_bytes(), b"challenge-media-a"
                )
                self.assertEqual(paused_admin.read_bytes(), b"challenge-media-a")
                self.assertIsNone(paused_public)
                for unavailable_state in ("READY", "MUSIC_QUIZ", "FINISHED"):
                    run.global_state = unavailable_state
                    self.assertIsNone(
                        snapshot_challenge_media_path(
                            run,
                            challenge,
                            actor_role="admin",
                            actor_team_id=None,
                            relative_path="challenge/a.png",
                        )
                    )
                run.global_state = "ADVENT_QUIZ"
                challenge.status = "resolved"
                self.assertIsNone(
                    snapshot_challenge_media_path(
                        run,
                        challenge,
                        actor_role="team",
                        actor_team_id="a",
                        relative_path="challenge/a.png",
                    )
                )

    def test_revealed_media_route_survives_pause_and_resume(self):
        users = get_user_model()
        team_user = users.objects.create_user("phase6-media-route-team")
        admin_user = users.objects.create_user("phase6-media-route-admin")
        AccountRole.objects.create(user=team_user, role="team", team_id="a")
        AccountRole.objects.create(user=admin_user, role="admin")
        with TemporaryDirectory() as directory:
            root = Path(directory)
            games = root / "games"
            write_package(games, phase6_config())
            with override_settings(
                QUIZ_GAMES_ROOT=games,
                QUIZ_SNAPSHOT_ROOT=root / "snapshots",
            ):
                staged = stage_snapshot("phase6")
                run = Run.objects.create(
                    global_state="ADVENT_QUIZ",
                    package_id="phase6",
                    snapshot_path=staged.path,
                    snapshot_digest=staged.digest,
                    gameplay_elapsed_ms=0,
                    advent_clock_anchor=None,
                )
                challenge = Challenge.objects.create(
                    run=run,
                    initiator_team_id="a",
                    challenged_team_id="b",
                    question_id="challenge-a",
                    paid_cost=0,
                    started_gameplay_ms=0,
                )
                url = reverse(
                    "challenge_media",
                    kwargs={
                        "run_id": run.pk,
                        "challenge_id": challenge.pk,
                        "asset_path": "challenge/a.png",
                    },
                )
                self.client.force_login(team_user)
                self.assertEqual(self.client.get(url).status_code, 404)

                Run.objects.filter(pk=run.pk).update(gameplay_elapsed_ms=30_000)
                revealed = self.client.get(url)
                self.assertEqual(revealed.status_code, 200)
                self.assertEqual(
                    b"".join(revealed.streaming_content), b"challenge-media-a"
                )

                Run.objects.filter(pk=run.pk).update(
                    global_state="PAUSED",
                    pause_resume_target="ADVENT_QUIZ",
                )
                paused = self.client.get(url)
                self.assertEqual(paused.status_code, 200)
                self.assertEqual(
                    b"".join(paused.streaming_content), b"challenge-media-a"
                )

                self.client.force_login(admin_user)
                self.assertEqual(self.client.get(url).status_code, 200)
                self.client.logout()
                self.assertEqual(self.client.get(url).status_code, 404)

                Run.objects.filter(pk=run.pk).update(
                    global_state="ADVENT_QUIZ",
                    pause_resume_target=None,
                )
                self.client.force_login(team_user)
                resumed = self.client.get(url)
                self.assertEqual(resumed.status_code, 200)
                self.assertEqual(
                    b"".join(resumed.streaming_content), b"challenge-media-a"
                )

    def test_wrong_run_question_or_initiator_slot_never_authorizes_media(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            games = root / "games"
            write_package(games, phase6_config())
            with override_settings(
                QUIZ_GAMES_ROOT=games,
                QUIZ_SNAPSHOT_ROOT=root / "snapshots",
            ):
                staged = stage_snapshot("phase6")
                run = Run.objects.create(
                    global_state="ADVENT_QUIZ",
                    package_id="phase6",
                    snapshot_path=staged.path,
                    snapshot_digest=staged.digest,
                )
                other_run = Run.objects.create(
                    active=False,
                    global_state="ADVENT_QUIZ",
                    package_id="phase6-history",
                    snapshot_path=staged.path,
                    snapshot_digest=staged.digest,
                )
                challenge = Challenge.objects.create(
                    run=run,
                    initiator_team_id="a",
                    challenged_team_id="b",
                    question_id="challenge-a",
                    paid_cost=0,
                    started_gameplay_ms=0,
                )

                self.assertIsNone(
                    snapshot_challenge_media_path(
                        other_run,
                        challenge,
                        actor_role="admin",
                        actor_team_id=None,
                        relative_path="challenge/a.png",
                    )
                )
                self.assertIsNone(
                    snapshot_challenge_media_path(
                        run,
                        challenge,
                        actor_role="admin",
                        actor_team_id=None,
                        relative_path="challenge/b.png",
                    )
                )
                challenge.question_id = "fabricated-question"
                self.assertIsNone(
                    snapshot_challenge_media_path(
                        run,
                        challenge,
                        actor_role="admin",
                        actor_team_id=None,
                        relative_path="challenge/a.png",
                    )
                )
