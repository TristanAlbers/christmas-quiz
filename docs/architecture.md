# Christmas Escape Room Quiz — Architecture

Status: approved architecture; phases 1 and 2 implemented, phase 3 in progress.

Phase 2 implementation decisions are recorded in
[`phase-2-contract.md`](phase-2-contract.md): one durable Hint reveal per
team/puzzle, generic Hint inventory, immediate Skip via canonical completion,
and reset by creating a new READY run ID from the immutable prior snapshot.

Phase 3 clock and effect decisions are recorded in
[`phase-3-contract.md`](phase-3-contract.md): active Advent downtime counts on a
persisted gameplay clock, paused downtime does not, and only player Freeze
attacks trigger Uno Reverse.

This document records implementation choices. Game behavior remains governed by
`christmas-2026-game-rules-state-semantics.md`, followed by `Design.md`, `Views.md`,
and `Game States.md`, in that order. Follow `AGENTS.md` when doing repository work.
Changes to this architecture or shared contracts require architect review.

## Stack and deployment

Use Python 3.12, Django 5.2 LTS, Django templates, locally bundled HTMX, plain CSS,
SQLite, Gunicorn WSGI, and WhiteNoise. Pin compatible dependency versions when
scaffolding. Ordinary synchronous functions handle requests and transactions.
The browser renders server decisions and submits commands; it has no game rules.

Docker Compose is the primary development, deployment, testing, and inspection
workflow. The Linux host needs Docker and Compose, not host-installed Python or
Node. Use one application service, initially one Gunicorn `gthread` worker with
four threads:

```text
gunicorn config.wsgi:application --bind 0.0.0.0:8000 --worker-class gthread --workers 1 --threads 4
```

This is a small deployment default, not a concurrency guarantee. The database
decides competing transactions even when requests run on different threads.
Publish the container port only on the intended LAN/VPN interface. There is no
public-internet deployment requirement, separate database service, Redis, task
queue, frontend build service, or additional proxy container.

Use `restart: unless-stopped`, a health check, and standard-output logs. A health
check reports status; it does not restart an unhealthy but still-running process.
Bind-mount `./var:/app/var` for `quiz.sqlite3`, `snapshots/`, and `backups/` on local
disk. Keep `var/`, credentials, and local secrets out of version control and the
image. Mount source game packages read-only. Document container-user permissions
for the bind mount during scaffolding.

Run `collectstatic` at image build time. With `DEBUG=False`, WhiteNoise middleware
and compressed manifest storage serve collected application CSS, JavaScript, and
public application images. Bundle HTMX locally so play needs no internet access.
Private puzzle media must never enter the public static directory.

Planned operations include `docker compose up -d --build`, `docker compose ps`,
`docker compose logs -f app`, and management commands through
`docker compose exec app python manage.py ...`. A development/test image target
provides linting and browser dependencies. See `docs/scaffold.md` for commands.

## Repository and boundaries

Keep the current specifications and agent configuration in place. The intended
application structure is:

```text
compose.yaml
Dockerfile
.dockerignore
pyproject.toml
requirements.lock
manage.py
config/                         settings, URLs, WSGI entry point
quiz/
  domain/                       plain Python rules and canonical completion
  application.py                synchronous use cases and transaction boundaries
  models.py
  migrations/
  configuration.py              package validation and snapshot creation
  web/                          authentication, forms, views, routes
  templates/
  static/
games/christmas-2026/
  game.json
  team-a/{puzzles,assets}/
  team-b/{puzzles,assets}/
tests/{domain,integration,security,browser}/
docs/architecture.md
var/                            untracked persistent data
```

- **Domain:** deterministic game states, answer checking, prerequisites, costs,
  rewards, and canonical completion. No Django, ORM, HTTP, or global wall-clock
  dependency. Time is an explicit input when timer milestones are implemented.
- **Application:** authenticate/authorize the supplied server actor, coordinate
  persistence and domain rules in one transaction, and expose actor-scoped state
  queries. Use ordinary functions, not a command-handler framework.
- **Persistence:** Django models, migrations, constraints, sessions, and database
  transaction configuration. Critical database constraints defend invariants;
  they do not become a second game engine.
- **Configuration:** schema-validated declarative JSON and media. Only named,
  implemented answer validators and completion effects are allowed. Never execute
  code from a game package.
