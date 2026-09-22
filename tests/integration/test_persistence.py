"""Focused database and snapshot safety tests for the first slice."""

import json
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection
from django.test import TestCase, override_settings

from quiz.configuration import InvalidPackage, load_snapshot, stage_snapshot
from quiz.models import AuditEvent, Run, TeamRun
from quiz.persistence import immediate_transaction, read_snapshot


def demo_package(root, media=False):
    package = root / "demo"
    package.mkdir()
    if media:
        (package / "a.txt").write_text("private")
    def puzzles(prefix):
        return [
            {
                "id": f"{prefix}-{number}",
                "number": number,
                "title": f"Puzzle {number}",
                "body": "Clue",
                "validator": {"type": "text_exact", "answer": "secret"},
                "reward_points": 1,
                "hint": None,
                "fragment": None,
                "media": ["a.txt"] if media and number == 1 else [],
            }
            for number in (1, 2)
        ]
    config = {
        "schema_version": 1,
        "package_id": "demo",
        "initial_points": 3,
        "teams": {"a": {"puzzles": puzzles("a")}, "b": {"puzzles": puzzles("b")}},
    }
    (package / "game.json").write_text(json.dumps(config))
    return package


class PersistenceTests(TestCase):
    def test_sqlite_policy_and_nested_transactions(self):
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA foreign_keys")
            self.assertEqual(cursor.fetchone()[0], 1)
            cursor.execute("PRAGMA busy_timeout")
            self.assertGreaterEqual(cursor.fetchone()[0], 1000)
        with immediate_transaction():
            with immediate_transaction():
                self.assertTrue(connection.connection.in_transaction)
            with read_snapshot():
                self.assertTrue(connection.connection.in_transaction)

    def test_nonnegative_balance_and_one_active_run(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Run.objects.create(
                global_state="ADVENT_QUIZ",
                package_id="demo",
                snapshot_path=temp,
                snapshot_digest="a" * 64,
            )
            with self.assertRaises(IntegrityError):
                with immediate_transaction():
                    TeamRun.objects.create(
                        run=run, team_id="a", activity_state="PUZZLE", points=-1
                    )
            with self.assertRaises(IntegrityError):
                with immediate_transaction():
                    Run.objects.create(
                        global_state="ADVENT_QUIZ",
                        package_id="demo",
                        snapshot_path=temp,
                        snapshot_digest="b" * 64,
                    )

    def test_snapshot_survives_source_change_and_detects_tampering(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            games = root / "games"
            games.mkdir()
            package = demo_package(games, media=True)
            snapshots = root / "snapshots"
            with override_settings(QUIZ_GAMES_ROOT=games, QUIZ_SNAPSHOT_ROOT=snapshots):
                staged = stage_snapshot("demo")
                run = Run.objects.create(
                    global_state="ADVENT_QUIZ",
                    package_id="demo",
                    snapshot_path=staged.path,
                    snapshot_digest=staged.digest,
                )
                (package / "a.txt").write_text("changed source")
                (package / "game.json").unlink()
                self.assertEqual(
                    load_snapshot(run)["teams"]["a"]["puzzles"][0]["body"], "Clue"
                )
                (Path(staged.path) / "media" / "a.txt").write_text("tampered")
                with self.assertRaises(InvalidPackage):
                    load_snapshot(run)

    def test_event_save_and_delete_are_immutable(self):
        with tempfile.TemporaryDirectory() as temp:
            User = get_user_model()
            actor = User.objects.create_user("admin-one", password="secret")
            run = Run.objects.create(
                global_state="ADVENT_QUIZ",
                package_id="demo",
                snapshot_path=temp,
                snapshot_digest="a" * 64,
            )
            import uuid

            event = AuditEvent.objects.create(
                run=run,
                request_id=uuid.uuid4(),
                actor=actor,
                actor_role="admin",
                action="start",
                result="accepted",
            )
            event.result = "changed"
            with self.assertRaises(ValueError):
                event.save()
            with self.assertRaises(ValueError):
                event.delete()
