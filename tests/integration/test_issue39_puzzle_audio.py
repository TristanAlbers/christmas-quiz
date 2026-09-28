"""Focused package/snapshot coverage for issue #39 typed Advent media."""

import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.test import SimpleTestCase, override_settings

from quiz.configuration import InvalidPackage, load_snapshot, stage_snapshot


class TypedPuzzleMediaSnapshotTests(SimpleTestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.games = self.root / "games"
        self.package = self.games / "christmas-2026-demo"
        shutil.copytree(settings.BASE_DIR / "games" / "christmas-2026-demo", self.package)
        self.snapshot_root = self.root / "snapshots"
        scope = override_settings(
            QUIZ_GAMES_ROOT=self.games,
            QUIZ_SNAPSHOT_ROOT=self.snapshot_root,
        )
        scope.enable()
        self.addCleanup(scope.disable)

    def _config(self):
        return json.loads((self.package / "game.json").read_text())

    def _write_config(self, config):
        (self.package / "game.json").write_text(json.dumps(config))

    def test_mixed_typed_media_is_snapshotted_and_legacy_strings_remain_images(self):
        audio = self.package / "a" / "clue.mp3"
        audio.write_bytes(b"ID3-private-audio-v1")
        config = self._config()
        config["teams"]["a"]["puzzles"][0]["media"] = [
            {"type": "image", "path": "a/star.png", "alt": "Rode ster"},
            {"type": "audio", "path": "a/clue.mp3"},
        ]
        self._write_config(config)

        staged = stage_snapshot("christmas-2026-demo")
        snapshot = load_snapshot(staged.path)

        self.assertEqual(
            snapshot["teams"]["a"]["puzzles"][0]["media"],
            config["teams"]["a"]["puzzles"][0]["media"],
        )
        self.assertEqual(
            snapshot["teams"]["b"]["puzzles"][0]["media"],
            ["b/sky.png"],
        )
        pinned_audio = Path(staged.path) / "media" / "a" / "clue.mp3"
        self.assertEqual(pinned_audio.read_bytes(), b"ID3-private-audio-v1")

        audio.write_bytes(b"ID3-source-edited-after-start")
        self.assertEqual(pinned_audio.read_bytes(), b"ID3-private-audio-v1")

    def test_unknown_typed_media_kind_is_rejected(self):
        config = self._config()
        config["teams"]["a"]["puzzles"][0]["media"] = [
            {"type": "video", "path": "a/star.png"}
        ]
        self._write_config(config)

        with self.assertRaisesRegex(InvalidPackage, "image or audio"):
            stage_snapshot("christmas-2026-demo")

    def test_audio_entry_rejects_presentation_fields_not_in_contract(self):
        config = self._config()
        config["teams"]["a"]["puzzles"][0]["media"] = [
            {"type": "audio", "path": "a/star.png", "alt": "Niet toegestaan"}
        ]
        self._write_config(config)

        with self.assertRaisesRegex(InvalidPackage, "Invalid audio media entry"):
            stage_snapshot("christmas-2026-demo")

    def test_image_alt_must_be_nonempty_when_supplied(self):
        config = self._config()
        config["teams"]["a"]["puzzles"][0]["media"] = [
            {"type": "image", "path": "a/star.png", "alt": "   "}
        ]
        self._write_config(config)

        with self.assertRaisesRegex(InvalidPackage, "alt must be nonempty"):
            stage_snapshot("christmas-2026-demo")