- **Web and presentation:** parse requests, invoke application functions, and
  render separate team, admin, and public projections. Business rules do not live
  in forms, views, or templates. Do not add generic repository interfaces or
  speculative adapter layers.

## State, commands, isolation, and transactions

Global state and per-team activity state are distinct. Use the canonical enums
from the normative specification. `PAUSED` and `MUSIC_QUIZ` preserve underlying
team states and gameplay-timer durations. Use `completed` for puzzle status and
record completion route separately. There is exactly one completion pipeline for
correct answers, immediate Skip, and admin force-completion.

Keep current completion separate from historical reward/fragment awards so a
reopened puzzle cannot award them twice. Enforce all earlier prerequisites on the
backend. Global `FINISHED` requires both teams to complete puzzle 25; the first
finisher becomes inactive while the other team continues.

Initial application functions cover Start, Submit Answer, and authorized state
queries. The architect defines their concrete Python contracts before parallel
implementation. Commands carry the displayed run ID, question ID, and a request
ID. Resolve the actor and team from the authenticated server session, never a
client-supplied team ID. Repeated request IDs with the same command return the
recorded outcome without repeating effects; reuse with a different payload is
rejected. Preserve IDs when retrying an uncertain request, and issue a new ID for
a new answer attempt.

Distinguish a persisted incorrect answer from a rejected command. Use stable
results for authentication/authorization failure, invalid input, stale run or
question, disallowed state, and temporary database contention. A delayed answer
must never be applied to the next question. No browser cancellation is treated as
proof that a server-side command did not commit.

Use Django sessions, hashed configurable team credentials, two named admin
accounts, and CSRF protection. One team device per team is the supported setup.
Apply authorization to every private read/write, including direct requests and
media access. Do not expose answers, unrevealed hints, or opposing-team private
data in HTML or responses. Frozen projections omit puzzle/hint content rather
than covering it visually. Game-master controls call application functions;
editable model-admin screens must not bypass the game engine.

SQLite uses WAL, foreign keys, a bounded busy timeout, nonnegative-balance checks,
and uniqueness constraints for one-time awards and request receipts. Every
mutating use case acquires an `IMMEDIATE` transaction **before reading mutable
game state**, then rechecks authorization and rules, applies changes, records
attempts/results and audit events, and commits all or nothing. Do not depend on
Python locks or SQLite's ineffective `select_for_update()` for race correctness.
Do not wrap every HTTP request in a write transaction or hold locks while
rendering HTML or doing filesystem work.

State projections must come from a consistent database snapshot. Prefer a single
SELECT for the first slice. If a projection later requires multiple queries, use
a short read-only `DEFERRED` snapshot with the persistence specialist; do not
accidentally use the command's `IMMEDIATE` locking policy for polling reads.

For Music Quiz, the first valid server-accepted transaction wins. The transaction
which acquires the writer slot validates the unresolved question, records the
winner, awards points, and immediately advances to the next question. A competing
transaction waits, then reads the committed state and rejects its old question.
An invalid or rolled-back transaction wins nothing. This is database acceptance
order, not client timestamps or a guarantee of network-arrival FIFO. The same
atomicity principle governs completion, purchases, and other races.

## Live views: 500 ms polling

Use HTMX to poll one compact, authenticated HTML-fragment endpoint per visible
screen every 500 ms. Refresh immediately on return to a visible tab. Ten active
screens generate about twenty polling requests per second; the specified shared
team-device setup generally uses fewer. Measure performance on the home server.

The submitting screen receives updated state directly in its POST response.
Other screens ordinarily see a change within 0–500 ms plus network/server/render
time. Aim for roughly subsecond visibility on the LAN; do not promise a hard
deadline. Music Quiz advances immediately in the authoritative transaction and
the next poll displays the winner, updated Music scores, and next question.
The normative rules do not require push transport.

Use the same stable synchronization container for all polls and commands affecting
one screen. Never replace that container. Polls use **`drop`**; commands use
**`replace`**. A command aborts an in-flight poll and still sends its POST. A poll
is skipped while a command is running and cannot cancel a command. Disable command
buttons during submission and retain server-side idempotency.

Illustrative template contract, not application code already implemented:

