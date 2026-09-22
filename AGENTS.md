# Christmas Escape Room Quiz — Codex Instructions

## Project goal

Build a lightweight, self-hosted Christmas escape-room quiz for two isolated teams, two administrators, and a public TV overview.

Correctness, recoverability, team isolation, understandable implementation, and easy game-package configuration take priority over visual polish or speculative scalability.

---

## Specification authority

Read the relevant specifications before designing or changing behavior.

Their authority, from highest to lowest, is:

1. `christmas-2026-game-rules-state-semantics.md` or `christmas-2026-game-rules-state-semantics(1).md` — normative game behavior and invariants.
2. `Design.md` — broader product and operational requirements.
3. `Views.md` — presentation targets and view requirements.
4. `Game States.md` — supporting state documentation.

When documents conflict, follow the higher-authority document.

Do not silently invent a resolution for an ambiguity not covered by that ordering. Record the ambiguity and escalate it to the `architect`; ask the user only when the ambiguity cannot safely be resolved from the approved architecture or specifications.

Read `docs/architecture.md` before implementation. It defines approved implementation choices and ownership but does not override the specification authority above.

The approved baseline is:

* synchronous Django;
* Gunicorn WSGI;
* Django templates;
* locally bundled HTMX;
* 500 ms authenticated polling;
* SQLite;
* WhiteNoise;
* Docker Compose;
* one application container;
* persistent `./var` runtime data.

Architecture changes require `architect` review.

Known examples:

* Global `FINISHED` occurs only after both teams complete puzzle 25, even if an older document suggests that the first finisher ends the game.
* Skip is an immediate completion action, not stored Skip inventory, even if an older view describes purchased Skip tokens.
* Use `completed` as the canonical puzzle status. Do not create separate domain states for solved, skipped, unlocked, or finished.

---

## Non-negotiable architecture rules

* Implement an authoritative backend state machine. The frontend renders state and requests transitions; it never decides whether a transition is legal.
* Keep global quiz state separate from each team's activity state.
* Treat `PAUSED` and `MUSIC_QUIZ` as global interruptions that preserve underlying team states and remaining gameplay-timer durations.
* Route correct answers, player Skip actions, and admin force-completion through one canonical completion pipeline.
* Enforce strict sequential prerequisites in the backend.
* Resolve concurrent actions at an atomic persistence/transaction boundary. The first valid server-accepted transaction wins.
* Derive team identity exclusively from authenticated server context. Never trust a client-supplied team ID for authorization.
* Enforce team isolation on every private read and write, including progression, attempts, points, effects, hints, fragments, inventory, puzzles, and private media.
* Keep balances non-negative and make purchases, rewards, attacks, one-time triggers, and race resolution atomic.
* Make timers server-authoritative, recoverable after refresh/reconnect/restart, and measured in Advent gameplay time where specified.
* Keep the event log append-only through supported application behavior and preserve it across a full game reset.
* Snapshot/version the active game configuration when a game starts. An active run reads only from its immutable snapshot.
* Treat `games/christmas-2026` as data, not application code. Never execute arbitrary puzzle-package code.
* Prefer one implementation of each business rule. Views and persistence code call domain/application behavior rather than reimplementing policy.
* Prefer the simplest conventional Django implementation that preserves these guarantees. Do not add abstraction layers for hypothetical future scale.

---

## Delivery principles

* Start with small end-to-end vertical slices.
* Build the normal game path before low-priority emergency operations.
* Keep deployment and maintenance simple for one home server and a developer with limited frontend experience.
* Make incremental changes and preserve unrelated user changes.
* Add or update automated tests with every behavior change.
* Test through public domain/application interfaces where practical rather than private implementation details.
* Before handing off, run the smallest relevant test suite plus required repository validation commands.
* Never weaken an invariant or change a specified rule merely to make a test pass.
* Do not silently change architecture, game rules, or public contracts.
* Record meaningful architectural decisions in the appropriate documentation.
* Do not broaden the requested implementation milestone without explicit user approval.

---

# Mandatory agent routing

The project-scoped agents under `.codex/agents/` are the default owners of their respective areas.

**The user does not need to explicitly request multi-agent mode or name an agent.**

For every non-trivial implementation, review, debugging, or design task:

1. Inspect the task.
2. Classify it by ownership using the routing rules below.
3. Delegate work to the owning agent automatically.
4. Use the `architect` to coordinate tasks spanning multiple ownership areas or touching shared integration points.
5. Integrate specialist results only after their ownership boundaries and assumptions are compatible.

Do not perform specialist-owned implementation directly in the parent/main agent when an appropriate project agent exists, except for trivial read-only inspection, summarization, or mechanical edits that do not alter behavior.

If ownership is uncertain, route to `architect` first.

Do not create a new agent merely because a task spans multiple areas. Use the existing agents unless a genuinely missing responsibility is identified.

---

## Agent routing table

### `architect`

Use `architect` when the task involves any of the following:

* architecture or architecture changes;
* decomposition of work spanning multiple agents;
* shared contracts or types;
* `quiz/application.py`;
* transaction orchestration across domain and persistence;
* integration between domain, persistence, authentication, views, or polling;
* shared settings or root routing;
* dependency changes;
* Docker/deployment structure;
* shared fixtures;
* migration ordering across independently developed changes;
* conflicts or ambiguity between specialist implementations;
* final integration review;
* determining ownership when routing is unclear.

The `architect` is the integration owner.

The `architect` should delegate specialist work rather than implementing all specialist concerns itself.

---

### `game_engine`

Use `game_engine` for pure game behavior, including:

