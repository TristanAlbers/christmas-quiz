"""Validate a data-only package and pin its JSON and media for a run."""

import hashlib
import json
import os
import re
import shutil
import tempfile
from collections import OrderedDict
from concurrent.futures import Future
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from threading import Lock
from types import MappingProxyType

from django.conf import settings


class InvalidPackage(ValueError):
    pass


@dataclass(frozen=True)
class DiscoveredPackage:
    package_id: str
    startable: bool
    diagnostic: str | None = None


@dataclass(frozen=True)
class StagedSnapshot:
    path: str
    digest: str
    config: dict


@dataclass(frozen=True)
class _VerifiedSnapshot:
    path: Path
    config_bytes: bytes
    files: MappingProxyType


_VERIFIED_SNAPSHOT_CACHE_MAX = 8
_verified_snapshot_cache = OrderedDict()
_snapshot_verification_flights = {}
_snapshot_cache_lock = Lock()


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _file_digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


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


def puzzle_media_descriptor(item):
    """Normalize legacy image paths and explicitly typed Advent puzzle media."""
    if isinstance(item, str):
        return {"type": "image", "path": str(_relative_path(item)), "alt": None}
    if not isinstance(item, dict):
        raise InvalidPackage("Puzzle media entries must be paths or typed objects")

    media_type = item.get("type")
    if media_type == "image":
        if set(item) not in ({"type", "path"}, {"type", "path", "alt"}):
            raise InvalidPackage("Invalid image media entry")
        alt = item.get("alt")
        if alt is not None and (not isinstance(alt, str) or not alt.strip()):
            raise InvalidPackage("Image media alt must be nonempty text or omitted")
        return {
            "type": "image",
            "path": str(_relative_path(item.get("path"))),
            "alt": alt.strip() if alt is not None else None,
        }
    if media_type == "audio":
        if set(item) != {"type", "path"}:
            raise InvalidPackage("Invalid audio media entry")
        return {
            "type": "audio",
            "path": str(_relative_path(item.get("path"))),
            "alt": None,
        }
    raise InvalidPackage("Puzzle media type must be image or audio")


def puzzle_media_paths(puzzle):
    """Return validated declared paths for one normal Advent puzzle."""
    media = puzzle.get("media")
    if not isinstance(media, list):
        raise InvalidPackage("media must be a list")
    return tuple(puzzle_media_descriptor(item)["path"] for item in media)