```html
<section id="live-game">
  <input id="view-context" type="hidden"
         name="view_context" value="{{ view_context }}">
  <div id="poller"
       hx-get="/team/state/"
       hx-trigger="every 500ms [!document.hidden], visibilitychange[!document.hidden] from:document"
       hx-sync="#live-game:drop"
       hx-include="#view-context"
       hx-target="#game-status"
       hx-swap="innerHTML"></div>
  <div id="game-status"></div>
  <div id="question-pane">
    <form hx-post="/team/answer/"
          hx-trigger="submit"
          hx-sync="#live-game:replace"
          hx-disabled-elt="#live-game button[type='submit']"
          hx-target="#game-status"
          hx-swap="innerHTML">
      {% csrf_token %}
      <input type="hidden" name="run_id" value="{{ run_id }}">
      <input type="hidden" name="question_id" value="{{ question_id }}">
      <input type="hidden" name="request_id" value="{{ request_id }}">
      <input name="answer" autocomplete="off">
      <button type="submit">Submit</button>
    </form>
  </div>
</section>
```

Normal polls replace status/results only. Replace `question-pane` and its context
field out-of-band only when the run, mode, question, or interaction permissions
change. Otherwise retain the actual input element so typing, focus, and caret
survive. Wrong-answer feedback and request tokens update separately. The client
context is only a rendering hint and cannot authorize access. Do not rely on
`hx-preserve` to preserve text-input focus.

Show connection trouble on failed requests; the next successful poll reads
current state. Synchronization avoids obsolete poll responses overwriting command
results. No SSE, WebSocket, notification hub, post-commit delivery callback,
subscriber queue, persisted audience revision, async streaming, or pub/sub
infrastructure is needed.

## Configuration, audit, and recovery

Start validates and stages an immutable snapshot of configuration **and every
referenced media asset**, then pins the completed snapshot in the short Start
transaction. Every active-run read uses that snapshot, including after a restart.
Source package edits or deletion cannot silently change active rules or media.
Keep secret credentials out of committed puzzle packages.

In phase 1, `load_snapshot` verifies the manifest and all declared media bytes
when it reads configuration, including within an answer transaction. The two
asset demonstration package keeps this short. A larger event package may make
that writer hold time material; measure it and adopt a validated immutable
snapshot cache or pretransaction verification with an in-transaction pin check
before loading large media packages. Do not skip integrity verification.

Persist attempts, balances, progression, reward history, fragments, and audit
events. Events identify timestamp, run/request, actor, affected team, action,
result, relevant puzzle/effect, and previous/delta/new values where applicable.
Audit history is append-only through all supported application operations;
resets preserve history and record the reset. Do not offer audit editing in admin
tools. Database triggers are optional later defense in depth, not a prerequisite.

Timers in later milestones use persisted, server-authoritative gameplay time and
injected clocks for tests. Browser refresh/disconnect never changes game outcomes.
Unexpected server-downtime accounting must be settled before timer implementation.

Provide a consistent SQLite backup plus its referenced snapshots and a documented,
tested restore procedure. Backups under `var/backups` survive container replacement
but require copying elsewhere to protect against losing the host disk.

## Ownership and coordination

These are future implementation assignments, not authorization to spawn agents
or start scaffolding. Specialists inspect current files and report overlaps
before editing. The architect reviews shared-contract changes.

| Owner | Exclusive production responsibility | Focused tests |
| --- | --- | --- |
| architect | `quiz/application.py`, shared contract decisions, application integration; initially `config/`, deployment/dependency files, root routing, non-auth gameplay views, templates/static | application integration checks until explicitly assigned |
| game_engine | `quiz/domain/` pure policies, transitions, answer validation, canonical completion; no ORM or application orchestration | `tests/domain/` |
| persistence_security | `quiz/models.py`, `quiz/migrations/`, `quiz/configuration.py`, authentication/session helpers and auth views; transaction setup and constraints via architect-coordinated settings edits | assigned persistence/auth test files |
| test_invariants | cross-cutting security, transaction concurrency, recovery, and browser verification; no production changes without assignment | assigned files in `tests/integration/`, `tests/security/`, `tests/browser/` |

Authentication views/helpers are explicitly assigned files within `quiz/web/`;
other gameplay views belong to the architect until reassigned. Directory ownership
does not override a named file assignment. Before parallel work, assign exact
test filenames to avoid specialist and cross-cutting test overlap.

High-conflict files are `quiz/application.py`, shared domain types, `config/`
settings/root URLs, dependency and Compose files, migration ordering, and shared
test fixtures. The architect owns integration of these files. Specialists propose
needed edits or receive an explicit temporary file assignment; never edit them
concurrently. Domain input/output structures are reviewed before persistence or
web code depends on them. Application transactions call domain policies once;
persistence specialists do not independently implement the same use cases.

