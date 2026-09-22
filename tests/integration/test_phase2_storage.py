"""Focused phase-2 storage and immutable configuration checks."""

import json
import tempfile
import uuid
from pathlib import Path

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase, override_settings

from quiz.configuration import InvalidPackage, load_snapshot, stage_snapshot
from quiz.models import CommandReceipt, HintReveal, Run, TeamRun
from quiz.persistence import immediate_transaction


class PhaseTwoStorageTests(TestCase):
    def setUp(self):
        self.actor = get_user_model().objects.create_user(
            "phase2-admin", password="secret"
        )
        self.run = Run.objects.create(
            global_state="READY",
            package_id="demo",
            snapshot_path="/tmp/unused",
            snapshot_digest="a" * 64,
        )

    def test_hint_inventory_cannot_be_negative(self):
        with self.assertRaises(IntegrityError):
            with immediate_transaction():
                TeamRun.objects.create(
                    run=self.run, team_id="a", activity_state="READY", hint_tokens=-1
                )

    def test_one_reveal_per_run_team_puzzle(self):
        fields = dict(
            run=self.run,
            team_id="a",
            puzzle_id="a-1",
            actor=self.actor,
            request_id=uuid.uuid4(),
            source="player",
        )
        HintReveal.objects.create(**fields)
        with self.assertRaises(IntegrityError):
            with immediate_transaction():
                HintReveal.objects.create(
                    **{**fields, "source": "admin", "request_id": uuid.uuid4()}
                )
        HintReveal.objects.create(**{**fields, "team_id": "b", "source": "admin"})

    def test_command_request_id_cannot_be_reused_by_same_actor(self):
        fields = dict(
            run=self.run,
            actor=self.actor,
            request_id=uuid.uuid4(),
            action="purchase_hint",
            payload_digest="a" * 64,
            result={"outcome": "purchased"},
        )
        CommandReceipt.objects.create(**fields)
        with self.assertRaises(IntegrityError):
            with immediate_transaction():
                CommandReceipt.objects.create(**{**fields, "action": "skip"})

    def test_v2_prices_are_pinned_and_invalid_costs_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "demo"
            package.mkdir()
            def puzzle(team, number):
                return {
                    "id": f"{team}-{number}",
                    "number": number,
                    "title": "Puzzle",
                    "body": "Clue",
                    "validator": {"type": "text_exact", "answer": "secret"},
                    "reward_points": 0,
                    "hint": "private hint",
                    "fragment": None,
                    "media": [],
                }
            config = {
                "schema_version": 2,
                "package_id": "demo",
                "initial_points": 3,
                "hint_cost": 2,
                "skip_cost": 5,
                "teams": {
                    team: {"puzzles": [puzzle(team, 1), puzzle(team, 2)]}
                    for team in ("a", "b")
                },
            }
            game_file = package / "game.json"
            game_file.write_text(json.dumps(config))
            with override_settings(
                QUIZ_GAMES_ROOT=root, QUIZ_SNAPSHOT_ROOT=root / "snapshots"
            ):
                snapshot = stage_snapshot("demo")
                config["hint_cost"] = 99
                game_file.write_text(json.dumps(config))
                self.assertEqual(load_snapshot(snapshot.path)["hint_cost"], 2)
                config["hint_cost"] = -1
                game_file.write_text(json.dumps(config))
                with self.assertRaises(InvalidPackage):
                    stage_snapshot("demo")
                config["hint_cost"] = True
                game_file.write_text(json.dumps(config))
                with self.assertRaises(InvalidPackage):
                    stage_snapshot("demo")
                del config["hint_cost"]
                game_file.write_text(json.dumps(config))
                with self.assertRaises(InvalidPackage):
                    stage_snapshot("demo")
