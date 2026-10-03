"""Issue #63 snapshot verification lifecycle and hot-path regressions."""

import json
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, Lock
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from quiz import configuration
from quiz.configuration import (
    InvalidPackage,
    load_snapshot,
    snapshot_media_path,
    stage_snapshot,
)


def _puzzle(team_id, number, media=None):
    return {
        "id": f"{team_id}-{number}",
        "number": number,
        "title": f"Puzzle {number}",
        "body": "Clue",
        "validator": {"type": "text_exact", "answer": "secret"},
        "reward_points": 1,
        "hint": None,
        "fragment": None,
        "media": media or [],
    }


def _write_package(games_root):
    package_id = "snapshot-cache"
    package = games_root / package_id
    package.mkdir(parents=True)
    config = {
        "schema_version": 3,
        "package_id": package_id,
        "initial_points": 3,
        "hint_cost": 1,
        "skip_cost": 2,
        "freeze_cost": 3,
        "uno_reverse_cost": 4,
        "teams": {
            "a": {
                "puzzles": [
                    _puzzle("a", 1, ["a/clue.bin", "a/other.bin"]),
                    _puzzle("a", 2),
                ]
            },
            "b": {"puzzles": [_puzzle("b", 1), _puzzle("b", 2)]},
        },
    }
    (package / "game.json").write_text(json.dumps(config))
    (package / "a").mkdir()
    (package / "a" / "clue.bin").write_bytes(b"current-clue")
    (package / "a" / "other.bin").write_bytes(b"unrelated-media")
    return package_id


class SnapshotVerificationLifecycleTests(SimpleTestCase):
    def setUp(self):
        configuration._reset_snapshot_cache()
        self.runtime = tempfile.TemporaryDirectory()
        self.addCleanup(self.runtime.cleanup)
        self.addCleanup(configuration._reset_snapshot_cache)
        root = Path(self.runtime.name)
        self.games = root / "games"
        self.games.mkdir()
        self.snapshots = root / "snapshots"
        package_id = _write_package(self.games)
        self.settings = override_settings(
            QUIZ_GAMES_ROOT=self.games,
            QUIZ_SNAPSHOT_ROOT=self.snapshots,
        )
        self.settings.enable()
        self.addCleanup(self.settings.disable)
        staged = stage_snapshot(package_id)
        self.run = SimpleNamespace(
            snapshot_path=staged.path,
            snapshot_digest=staged.digest,
        )
        self.snapshot = Path(staged.path)

    def test_warm_load_skips_media_hashing_and_returns_independent_config(self):
        original_digest = configuration._file_digest
        with patch.object(
            configuration,
            "_file_digest",
            wraps=original_digest,
        ) as cold_digest:
            first = load_snapshot(self.run)

        self.assertEqual(cold_digest.call_count, 2)
        first["teams"]["a"]["puzzles"][0]["title"] = "mutated caller copy"

        with patch.object(
            configuration,
            "_file_digest",
            wraps=original_digest,
        ) as warm_digest:
            second = load_snapshot(self.run)

        warm_digest.assert_not_called()
        self.assertEqual(second["teams"]["a"]["puzzles"][0]["title"], "Puzzle 1")

    def test_concurrent_cold_load_single_flights_full_verification(self):
        configuration._reset_snapshot_cache()
        original_verify = configuration._verify_snapshot
        entered = Event()
        release = Event()
        count_lock = Lock()
        verify_count = 0

        def controlled_verify(path, expected):
            nonlocal verify_count
            with count_lock:
                verify_count += 1
            entered.set()
            release.wait(timeout=2)
            return original_verify(path, expected)

        with patch.object(
            configuration,
            "_verify_snapshot",
            side_effect=controlled_verify,
        ):
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = [pool.submit(load_snapshot, self.run) for _ in range(4)]
                self.assertTrue(entered.wait(timeout=1))
                release.set()
                results = [future.result(timeout=2) for future in futures]

        self.assertEqual(verify_count, 1)
        self.assertTrue(
            all(result["package_id"] == "snapshot-cache" for result in results)
        )

    def test_restart_reverification_detects_unrequested_media_corruption(self):
        load_snapshot(self.run)
        other = self.snapshot / "media" / "a" / "other.bin"
        other.write_bytes(b"tampered-after-warm-verification")

        self.assertEqual(load_snapshot(self.run)["package_id"], "snapshot-cache")

        configuration._reset_snapshot_cache()
        with self.assertRaisesRegex(InvalidPackage, "Snapshot content changed"):
            load_snapshot(self.run)

    def test_media_request_hashes_only_requested_file_and_rejects_tampering(self):
        load_snapshot(self.run)
        original_digest = configuration._file_digest
        expected_path = self.snapshot / "media" / "a" / "clue.bin"

        with patch.object(
            configuration,
            "_file_digest",
            wraps=original_digest,
        ) as requested_digest:
            path = snapshot_media_path(self.run, "a", "a/clue.bin")

        self.assertEqual(path, expected_path)
        requested_digest.assert_called_once_with(expected_path)

        expected_path.write_bytes(b"tampered-requested-file")
        self.assertIsNone(snapshot_media_path(self.run, "a", "a/clue.bin"))