def _validate_challenge_puzzle(puzzle, team_id, referenced):
    if not isinstance(puzzle, dict) or set(puzzle) != {
        "id",
        "title",
        "body",
        "validator",
        "media",
    }:
        raise InvalidPackage(f"Invalid Challenge puzzle entry for team {team_id}")
    puzzle_id = puzzle["id"]
    if not isinstance(puzzle_id, str) or not re.fullmatch(
        r"[a-zA-Z0-9_-]{1,100}", puzzle_id
    ):
        raise InvalidPackage("Invalid Challenge puzzle ID")
    for key in ("title", "body"):
        if not isinstance(puzzle[key], str) or not puzzle[key].strip():
            raise InvalidPackage(f"Challenge {key} must be nonempty text")
    validator = puzzle["validator"]
    if not isinstance(validator, dict) or set(validator) != {"type", "answer"}:
        raise InvalidPackage("Invalid Challenge validator")
    if validator["type"] not in ("text_exact", "number_exact"):
        raise InvalidPackage("Unknown Challenge validator")
    if not isinstance(validator["answer"], str) or not validator["answer"].strip():
        raise InvalidPackage("Challenge validator answer must be nonempty text")
    if validator["type"] == "number_exact":
        try:
            expected = Decimal(validator["answer"].strip())
        except InvalidOperation as exc:
            raise InvalidPackage(
                "Challenge numeric validator answer must be a finite decimal"
            ) from exc
        if not expected.is_finite():
            raise InvalidPackage(
                "Challenge numeric validator answer must be a finite decimal"
            )
    media = puzzle["media"]
    if not isinstance(media, list):
        raise InvalidPackage("Challenge media must be a list")
    normalized_media = []
    for item in media:
        rel = str(_relative_path(item))
        referenced.add(rel)
        normalized_media.append(rel)
    fingerprint = (
        puzzle["title"].strip(),
        puzzle["body"].strip(),
        validator["type"],
        validator["answer"].strip(),
        tuple(normalized_media),
    )
    return puzzle_id, fingerprint


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
    music_keys = {
        "hint_cost",
        "skip_cost",
        "freeze_cost",
        "uno_reverse_cost",
        "music_question_reward",
        "music_score_display_duration_ms",
        "music_questions",
    }
    challenge_keys = {"challenge_cost", "challenge_puzzles"}
    versioned_keys = {
        1: set(),
        2: {"hint_cost", "skip_cost"},
        3: {"hint_cost", "skip_cost", "freeze_cost", "uno_reverse_cost"},
        4: music_keys,
        5: music_keys,
        6: music_keys | challenge_keys,
    }
    required_keys = common_keys | versioned_keys.get(version, set())
    if (
        type(version) is not int
        or version not in versioned_keys
        or set(config) != required_keys
    ):
        raise InvalidPackage("Invalid package top level")
    if config["package_id"] != package_id:
        raise InvalidPackage("Unsupported schema or mismatched package ID")
    points = config["initial_points"]
    if type(points) is not int or points < 0:
        raise InvalidPackage("initial_points must be nonnegative integer")
    if version in (2, 3, 4, 5, 6):
        price_keys = ["hint_cost", "skip_cost"]
        if version in (3, 4, 5, 6):
            price_keys.extend(["freeze_cost", "uno_reverse_cost"])
        if version == 6:
            price_keys.append("challenge_cost")
        for key in price_keys:
            if type(config[key]) is not int or config[key] < 0:
                raise InvalidPackage(f"{key} must be nonnegative integer")
    if version == 6 and config["challenge_cost"] != 0:
        raise InvalidPackage("challenge_cost must be 0 because Challenge is free")
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
        if version in (5, 6) and len(puzzles) != 25:
            raise InvalidPackage(
                f"Schema v{version} requires exactly 25 puzzles per team"
            )
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
                referenced.add(puzzle_media_descriptor(item)["path"])
    if version in (4, 5, 6):
        reward = config["music_question_reward"]
        if type(reward) is not int or reward < 0:
            raise InvalidPackage("music_question_reward must be nonnegative integer")
        display_ms = config["music_score_display_duration_ms"]
        if type(display_ms) is not int or display_ms <= 0:
            raise InvalidPackage(
                "music_score_display_duration_ms must be positive integer"
            )
        questions = config["music_questions"]
        if not isinstance(questions, list) or len(questions) != 11:
            raise InvalidPackage("Exactly 11 Music questions are required")
        seen_music_ids = set()
        for number, question in enumerate(questions, 1):
            if (
                not isinstance(question, dict)
                or not set(question).issubset(
                    {"id", "number", "title", "body", "validator", "audio"}
                )
                or set(question) - {"audio"}
                != {"id", "number", "title", "body", "validator"}
            ):
                raise InvalidPackage("Invalid Music question entry")
            question_id = question["id"]
            if not isinstance(question_id, str) or not re.fullmatch(
                r"[a-zA-Z0-9_-]{1,100}", question_id
            ):
                raise InvalidPackage("Invalid Music question ID")
            if (
                question_id in seen_music_ids
                or type(question["number"]) is not int
                or question["number"] != number
            ):
                raise InvalidPackage(
                    "Music question IDs and sequential numbers must be unique"
                )
            seen_music_ids.add(question_id)
            for key in ("title", "body"):
                if not isinstance(question[key], str) or not question[key].strip():
                    raise InvalidPackage(f"Music {key} must be nonempty text")
            validator = question["validator"]
            if not isinstance(validator, dict) or set(validator) != {"type", "answer"}:
                raise InvalidPackage("Invalid Music validator")
            if validator["type"] not in ("text_exact", "number_exact"):
                raise InvalidPackage("Unknown Music validator")
            if (
                not isinstance(validator["answer"], str)
                or not validator["answer"].strip()
            ):
                raise InvalidPackage("Music validator answer must be nonempty text")
            audio = question.get("audio")
            if audio is not None:
                referenced.add(str(_relative_path(audio)))
    if version == 6:
        challenge_puzzles = config["challenge_puzzles"]
        if (
            not isinstance(challenge_puzzles, dict)
            or set(challenge_puzzles) != {"a", "b"}
        ):
            raise InvalidPackage(
                "Challenge requires distinct puzzles for initiators a and b"
            )
        challenge_a = _validate_challenge_puzzle(
            challenge_puzzles["a"], "a", referenced
        )
        challenge_b = _validate_challenge_puzzle(
            challenge_puzzles["b"], "b", referenced
        )
        if challenge_a[0] == challenge_b[0]:
            raise InvalidPackage("Challenge puzzle IDs must be distinct")
        if challenge_a[1] == challenge_b[1]:
            raise InvalidPackage("Challenge puzzles must be different")
    return referenced