## First slice and validation

Implementation order, after separate scaffolding authorization:

1. Establish the skeleton, dependencies, Compose workflow, checks, and narrow
   Python contracts under architect ownership.
2. Define the smallest domain states/completion rules and persistence schema,
   including accounts/sessions, run snapshots, attempts, reward history, receipts,
   and append-only audit behavior. Agree contracts before parallel edits.
3. Implement team/admin authentication and admin Start, pinning a development
   package snapshot and opening puzzle 1 for both teams.
4. Integrate Team A state, puzzle 1, wrong-attempt persistence without progression,
   and correct-answer atomic completion/reward/fragment/advance to puzzle 2/logging.
5. Add simple team/admin views and synchronized polling. Prove reload and
   container restart restore the persisted result.
6. Integrate adversarial tests and validate the milestone before later mechanics.

Acceptance includes authenticated Team A access; Team B read/write/media rejection;
server answer validation; persisted wrong attempts; sequential prerequisites;
configurable, once-only rewards; atomic completion; immutable events; snapshot
stability; and correct reload/restart results. The development slice is not a
claim that the full 25-puzzle game is ready.

Use domain tests, Django HTTP/integration tests, real temporary file-backed SQLite
databases with separate connections for races, and Playwright browser tests.
Test rollback with injected persistence failure, duplicate requests, stale
run/question IDs, cross-team requests, configuration/media changes, resets
preserving history when reset is implemented, and backup/restore.

Browser tests must hold a slow poll response, submit an answer, prove the POST
actually reaches the server, then release the old response and prove it cannot
overwrite the accepted result. Also test polls while a command is running,
input/focus preservation, hidden-tab return, reconnection, and `DEBUG=False`
static serving. Performance is a separate home-server smoke check with expected
screen count, not a brittle wall-clock CI assertion.

At the Music milestone, use controlled synchronization and two real SQLite
connections: A acquires the writer lock, B attempts the same question, A commits,
and B rechecks/rejects. Assert one winner, one reward, and one advancement; repeat
with the designated first transaction reversed. Also test both browsers showing
the result and next question. Do not substitute sequential mocks or sleep-based
ordering for the transaction test.

Container-based `manage.py check`, `makemigrations --check --dry-run`, Ruff,
application test, and Playwright dependencies are scaffolded. The first-slice
contracts and exact file ownership are in `docs/contracts-first-slice.md`.

## Decisions still deferred

There is no known blocking rule ambiguity for the first slice. Do not implement
Freeze, Music Quiz, Challenge, Uno Reverse, or polished calendars before that
slice is stable without explicit reprioritization.

- Public TV progression: normative section 15 treats progression as private and
  identifies Music scores as an explicit shared exception; `Views.md` requests
  public percentages. Ask for an explicit allowed public projection before that
  feature; never expose full team state to satisfy the display requirement.
- Server-downtime accounting is settled for phase 3: persisted `ADVENT_QUIZ`
  downtime counts, while persisted `PAUSED` downtime does not.
- Emergency reopening and unusual corrections need specific contracts before
  their later milestones. Do not invent those contracts in ordinary gameplay.

Known lower-authority conflicts are resolved already: both teams must finish for
global completion; Skip is immediate, not inventory; Hint tokens are generic;
frozen teams cannot view underlying puzzle/hint content.

## Technical references

- [Django supported versions](https://www.djangoproject.com/download/)
- [Django SQLite transaction behavior](https://docs.djangoproject.com/en/5.2/ref/databases/#sqlite-notes)
- [SQLite WAL](https://sqlite.org/wal.html)
- [Gunicorn worker/thread configuration](https://gunicorn.org/reference/settings/)
- [WhiteNoise with Django](https://whitenoise.readthedocs.io/en/stable/django.html)
- [HTMX synchronization](https://htmx.org/attributes/hx-sync/) and [verified 2.0.10 source](https://github.com/bigskysoftware/htmx/blob/v2.0.10/src/htmx.js)
- [HTMX polling and visibility triggers](https://htmx.org/attributes/hx-trigger/)
- [HTMX input preservation limitations](https://htmx.org/attributes/hx-preserve/)
- [Docker Compose operation](https://docs.docker.com/compose/gettingstarted/)
