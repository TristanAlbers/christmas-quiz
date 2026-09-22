# First vertical slice contracts

Status: implemented and validated for phase 1, 2026-09-22.
The normative rules remain in `christmas-2026-game-rules-state-semantics.md`.
Changes to a shared contract require architect review before code uses it.
No unresolved rule ambiguity blocks this slice. The two-puzzle package is
demonstration data and never signals a completed 25-puzzle game.

The implemented HTTP endpoints are `/login/`, `/admin-login/`, `/team/`,
`/team/state/`, `/team/answer/`, `/admin-game/`, `/admin-game/start/`, and
`/media/<run>/<team>/<asset>/`. The media endpoint authorizes the actor's
current visible puzzle on every request. Account provisioning reads four
distinct credentials from environment variables through `provision_accounts`;
container startup runs that command after migrations. A changed `.env`
credential takes effect when Compose recreates the app container; a plain
container restart reuses its existing environment.

## Concrete phase 1 decisions

- `Actor` is an immutable value with `user_id: int`, `role: Literal["team", "admin"]`,
  and `team_id: Literal["a", "b"] | None`. `quiz.auth.actor_for_user(user)`
  resolves it from the authenticated Django user and a database account role.
  Team identity in URLs/forms is never used to construct an actor.
- `StartGame(request_id, package_id)` and `SubmitAnswer(request_id, run_id,
  question_id, answer)` are immutable values. Results/projections are immutable
  values defined in `quiz/contracts.py`; request IDs and run IDs are opaque UUID
  strings, while question IDs are snapshot-local strings. Errors use
  `ApplicationError(code)` and the semantic codes below.
- Start receipt uniqueness is `(actor_user_id, request_id)` globally, because a
  run does not yet exist. An identical retry returns the original run even after
  it has started. Answer receipt uniqueness is `(run, actor_user_id, request_id)`.
  A future reset will require an explicit run-epoch policy before implementation;
  a historical Start receipt must never start a fresh run by replay.
  The digest covers action, actor, and all command fields, including answer text.
  A retry is checked before stale-state validation, so a committed response can
  be recovered after progression. Receipt results contain the original outcome.
- Only one run can be active. A new Start in `ADVENT_QUIZ` is disallowed unless
  it is the original receipt retry. There is no reset in phase 1.
- The package is JSON with `schema_version: 1`, stable package ID, `initial_points`,
  and exactly teams `a` and `b`. Each has sequential demonstration puzzles 1 and
  2 with stable IDs, title/body, one declared `text_exact` or `number_exact`
  answer validator, integer nonnegative reward, optional hint, optional fragment,
  and relative media paths. No arbitrary expressions or Python imports. An
  immutable snapshot copies validated JSON and referenced media into a uniquely
  named directory under `var/snapshots`, stores a manifest/content digest, and
  is pinned by the run. Source package mutations/deletions cannot change an
  active run. Credentials are provisioned separately via a management command.
- `TeamRun` stores `activity_state`, `current_number`, `points`; puzzle completion
  rows store `completed`, route and historical award marker separately. Attempts,
  fragments, receipts and audit events have run/team foreign keys. All mutable
  state writes for an answer share one `BEGIN IMMEDIATE` transaction; a wrong
  answer writes an attempt, receipt and event, with no progression. A correct
  answer writes attempt, completion, once-only reward/fragment, progression,
  receipt and event before commit. Domain functions return decisions and never
  write models. Persistent checks prevent negative balances and duplicate awards.
- `quiz.persistence.immediate_transaction()` owns SQLite's bounded writer-slot
  acquisition; the application owns use-case transaction call sites and ORM
  orchestration. `quiz.persistence.read_snapshot()` provides a short DEFERRED
  consistent read for multi-query projections. Polling never takes a writer slot.
  WAL, foreign keys and busy timeout are configured at connection creation.
- A team projection returns only the team's current question and its own state.
  Its media links use authenticated snapshot media endpoints with team scope.
  Private media is outside WhiteNoise/static and is authorized afresh on every
  request. A cross-team media path returns the same 404 response whether or not
  the target asset exists. Admin Start is the only phase 1 admin mutation.
- Browser polling uses one stable `#live-game` sync container. Poll requests use
  `hx-sync="#live-game:drop"` and commands use `hx-sync="#live-game:replace"`.
  Polls update status, and replace question/input only on context change; an
  input in progress keeps its element and focus. Browser acceptance uses an
  isolated SQLite database and server instance, never the mounted event runtime.

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
| architect | `quiz/application.py`, `quiz/contracts.py`, `config/settings.py`, `config/urls.py`, `quiz/web/urls.py`, `quiz/web/views.py`, `quiz/templates/quiz/index.html`, `quiz/templates/quiz/team.html`, `quiz/templates/quiz/admin.html`, `quiz/templates/quiz/_team_state.html`, `quiz/templates/quiz/_question_pane.html`, `quiz/static/quiz/**`, `Dockerfile`, `compose.yaml`, dependency files, `games/christmas-2026-demo/**`, shared `tests/conftest.py` if needed, this document and plan | `tests/integration/test_first_slice.py`, existing `tests/integration/test_scaffold.py` |
| game_engine | `quiz/domain/__init__.py`, `quiz/domain/types.py`, `quiz/domain/answers.py`, `quiz/domain/completion.py` | `tests/domain/test_answers.py`, `tests/domain/test_completion.py` |
| persistence_security | `quiz/apps.py`, `quiz/models.py`, `quiz/migrations/0001_initial.py`, `quiz/configuration.py`, `quiz/persistence.py`, `quiz/auth.py`, `quiz/web/auth_views.py`, `quiz/web/auth_forms.py`, `quiz/web/media_views.py`, `quiz/templates/quiz/login.html`, `quiz/management/commands/provision_accounts.py` | `tests/integration/test_authentication.py`, `tests/integration/test_persistence.py` |
| test_invariants | No production files without a new assignment | `tests/security/test_team_isolation.py`, `tests/integration/test_concurrency.py`, `tests/integration/test_recovery.py`, `tests/browser/test_live_sync.py` |

The architect integrates root URL and settings changes requested by the
persistence specialist and coordinates migration ordering. Specialists inspect
existing files first and report overlaps or incompatible assumptions instead
of editing another owner's files. Recording assignments does not authorize
parallel implementation.

The architect creates `quiz/contracts.py` first. Domain and persistence owners
may then edit their distinct modules concurrently. The architect edits
`quiz/application.py` after exported domain/persistence APIs are confirmed;
`quiz/web/urls.py` is edited last, after auth and media view names are exported.

## Acceptance gate

The first slice is complete only after Team A logs in, sees its own puzzle 1,
and is refused Team B reads/writes; a wrong answer persists without moving; a
correct answer atomically completes puzzle 1, grants its configured reward
once, exposes puzzle 2, writes an immutable event, and reloads from persisted
state. Tests cover duplicate and stale requests, rollback, snapshot stability,
and real SQLite contention. Run `check`, `makemigrations --check --dry-run`,
Ruff, and relevant Django tests inside the container before handoff.