def _root(setting, fallback):
    return Path(
        getattr(settings, setting, Path(settings.BASE_DIR) / fallback)
    ).resolve()


def _source_package(package_id):
    if not isinstance(package_id, str) or not re.fullmatch(
        r"[a-zA-Z0-9_-]{1,100}", package_id
    ):
        raise InvalidPackage("Directory name must be a 1-100 character package ID")
    games_root = _root("QUIZ_GAMES_ROOT", "games")
    source = games_root / package_id
    if source.is_symlink() or not source.is_dir():
        raise InvalidPackage("Package directory is missing or is a symlink")
    if (source / "game.json").is_symlink():
        raise InvalidPackage("game.json must be a regular file, not a symlink")
    try:
        raw = (source / "game.json").read_bytes()
        if len(raw) > 2_000_000:
            raise InvalidPackage("game.json exceeds the 2 MB limit")
        config = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InvalidPackage(
            "game.json is missing, unreadable, or invalid JSON"
        ) from exc
    referenced = _validate(config, package_id)
    return source, config, referenced


def _validate_source_media(source, referenced):
    for rel in sorted(referenced):
        source_asset = source / rel
        if any(
            part.is_symlink()
            for part in (source_asset, *source_asset.parents)
            if part != source.parent
        ):
            raise InvalidPackage("Referenced media must not use symlinks")
        try:
            valid_file = source_asset.is_file()
            oversized = valid_file and source_asset.stat().st_size > 20_000_000
        except OSError as exc:
            raise InvalidPackage("Referenced media is unreadable") from exc
        if not valid_file:
            raise InvalidPackage("Referenced media file is missing")
        if oversized:
            raise InvalidPackage("Referenced media exceeds the 20 MB limit")


def discover_packages():
    """Return direct source packages without creating runs or snapshots."""
    games_root = _root("QUIZ_GAMES_ROOT", "games")
    try:
        entries = sorted(games_root.iterdir(), key=lambda entry: entry.name)
    except OSError as exc:
        raise InvalidPackage("Configured games root is missing or unreadable") from exc

    discovered = []
    for entry in entries:
        if not entry.is_dir():
            continue
        try:
            source, _, referenced = _source_package(entry.name)
            _validate_source_media(source, referenced)
        except InvalidPackage as exc:
            discovered.append(
                DiscoveredPackage(
                    package_id=entry.name,
                    startable=False,
                    diagnostic=str(exc),
                )
            )
        else:
            discovered.append(
                DiscoveredPackage(
                    package_id=entry.name,
                    startable=True,
                )
            )
    return tuple(discovered)


