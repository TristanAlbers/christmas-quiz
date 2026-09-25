"""Challenge snapshot media authorization and context isolation."""

from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

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
                    question_id="shared-challenge",
                    paid_cost=7,
                )

                participant = snapshot_challenge_media_path(
                    run,
                    challenge,
                    actor_role="team",
                    actor_team_id="a",
                    relative_path="challenge/clue.png",
                )
                admin = snapshot_challenge_media_path(
                    run,
                    challenge,
                    actor_role="admin",
                    actor_team_id=None,
                    relative_path="challenge/clue.png",
                )
                denied = (
                    snapshot_challenge_media_path(
                        run,
                        challenge,
                        actor_role="team",
                        actor_team_id=None,
                        relative_path="challenge/clue.png",
                    ),
                    snapshot_challenge_media_path(
                        run,
                        challenge,
                        actor_role="public",
                        actor_team_id=None,
                        relative_path="challenge/clue.png",
                    ),
                    snapshot_challenge_media_path(
                        run,
                        challenge,
                        actor_role="team",
                        actor_team_id="a",
                        relative_path="a-1.png",
                    ),
                )

                self.assertEqual(participant.read_bytes(), b"challenge-media")
                self.assertEqual(admin.read_bytes(), b"challenge-media")
                self.assertEqual(denied, (None, None, None))

                run.global_state = "PAUSED"
                self.assertIsNone(
                    snapshot_challenge_media_path(
                        run,
                        challenge,
                        actor_role="team",
                        actor_team_id="a",
                        relative_path="challenge/clue.png",
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
                        relative_path="challenge/clue.png",
                    )
                )

    def test_wrong_run_and_question_never_authorize_media(self):
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
                    question_id="shared-challenge",
                    paid_cost=7,
                )

                self.assertIsNone(
                    snapshot_challenge_media_path(
                        other_run,
                        challenge,
                        actor_role="admin",
                        actor_team_id=None,
                        relative_path="challenge/clue.png",
                    )
                )
                challenge.question_id = "fabricated-question"
                self.assertIsNone(
                    snapshot_challenge_media_path(
                        run,
                        challenge,
                        actor_role="admin",
                        actor_team_id=None,
                        relative_path="challenge/clue.png",
                    )
                )
