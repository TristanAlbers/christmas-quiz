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
class QuestionProjection:
    id: str
    number: int
    title: str
    body: str
    media_urls: tuple[str, ...] = ()


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


@dataclass(frozen=True)
class AnswerResult:
    outcome: Literal["incorrect", "completed"]
    state: TeamProjection