def stage_snapshot(package_id):
    """Do filesystem validation/copy before the short Start write transaction."""
    source, config, referenced = _source_package(package_id)
    _validate_source_media(source, referenced)
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
                raise InvalidPackage("Referenced media must not use symlinks")
            target = staging / "media" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                if not source_asset.is_file():
                    raise InvalidPackage("Referenced media file is missing")
                if source_asset.stat().st_size > 20_000_000:
                    raise InvalidPackage("Referenced media exceeds the 20 MB limit")
                shutil.copyfile(source_asset, target)
                if target.stat().st_size > 20_000_000:
                    raise InvalidPackage("Referenced media exceeds the 20 MB limit")
                hashes[f"media/{rel}"] = _file_digest(target)
            except OSError as exc:
                raise InvalidPackage(
                    "Referenced media became unreadable while staging"
                ) from exc
        manifest_bytes = _canonical({"schema_version": 1, "files": hashes})
        (staging / "manifest.json").write_bytes(manifest_bytes)
        digest = _digest(manifest_bytes)
        destination = snapshot_root / f"{package_id}-{os.urandom(16).hex()}"
        os.replace(staging, destination)
        return StagedSnapshot(str(destination), digest, config)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _snapshot_identity(run_or_path):
    original = Path(getattr(run_or_path, "snapshot_path", run_or_path))
    if original.is_symlink():
        raise InvalidPackage("Snapshot path is a symlink")
    path = original.resolve()
    root = _root("QUIZ_SNAPSHOT_ROOT", "var/snapshots")
    if path.parent != root:
        raise InvalidPackage("Snapshot path is outside the snapshot root")

    expected = getattr(run_or_path, "snapshot_digest", None)
    if expected is None:
        try:
            expected = _digest((path / "manifest.json").read_bytes())
        except OSError as exc:
            raise InvalidPackage("Cannot read snapshot") from exc
    if not isinstance(expected, str):
        raise InvalidPackage("Invalid snapshot digest")
    return path, expected


