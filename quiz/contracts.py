"""Small immutable boundary values for the first game slice."""

from dataclasses import dataclass
from typing import Literal

Role = Literal["team", "admin"]
TeamId = Literal["a", "b"]
ErrorCode = Literal[
    "unauthenticated",
    "forbidden",
    "invalid_input",
    "stale_run",
    "stale_question",
    "disallowed_state",
    "request_conflict",
    "temporarily_busy",
    "insufficient_points",
    "no_hint_tokens",
    "already_active",
]


class ApplicationError(Exception):
    def __init__(self, code: ErrorCode):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class Actor:
    user_id: int
    role: Role
    team_id: TeamId | None = None


@dataclass(frozen=True)
class StartGame:
    request_id: str
    package_id: str


@dataclass(frozen=True)
class StartResult:
    run_id: str
    global_state: str


@dataclass(frozen=True)
class SubmitAnswer:
    request_id: str
    run_id: str
    question_id: str
    answer: str


@dataclass(frozen=True)
class SubmitMusicAnswer:
    request_id: str
    run_id: str
    question_id: str
    answer: str


@dataclass(frozen=True)
class QuestionProjection:
    id: str
    number: int
    title: str
    body: str
    media_urls: tuple[str, ...] = ()
    hint: str | None = None
    hint_available: bool = False


@dataclass(frozen=True)
class MusicScoreProjection:
    team_id: TeamId
    score: int


@dataclass(frozen=True)
class MusicProjection:
    phase: Literal["question", "final_results"]
    question_id: str | None
    question_number: int | None
    question_total: int
    title: str | None
    body: str | None
    scores: tuple[MusicScoreProjection, ...]
    question_elapsed_ms: int | None = None
    final_results_remaining_ms: int | None = None
    previous_winner_team_id: TeamId | None = None
    audio_url: str | None = None


@dataclass(frozen=True)
class AdventDoorProjection:
    number: int
    status: Literal["completed", "current", "future"]


@dataclass(frozen=True)
class AdventProgressProjection:
    doors: tuple[AdventDoorProjection, ...]
    completed_count: int
    current_number: int | None
    is_finished: bool


@dataclass(frozen=True)
class PublicTeamProgressProjection:
    team_id: TeamId
    advent_progress: AdventProgressProjection


@dataclass(frozen=True)
class TeamPresentationEvent:
    id: int
    kind: Literal["freeze_attack"]
    attacker_team_id: TeamId
    target_team_id: TeamId
    frozen_team_id: TeamId
    reversed: bool


@dataclass(frozen=True)
class TeamProjection:
    run_id: str | None
    global_state: str
    team_state: str
    points: int
    current_number: int | None
    completed_numbers: tuple[int, ...]
    fragments: tuple[str, ...]
    question: QuestionProjection | None
    hint_tokens: int = 0
    hint_cost: int | None = None
    skip_cost: int | None = None
    freeze_cost: int | None = None
    uno_reverse_cost: int | None = None
    uno_reverse_active: bool = False
    freeze_remaining_ms: int | None = None
    music: MusicProjection | None = None
    advent_progress: AdventProgressProjection | None = None
    first_finisher_team_id: TeamId | None = None
    gameplay_elapsed_ms: int = 0
    opponent_freeze_active: bool = False
    presentation_event: TeamPresentationEvent | None = None


@dataclass(frozen=True)
class AnswerResult:
    outcome: Literal["incorrect", "completed"]
    state: TeamProjection


@dataclass(frozen=True)
class MusicAnswerResult:
    outcome: Literal["incorrect", "won"]
    state: TeamProjection


@dataclass(frozen=True)
class RunCommand:
    request_id: str
    run_id: str


@dataclass(frozen=True)
class AdminPoints:
    request_id: str
    run_id: str
    team_id: TeamId
    delta: int


@dataclass(frozen=True)
class AdminTeam:
    request_id: str
    run_id: str
    team_id: TeamId


@dataclass(frozen=True)
class AdminPuzzle:
    request_id: str
    run_id: str
    team_id: TeamId
    question_id: str


@dataclass(frozen=True)
class TeamPuzzle:
    request_id: str
    run_id: str
    question_id: str


@dataclass(frozen=True)
class CommandResult:
    outcome: str
    run_id: str
    global_state: str


@dataclass(frozen=True)
class AdminTeamProjection:
    team_id: TeamId
    activity_state: str
    points: int
    hint_tokens: int
    current_number: int
    current_question_id: str | None
    completed_numbers: tuple[int, ...]
    hint_revealed: bool
    uno_reverse_active: bool = False
    freeze_remaining_ms: int | None = None
    advent_progress: AdventProgressProjection | None = None


@dataclass(frozen=True)
class PackageProjection:
    package_id: str
    startable: bool
    diagnostic: str | None = None


@dataclass(frozen=True)
class AdminProjection:
    run_id: str | None
    global_state: str
    package_id: str | None
    teams: tuple[AdminTeamProjection, ...]
    packages: tuple[PackageProjection, ...] = ()
    discovery_error: str | None = None
    music: MusicProjection | None = None
    first_finisher_team_id: TeamId | None = None
    gameplay_elapsed_ms: int = 0


@dataclass(frozen=True)
class PublicProjection:
    global_state: str
    music: MusicProjection | None = None
    teams: tuple[PublicTeamProgressProjection, ...] = ()
    first_finisher_team_id: TeamId | None = None
    gameplay_elapsed_ms: int = 0
