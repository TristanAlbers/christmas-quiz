"""Validate a data-only package and pin its JSON and media for a run."""

import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from django.conf import settings


class InvalidPackage(ValueError):
    pass


@dataclass(frozen=True)
class StagedSnapshot:
    path: str
    digest: str
    config: dict


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


def _relative_path(value):
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise InvalidPackage("Invalid media path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in (".", "..", "") for part in value.split("/")):
        raise InvalidPackage("Invalid media path")
    return path


def _validate(config, package_id):
    if not isinstance(config, dict):
        raise InvalidPackage("Invalid package top level")
    common_keys = {
        "schema_version",
        "package_id",
        "initial_points",
        "teams",
    }
    version = config.get("schema_version")
    required_keys = common_keys | (
        {"hint_cost", "skip_cost"} if version == 2 else set()
    )
    if (
        type(version) is not int
        or version not in (1, 2)
        or set(config) != required_keys
    ):
        raise InvalidPackage("Invalid package top level")
    if config["package_id"] != package_id:
        raise InvalidPackage("Unsupported schema or mismatched package ID")
    points = config["initial_points"]
    if type(points) is not int or points < 0:
        raise InvalidPackage("initial_points must be nonnegative integer")
    if version == 2:
        for key in ("hint_cost", "skip_cost"):
            if type(config[key]) is not int or config[key] < 0:
                raise InvalidPackage(f"{key} must be nonnegative integer")
    teams = config["teams"]
    if not isinstance(teams, dict) or set(teams) != {"a", "b"}:
        raise InvalidPackage("Exactly teams a and b are required")
    referenced = set()
    for team_id in ("a", "b"):
        team = teams[team_id]
        if not isinstance(team, dict) or set(team) != {"puzzles"}:
            raise InvalidPackage("Invalid team entry")
        puzzles = team["puzzles"]
        if not isinstance(puzzles, list) or len(puzzles) < 2 or len(puzzles) > 25:
            raise InvalidPackage("Each team needs 2 to 25 puzzles")
        seen_ids = set()
        for number, puzzle in enumerate(puzzles, 1):
            if not isinstance(puzzle, dict) or set(puzzle) != {
                "id",
                "number",
                "title",
                "body",
                "validator",
                "reward_points",
                "hint",
                "fragment",
                "media",
            }:
                raise InvalidPackage("Invalid puzzle entry")
            puzzle_id = puzzle["id"]
            if not isinstance(puzzle_id, str) or not re.fullmatch(
                r"[a-zA-Z0-9_-]{1,100}", puzzle_id
            ):
                raise InvalidPackage("Invalid puzzle ID")
            if (
                puzzle_id in seen_ids
                or type(puzzle["number"]) is not int
                or puzzle["number"] != number
            ):
                raise InvalidPackage("Puzzle IDs and sequential numbers must be unique")
            seen_ids.add(puzzle_id)
            for key in ("title", "body"):
                if not isinstance(puzzle[key], str) or not puzzle[key].strip():
                    raise InvalidPackage(f"{key} must be nonempty text")
            validator = puzzle["validator"]
            if not isinstance(validator, dict) or set(validator) != {"type", "answer"}:
                raise InvalidPackage("Invalid validator")
            if validator["type"] not in ("text_exact", "number_exact"):
                raise InvalidPackage("Unknown validator")
            if (
                not isinstance(validator["answer"], str)
                or not validator["answer"].strip()
            ):
                raise InvalidPackage("Validator answer must be nonempty text")
            reward = puzzle["reward_points"]
            if type(reward) is not int or reward < 0:
                raise InvalidPackage("reward_points must be nonnegative integer")
            for key in ("hint", "fragment"):
                if puzzle[key] is not None and not isinstance(puzzle[key], str):
                    raise InvalidPackage(f"{key} must be text or null")
            media = puzzle["media"]
            if not isinstance(media, list):
                raise InvalidPackage("media must be a list")
            for item in media:
                referenced.add(str(_relative_path(item)))
    return referenced


def _root(setting, fallback):
    return Path(
        getattr(settings, setting, Path(settings.BASE_DIR) / fallback)
    ).resolve()


def stage_snapshot(package_id):
    """Do filesystem validation/copy before the short Start write transaction."""
    if not isinstance(package_id, str) or not re.fullmatch(
        r"[a-zA-Z0-9_-]{1,100}", package_id
    ):
        raise InvalidPackage("Invalid package ID")
    games_root = _root("QUIZ_GAMES_ROOT", "games")
    source = games_root / package_id
    if source.is_symlink() or not source.is_dir():
        raise InvalidPackage("Package does not exist")
    if (source / "game.json").is_symlink():
        raise InvalidPackage("Symlink package JSON is forbidden")
    try:
        raw = (source / "game.json").read_bytes()
        if len(raw) > 2_000_000:
            raise InvalidPackage("Package JSON is too large")
        config = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InvalidPackage("Cannot read package JSON") from exc
    referenced = _validate(config, package_id)
    snapshot_root = _root("QUIZ_SNAPSHOT_ROOT", "var/snapshots")
    snapshot_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=snapshot_root))
    try:
        config_bytes = _canonical(config)
        (staging / "game.json").write_bytes(config_bytes)
        hashes = {"game.json": _digest(config_bytes)}
        for rel in sorted(referenced):
            source_asset = source / rel
            if any(
                part.is_symlink()
                for part in (source_asset, *source_asset.parents)
                if part != source.parent
            ):
                raise InvalidPackage("Symlink media is forbidden")
            if not source_asset.is_file() or source_asset.stat().st_size > 20_000_000:
                raise InvalidPackage("Missing or oversized media")
            target = staging / "media" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_asset, target)
            hashes[f"media/{rel}"] = _digest(target.read_bytes())
        manifest_bytes = _canonical({"schema_version": 1, "files": hashes})
        (staging / "manifest.json").write_bytes(manifest_bytes)
        digest = _digest(manifest_bytes)
        destination = snapshot_root / f"{package_id}-{os.urandom(16).hex()}"
        os.replace(staging, destination)
        return StagedSnapshot(str(destination), digest, config)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def load_snapshot(run_or_path):
    """Verify the pinned manifest and every referenced byte before using rules."""
    original = Path(getattr(run_or_path, "snapshot_path", run_or_path))
    if original.is_symlink():
        raise InvalidPackage("Snapshot path is a symlink")
    path = original.resolve()
    root = _root("QUIZ_SNAPSHOT_ROOT", "var/snapshots")
    if path.parent != root:
        raise InvalidPackage("Snapshot path is outside the snapshot root")
    try:
        manifest_bytes = (path / "manifest.json").read_bytes()
        expected = getattr(run_or_path, "snapshot_digest", _digest(manifest_bytes))
        if _digest(manifest_bytes) != expected:
            raise InvalidPackage("Snapshot manifest changed")
        manifest = json.loads(manifest_bytes)
        if manifest.get("schema_version") != 1 or not isinstance(
            manifest.get("files"), dict
        ):
            raise InvalidPackage("Invalid snapshot manifest")
        for rel, digest in manifest["files"].items():
            _relative_path(rel)
            target = path / rel
            if target.is_symlink() or _digest(target.read_bytes()) != digest:
                raise InvalidPackage("Snapshot content changed")
        config = json.loads((path / "game.json").read_bytes())
        if not isinstance(config, dict):
            raise InvalidPackage("Invalid snapshot config")
        _validate(config, config.get("package_id"))
        return config
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InvalidPackage("Cannot read snapshot") from exc


def snapshot_media_path(run, team_id, relative_path):
    """Return a declared asset only after the caller has authorized this team."""
    try:
        rel = str(_relative_path(relative_path))
        config = load_snapshot(run)
    except InvalidPackage:
        return None
    if team_id not in ("a", "b"):
        return None
    declared = {
        media
        for puzzle in config["teams"][team_id]["puzzles"]
        for media in puzzle["media"]
    }
    if rel not in declared:
        return None
    return Path(run.snapshot_path) / "media" / rel