def _verify_snapshot(path, expected):
    """Fully verify one pinned snapshot before trusting it in this process."""
    try:
        manifest_path = path / "manifest.json"
        if manifest_path.is_symlink():
            raise InvalidPackage("Snapshot manifest is a symlink")
        manifest_bytes = manifest_path.read_bytes()
        if _digest(manifest_bytes) != expected:
            raise InvalidPackage("Snapshot manifest changed")
        manifest = json.loads(manifest_bytes)
        files = manifest.get("files")
        if manifest.get("schema_version") != 1 or not isinstance(files, dict):
            raise InvalidPackage("Invalid snapshot manifest")

        config_digest = files.get("game.json")
        if not isinstance(config_digest, str):
            raise InvalidPackage("Invalid snapshot manifest")
        config_path = path / "game.json"
        if config_path.is_symlink():
            raise InvalidPackage("Snapshot content changed")
        config_bytes = config_path.read_bytes()
        if _digest(config_bytes) != config_digest:
            raise InvalidPackage("Snapshot content changed")

        for rel, digest in files.items():
            _relative_path(rel)
            if not isinstance(digest, str):
                raise InvalidPackage("Invalid snapshot manifest")
            if rel == "game.json":
                continue
            target = path / rel
            if target.is_symlink() or _file_digest(target) != digest:
                raise InvalidPackage("Snapshot content changed")

        config = json.loads(config_bytes)
        if not isinstance(config, dict):
            raise InvalidPackage("Invalid snapshot config")
        _validate(config, config.get("package_id"))
        return _VerifiedSnapshot(
            path=path,
            config_bytes=config_bytes,
            files=MappingProxyType(dict(files)),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InvalidPackage("Cannot read snapshot") from exc


def _verified_snapshot(run_or_path):
    """Return a process-verified snapshot, single-flighting cold verification."""
    path, expected = _snapshot_identity(run_or_path)
    key = (path, expected)

    with _snapshot_cache_lock:
        cached = _verified_snapshot_cache.get(key)
        if cached is not None:
            _verified_snapshot_cache.move_to_end(key)
            return cached
        flight = _snapshot_verification_flights.get(key)
        if flight is None:
            flight = Future()
            _snapshot_verification_flights[key] = flight
            verifier = True
        else:
            verifier = False

    if not verifier:
        return flight.result()

    try:
        verified = _verify_snapshot(path, expected)
    except BaseException as exc:
        with _snapshot_cache_lock:
            _snapshot_verification_flights.pop(key, None)
        flight.set_exception(exc)
        raise

    with _snapshot_cache_lock:
        _verified_snapshot_cache[key] = verified
        _verified_snapshot_cache.move_to_end(key)
        while len(_verified_snapshot_cache) > _VERIFIED_SNAPSHOT_CACHE_MAX:
            _verified_snapshot_cache.popitem(last=False)
        _snapshot_verification_flights.pop(key, None)
    flight.set_result(verified)
    return verified


def _reset_snapshot_cache():
    """Clear verified snapshots; used by restart-focused tests."""
    with _snapshot_cache_lock:
        if _snapshot_verification_flights:
            raise RuntimeError("Cannot clear snapshot cache during verification")
        _verified_snapshot_cache.clear()


def load_snapshot(run_or_path):
    """Return pinned rules after one full verification per process/cache lifetime."""
    verified = _verified_snapshot(run_or_path)
    return json.loads(verified.config_bytes)


def _verified_snapshot_file(run_or_path, relative_path):
    """Verify one requested file against the already-verified pinned manifest."""
    verified = _verified_snapshot(run_or_path)
    rel = str(_relative_path(relative_path))
    expected = verified.files.get(rel)
    if not isinstance(expected, str):
        raise InvalidPackage("Snapshot file is not declared in manifest")
    target = verified.path / rel
    try:
        if target.is_symlink() or _file_digest(target) != expected:
            raise InvalidPackage("Snapshot content changed")
    except OSError as exc:
        raise InvalidPackage("Cannot read snapshot") from exc
    return target

def snapshot_media_path(run, team_id, relative_path):
    """Return a declared asset only after the caller has authorized this team."""
    try:
        rel = str(_relative_path(relative_path))
        config = load_snapshot(run)
        if team_id not in ("a", "b"):
            return None
        declared = {
            descriptor["path"]
            for puzzle in config["teams"][team_id]["puzzles"]
            for descriptor in (
                puzzle_media_descriptor(media) for media in puzzle["media"]
            )
        }
        if rel not in declared:
            return None
        return _verified_snapshot_file(run, f"media/{rel}")
    except (InvalidPackage, KeyError, TypeError):
        return None


def snapshot_music_audio_path(run, question_number):
    """Return only the declared audio for one caller-authorized Music question."""
    if type(question_number) is not int or not 1 <= question_number <= 11:
        return None
    try:
        config = load_snapshot(run)
        if config.get("schema_version") not in (4, 5, 6):
            return None
        question = config["music_questions"][question_number - 1]
        audio = question.get("audio")
        if audio is None:
            return None
        rel = str(_relative_path(audio))
        return _verified_snapshot_file(run, f"media/{rel}")
    except (InvalidPackage, IndexError, KeyError, TypeError):
        return None


def snapshot_challenge_media_path(
    run,
    challenge,
    *,
    actor_role,
    actor_team_id,
    relative_path,
):
    """Return post-grace Challenge media to an authorized participant/admin."""
    if (
        not run.active
        # Pause preserves an active Challenge's already-revealed answer context.
        # The serving view separately enforces the gameplay-time grace period.
        or run.global_state not in ("ADVENT_QUIZ", "PAUSED")
        or challenge.run_id != run.pk
        or challenge.status != "active"
        or (
            actor_role != "admin"
            and not (
                actor_role == "team"
                and actor_team_id
                in (challenge.initiator_team_id, challenge.challenged_team_id)
            )
        )
    ):
        return None
    try:
        rel = str(_relative_path(relative_path))
        config = load_snapshot(run)
        if config.get("schema_version") != 6:
            return None
        puzzle = config["challenge_puzzles"][challenge.initiator_team_id]
        if challenge.question_id != puzzle["id"] or rel not in puzzle["media"]:
            return None
        return _verified_snapshot_file(run, f"media/{rel}")
    except (InvalidPackage, KeyError, TypeError):
        return None