* domain state transitions;
* legality rules;
* prerequisites;
* canonical puzzle completion;
* correct-answer behavior;
* Skip semantics;
* rewards as domain decisions;
* Freeze rules;
* Challenge rules;
* Music Quiz domain behavior;
* Uno Reverse domain behavior;
* timer semantics at the domain level;
* first-valid-answer race semantics;
* pure domain tests.

`game_engine` must not own:

* Django ORM implementation;
* authentication;
* authorization;
* HTTP views;
* templates;
* database transaction orchestration;
* deployment;
* application-wide integration.

If a game rule requires persistence or transaction behavior, `game_engine` defines the rule and contract, while `architect` and `persistence_security` coordinate its implementation.

---

### `persistence_security`

Use `persistence_security` for:

* Django models;
* schema design;
* migrations;
* SQLite configuration;
* database constraints;
* transaction guarantees;
* idempotency persistence;
* attempts and event persistence;
* rewards/progression persistence;
* authentication;
* authorization;
* session-derived team identity;
* team isolation;
* private-media protection;
* immutable run snapshots;
* backup/recovery persistence concerns;
* security-focused implementation tests.

`persistence_security` does not redefine game rules. It implements and enforces persistence/security requirements defined by the specifications, domain, and application layer.

Transaction boundaries shared with application orchestration require `architect` coordination.

---

### `test_invariants`

Use `test_invariants` for independent cross-cutting verification, especially:

* team-isolation tests;
* authorization bypass attempts;
* concurrency races;
* Music Quiz first-winner verification;
* duplicate/idempotent command behavior;
* stale run/question submissions;
* rollback guarantees;
* exactly-once rewards;
* restart/recovery behavior;
* snapshot stability;
* private-media isolation;
* browser-level polling races;
* HTMX poll-versus-command behavior;
* adversarial integration tests;
* recovery and backup verification.

`test_invariants` should test the contracts implemented by other agents rather than redesigning those contracts.

A specialist may add focused tests for its own code. `test_invariants` owns cross-cutting, adversarial, and integration-level invariant verification.

---

# Automatic routing examples

Apply these mappings without requiring the user to name agents.

| Requested work                                  | Required routing                                                                               |
| ----------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| Change a game rule                              | `game_engine`                                                                                  |
| Add/change a Django model                       | `persistence_security`                                                                         |
| Change authentication or team isolation         | `persistence_security`                                                                         |
| Implement a transaction spanning rules + models | `architect` coordinating `game_engine` and `persistence_security`                              |
| Implement Music Quiz winner logic               | `architect` + `game_engine` + `persistence_security`; `test_invariants` verifies race behavior |
| Add HTMX polling UI only                        | `architect` unless ownership is explicitly narrower in `docs/architecture.md`                  |
| Debug concurrent double rewards                 | `architect` coordinates `persistence_security`; `test_invariants` reproduces/verifies          |
| Add domain-only prerequisite logic              | `game_engine`                                                                                  |
| Modify Docker/Compose/dependencies/settings     | `architect`                                                                                    |
| Security review                                 | `persistence_security` + `test_invariants`                                                     |
| Cross-cutting feature                           | `architect` decomposes and delegates                                                           |
| Unclear ownership                               | `architect` decides                                                                            |

---

## Multi-agent execution rules

When a task spans multiple ownership areas, the `architect` must first establish:

1. the required contracts;
2. which agent owns each part;
3. shared/high-conflict files;
4. edit order where concurrent editing would be unsafe.

Parallelize only work that has non-overlapping ownership and file boundaries.

Do not allow multiple agents to concurrently edit the same shared/high-conflict file.

Agents must inspect existing repository state before editing. They must not assume another agent's work has not already changed a file.

When specialist work reveals an incompatible assumption:

* stop modifying the conflicting area;
* report the conflict to `architect`;
* resolve the contract first;
* then continue.

Do not overwrite another agent's implementation merely because a specialist prefers a different design.

---

## Shared and high-conflict integration points

The following require `architect` coordination and one assigned editor at a time:

* `quiz/application.py`;
* shared domain types;
* Django settings;
* root routes;
* project dependencies;
* `Dockerfile`;
* `compose.yaml`;
* shared fixtures;
* migration ordering;
* cross-agent public contracts;
* files explicitly identified as shared in `docs/architecture.md`.

Authentication-view files and specialist test files must have explicit ownership before parallel work.

The ownership table in `docs/architecture.md` remains authoritative for file-level ownership where it is more specific than this document.

---

## Agent completion requirements

A delegated agent must report back:

* files changed;
* contracts or assumptions relied upon;
* tests added or updated;
* validation performed;
* unresolved issues;
* any work discovered outside its ownership.

The integrating agent must inspect specialist results rather than assuming success merely because the specialist completed.

For multi-agent tasks, final integration must verify that domain, persistence, web, and tests agree on the same behavior.

---

## First implementation milestone

The first milestone is complete only when the vertical slice is green and demonstrates:

* authenticated Team A access;
* rejection of Team B resource access;
* server-side answer validation;
* wrong-answer persistence without progression;
* atomic canonical completion on a correct answer;
* configurable reward application;
* sequential advancement from puzzle 1 to puzzle 2;
* immutable/append-only event recording through supported application behavior;
* correct state after reload.

Do not begin Freeze, Music Quiz, Challenge, Uno Reverse, or polished calendar work before this milestone is stable unless the user explicitly reprioritizes.

For this milestone, expected routing is:

* `architect`: coordination, application transaction boundary, shared integration, polling/view integration;
* `game_engine`: answer/completion/progression domain behavior;
* `persistence_security`: models, migrations, transactions, authentication, authorization, isolation, snapshots/event persistence;
* `test_invariants`: cross-team isolation, rollback, concurrency, recovery, and adversarial verification.

The user should not need to repeat these agent assignments in implementation prompts.
