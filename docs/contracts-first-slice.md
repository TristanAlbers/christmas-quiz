# First vertical slice contracts

Status: initial architect contract for review; no gameplay implementation exists.
The normative rules remain in `christmas-2026-game-rules-state-semantics.md`.
Changes to a shared contract require architect review before code uses it.
No unresolved rule ambiguity blocks this slice.

## Scope and shared application surface

Implement only admin Start and Team A's first two puzzles: authenticated read,
wrong answer persisted without progression, correct answer through canonical
completion, configured once-only reward, advance to puzzle 2, audit event, and
reload. Include Team B authorization rejection. The scaffold currently has no
game models, package format, or domain rules. The first schema migration and
shared Python types must be reviewed together before implementation.

Place immutable request/result types in `quiz/contracts.py` under architect
ownership. Keep them free of Django models and HTTP objects. Intended public
application signatures:

```python
def start_game(actor: Actor, command: StartGame) -> StartResult: ...
def get_team_state(actor: Actor) -> TeamProjection: ...
def submit_answer(actor: Actor, command: SubmitAnswer) -> AnswerResult: ...
```

`Actor` is built only from the authenticated server session and has `user_id`,
`role` (`team` or `admin`), and a server-resolved `team_id` only for a team.
`StartGame` has `request_id` and a selected, validated `package_id`. Its result
has `run_id` and new global state. `SubmitAnswer` has `request_id`, displayed
`run_id`, `question_id`, and answer text. It has no authorization team ID from
the client. `AnswerResult` distinguishes `incorrect` (accepted and persisted)
from `completed` (accepted with resulting team projection). `TeamProjection`
contains only the actor's team data and currently allowed question content;
it never includes answer keys, unrevealed hints, or opponent private state.
IDs are opaque strings at the transport boundary. New attempts get new request
IDs; retries keep the original one.

Semantic failures are `unauthenticated`, `forbidden`, `invalid_input`,
`stale_run`, `stale_question`, `disallowed_state`, `request_conflict`, and
`temporarily_busy`. Wrong answers are successful results, not failures. Web
handlers map these to 401 or a login redirect, 403, 400, 409, 409, 409, 409,
and 503 respectively. A delayed answer for an old question must receive
`stale_question` and never apply to the next question. Responses must not
reveal whether an opponent's private resource exists.

## Domain contract

The domain receives plain immutable state/configuration values, not ORM
models, requests, or wall-clock access. Its first public operations are answer
evaluation and one canonical completion calculation. Completion accepts route
`correct_answer`, `skip`, or `admin_force`, though only the first is exposed
in this slice. It returns a proposed state/effect result; the application
persists it atomically. Historical award markers remain separate from current
`completed` status, so reopening cannot pay rewards twice. `game_engine` and
the architect finalize domain types and signatures before code depends on them.

## Persistence and transaction contract

`persistence_security` owns Django models/migrations, account/session
resolution, package snapshot storage, constraints, and SQLite connection
policy. The architect owns application transaction call sites. A mutating use
case takes SQLite's `IMMEDIATE` writer slot **before** reading mutable state.
It then rechecks actor permissions and run/question/state, applies the one
domain decision, writes attempts, progression, balances and award history,
records a request receipt and append-only event, and commits all or nothing.
A wrong answer writes an attempt and receipt without advancing. The first
valid accepted transaction wins; client timestamps do not decide.

Receipts are unique within run and actor for `request_id`. Repeating the same
payload returns the recorded result without repeating effects; reusing an ID
for a different payload returns `request_conflict`. The application compares
a canonical payload digest. Receipt and event writes share the state-change
transaction. Configuration and media are validated and staged before Start's
short transaction; Start pins an immutable snapshot/version, which every
active-run read uses. No package code executes.

Use consistent read snapshots for projections. Polling reads stay outside the
`IMMEDIATE` command transaction. The persistence specialist proposes the
smallest query and implements SQLite WAL, foreign-key enforcement, and bounded
busy timeout with architect-coordinated settings edits. The first migration is
reviewed for nonnegative balances, unique awards/receipts, foreign keys, and
immutable audit behavior. Audit rows survive future full resets.

Initial event shape: timestamp; run ID; request ID; server actor ID/role;
affected team ID; action; result; puzzle ID if relevant; and structured
previous/delta/new values for changed balances or state. Additional optional
fields can be added with later effects. Events are historical facts, never
the source of live state.

## Exact ownership for first slice

| Owner | Production files | Focused test files |
| --- | --- | --- |
| architect | `quiz/application.py`, `quiz/contracts.py`, `config/settings.py`, `config/urls.py`, `quiz/web/urls.py`, `quiz/web/views.py`, `quiz/templates/quiz/index.html`, `quiz/templates/quiz/team.html`, `quiz/static/quiz/**`, `Dockerfile`, `compose.yaml`, dependency files, shared `tests/conftest.py` if needed | `tests/integration/test_first_slice.py`, existing `tests/integration/test_scaffold.py` |
| game_engine | `quiz/domain/__init__.py`, `quiz/domain/types.py`, `quiz/domain/answers.py`, `quiz/domain/completion.py` | `tests/domain/test_answers.py`, `tests/domain/test_completion.py` |
| persistence_security | `quiz/models.py`, `quiz/migrations/0001_initial.py`, `quiz/configuration.py`, `quiz/auth.py`, `quiz/web/auth_views.py`, `quiz/web/auth_forms.py`, `quiz/templates/quiz/login.html` | `tests/integration/test_authentication.py`, `tests/integration/test_persistence.py` |
| test_invariants | No production files without a new assignment | `tests/security/test_team_isolation.py`, `tests/integration/test_concurrency.py`, `tests/integration/test_recovery.py`, `tests/browser/test_live_sync.py` |

The architect integrates root URL and settings changes requested by the
persistence specialist and coordinates migration ordering. Specialists inspect
existing files first and report overlaps or incompatible assumptions instead
of editing another owner's files. Recording assignments does not authorize
parallel implementation.

## Acceptance gate

The first slice is complete only after Team A logs in, sees its own puzzle 1,
and is refused Team B reads/writes; a wrong answer persists without moving; a
correct answer atomically completes puzzle 1, grants its configured reward
once, exposes puzzle 2, writes an immutable event, and reloads from persisted
state. Tests cover duplicate and stale requests, rollback, snapshot stability,
and real SQLite contention. Run `check`, `makemigrations --check --dry-run`,
Ruff, and relevant Django tests inside the container before handoff.
