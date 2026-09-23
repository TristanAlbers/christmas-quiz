# Christmas Escape Room Quiz — Codex Instructions

## Project goal

Build a lightweight, self-hosted Christmas escape-room quiz for two isolated teams, two administrators, and a public TV overview.

Correctness, recoverability, team isolation, understandable implementation, and easy game-package configuration take priority over visual polish, speculative scalability, and model-usage savings. Usage optimization must never weaken an invariant, skip required specialist judgment, or reduce test coverage.

## Specification authority

Use this authority order:

1. `christmas-2026-game-rules-state-semantics.md` (or the duplicate `(1)` file if present) — normative game behavior and invariants.
2. `Design.md` — broader product and operational requirements.
3. `Views.md` — presentation targets and view requirements.
4. `Game States.md` — supporting state documentation.
5. `docs/architecture.md` — approved implementation architecture and ownership; it does not override higher-authority product rules.
6. Phase contracts/handoffs — implementation records for a named phase. A later contract may supersede only the portions it explicitly names.

Do not silently invent resolutions. Escalate genuine ambiguity to `architect`; ask the user only when authoritative project material cannot resolve it.

Known canonical interpretations include:
- global `FINISHED` occurs only after both teams complete puzzle 25;
- Skip is an immediate completion action, not stored inventory;
- `completed` is the canonical puzzle status.

## Non-negotiable architecture and correctness rules

- Backend state is authoritative; the frontend requests transitions and renders projections.
- Keep global quiz state separate from each team's activity state.
- `PAUSED` and `MUSIC_QUIZ` preserve underlying team state and timer semantics exactly as specified.
- Correct answers, player Skip, and admin force-completion share one canonical completion pipeline.
- Enforce sequential prerequisites in the backend.
- Resolve races at an atomic persistence boundary; first valid server-accepted transaction wins.
- Derive team identity only from authenticated server context.
- Enforce team isolation on every private read/write, including attempts, progression, points, effects, hints, fragments, inventory, puzzles, and private media.
- Keep balances nonnegative; purchases, rewards, attacks, one-time triggers, race resolution, receipts, and audit effects must be atomic where applicable.
- Timers are server-authoritative and recoverable across refresh/reconnect/restart.
- Preserve the append-only event/audit history through supported application behavior, including Reset.
- Snapshot/version active game configuration and referenced media; an active run reads only its immutable snapshot.
- Treat `games/*` packages as declarative data, never executable application code.
- Prefer one implementation of each business rule and conventional Django over speculative abstraction.
- Preserve the 500 ms authenticated HTMX polling architecture and the polling-control stability guidance in `docs/polling-ui-guideline.md`.

## Approved implementation baseline

- synchronous Django;
- Gunicorn WSGI;
- Django templates;
- locally bundled HTMX;
- SQLite;
- WhiteNoise;
- Docker Compose;
- one application container;
- persistent `./var` runtime data.

Architecture changes require `architect` review.

## Delivery principles

- Work in thin, complete vertical slices.
- Preserve unrelated user changes.
- Add/update automated tests with every behavior change.
- Test through public domain/application interfaces where practical.
- Never change a specified rule just to make a test pass.
- Do not broaden the authorized phase.
- Keep `USER.md`, relevant contracts, architecture notes, and `.env.example` accurate when behavior/configuration changes.
- Use focused local validation during implementation and the GitHub Actions full suite as the clean-environment gate.

## Repository / branch / PR workflow

For non-trivial implementation work, the parent/main routing agent owns the Git lifecycle. Specialists work on the assigned branch/worktree and do not create competing branches, commits, pushes, or PRs unless explicitly delegated.

When starting new work from `main`, create a short-lived feature branch. Reuse an existing suitable task branch for follow-up work. Preserve unrelated changes. Before handoff inspect the final diff, commit coherently, push, and create a PR targeting `main` when available.

Do not commit implementation directly to `main`, merge, enable auto-merge, alter branch protection, or delete branches unless the user explicitly asks.

## CI and deterministic verification

During implementation:
- run the smallest tests covering the changed behavior and nearby invariants;
- run Ruff on changed Python/smallest practical scope;
- run Django/migration checks when relevant;
- run browser tests locally when browser behavior is changed or needed to diagnose a failure.

Do not repeatedly run an unchanged full suite for reassurance.

GitHub Actions is the authoritative clean-environment full-suite gate. A green CI run is sufficient execution evidence for checks it already ran. Deterministic compute belongs in tests, Ruff, Django checks, browser tests, and CI; model reasoning should focus on implementation decisions, diagnosis, and coverage gaps.

When CI fails, inspect the failed step/log, route only to the implicated owner, reproduce narrowly when practical, fix, run focused validation, push, and let CI rerun. Do not fan out all specialists for one failure.

# Bounded specialist workflow

The project uses specialist agents for quality. Usage is reduced by narrowing assignments, not by removing expertise or weakening models.

## Core rule

A specialist assignment must be a bounded work packet. It should contain:

1. the concrete objective;
2. exact owned production/test files or modules;
3. the governing phase-contract/handoff sections;
4. only the normative/architecture sections needed for the assignment;
5. required input/output interfaces and invariants;
6. focused acceptance tests;
7. explicit out-of-scope areas.

The parent/architect must not ask every specialist to independently reacquire the whole repository, all specifications, all historical contracts, and all phase context.

A bounded packet does **not** lower specification authority. If the packet is ambiguous, contradictory, or appears incomplete in a way that could change correctness, the specialist must expand context and consult the authoritative source before acting.

## Staged participation

For a multi-area phase, use this default sequence:

1. **Contract pass — `architect`:** inspect authoritative material needed for the phase, settle shared contracts/decisions, assign exact files and edit order, and record a concise phase contract/handoff.
2. **Owned implementation — specialists:** `game_engine` and/or `persistence_security` implement only their concrete owned pieces with focused tests. They hand back results and stop unless a concrete issue requires re-entry.
3. **Integration — parent/`architect`:** integrate application orchestration, shared files, web/views/templates, fixtures, and documentation as assigned.
4. **Independent verification — `test_invariants`:** after integration, inspect the phase contract, diff, relevant tests, and CI evidence for adversarial gaps. It is not a continuous implementation participant.
5. **Full gate — CI:** run the complete deterministic suite once against the integrated PR state.
6. **Failure routing:** if a defect appears, reactivate only the owner of that concrete defect/ambiguity plus `test_invariants` when verification work is needed.

Do not keep all four agents active merely because a phase is cross-cutting. Parallelize only genuinely independent, non-overlapping work.

## Quality floor

The narrower workflow must retain:
- the same authoritative rules;
- specialist ownership of domain and persistence/security decisions;
- independent adversarial review where the phase has cross-cutting risk;
- focused tests by implementers;
- concurrency/isolation/recovery/browser tests where applicable;
- the complete CI gate;
- escalation to high-reasoning specialists for genuinely high-risk decisions.

Never trade away a correctness safeguard solely to reduce usage.

# Mandatory routing and ownership

The project agents under `.codex/agents/` are the default owners.

## `architect`

Use for:
- architecture or architecture changes;
- phase contracts/decomposition;
- shared types/contracts;
- `quiz/application.py`;
- transaction orchestration across domain/persistence;
- integration among domain, persistence, auth, views, polling;
- settings/root routes/dependencies/deployment;
- shared fixtures and migration ordering;
- cross-specialist conflicts/ambiguity;
- final integration review.

`architect` is the integration owner. It should make the minimum shared decisions, delegate specialist-owned work, integrate the results, and avoid shadow-implementing specialist concerns.

## `game_engine`

Use for pure game behavior:
- state transitions and legality;
- prerequisites;
- canonical completion;
- Skip/Hint/Freeze/Uno Reverse domain semantics;
- Music Quiz and Challenge domain behavior;
- rewards/fragments as domain decisions;
- timer semantics at domain level;
- first-valid-answer and first-finisher rules;
- focused pure domain tests.

It does not own Django ORM, auth, HTTP/templates, database transaction orchestration, deployment, or application-wide integration.

## `persistence_security`

Use for:
- Django models/schema/migrations;
- SQLite configuration/constraints/transactions;
- idempotency persistence;
- attempts/events/rewards/progression persistence;
- auth/authorization/session-derived team identity;
- team isolation and private media;
- immutable snapshots;
- concurrency/atomicity/recovery;
- focused persistence/security tests.

It implements approved rules; it does not redefine them. Shared transaction boundaries require `architect` coordination.

## `test_invariants`

Use after integration for independent cross-cutting verification, especially:
- team isolation / authorization bypass;
- real concurrency races;
- Music/Challenge first-winner behavior;
- duplicate/idempotent/stale commands;
- rollback/exactly-once rewards;
- restart/recovery/snapshot stability;
- private media isolation;
- polling/browser interaction races;
- requirements-to-tests gaps.

It tests contracts rather than redesigning them and does not edit production code unless explicitly reassigned.

## Routing examples

| Work | Routing |
| --- | --- |
| Routine phase-gate verification | Parent first; `test_invariants` only for independent adversarial judgment/gaps |
| Pure game-rule change | `game_engine` |
| Django model/migration | `persistence_security` |
| Authentication/team isolation | `persistence_security` |
| Transaction spanning rules + models | `architect` coordinates `game_engine` + `persistence_security` |
| Music Quiz winner implementation | contract by `architect`; domain by `game_engine`; atomic persistence by `persistence_security`; post-integration race review by `test_invariants` |
| HTMX/presentation-only change | `architect`/assigned presentation owner |
| Concurrent double reward | `persistence_security` diagnosis; `test_invariants` reproduces/verifies; `architect` only if shared orchestration contract changes |
| Docker/Compose/dependencies/settings | `architect` |
| Security review | `persistence_security` + independent `test_invariants` |
| Unclear ownership/shared conflict | `architect` |

# Model / reasoning policy

Configured defaults remain intentionally strong:
- `architect`: GPT-5.6 Sol / high;
- `game_engine`: GPT-5.6 Sol / high;
- `persistence_security`: GPT-5.6 Sol / high;
- `test_invariants`: GPT-5.6 Terra / medium;
- unconfigured subagents: Terra / medium.

Do not downgrade a high-risk specialist merely to save usage. Reduce usage through bounded context, staged participation, focused validation, and stopping completed specialists.

Use high reasoning where architecture, shared contracts, interacting state rules, idempotency, security, concurrency, snapshots, or recovery genuinely demand it. Do not invoke a high-effort specialist for formatting, documentation cleanup, deterministic command execution, or unrelated inspection.

# Verification fast path

For routine verification:
1. read the named phase gate, current phase contract/handoff, diff, relevant tests, and CI evidence;
2. run only missing/failing focused checks locally;
3. use green CI as authoritative evidence for the unchanged full gate;
4. stop if requirements are covered and evidence is green.

Expand context/routing only when evidence requires it:
- domain/state-rule failure -> `game_engine`;
- transaction/auth/isolation/recovery failure -> `persistence_security`;
- shared contract/architecture ambiguity -> `architect`;
- adversarial coverage gap -> `test_invariants`.

Do not summon all agents to independently repeat a green phase gate.

# Multi-agent integration rules

Before parallel edits, `architect` establishes contracts, owners, shared/high-conflict files, migration order, and unsafe edit order.

Only one editor at a time owns:
- `quiz/application.py`;
- shared domain/contracts;
- settings/root routes;
- dependencies;
- `Dockerfile` / `compose.yaml`;
- shared fixtures;
- migration ordering;
- other files identified as shared by `docs/architecture.md`.

A specialist encountering an incompatible assumption stops that conflicting edit, reports it to `architect`, resolves the contract, then continues. Never overwrite another agent's implementation just because a different design is preferred.

# Progress and handoff

The parent/main agent remains user-facing. For substantial work, report concise operational checkpoints when the work phase changes or a meaningful finding/failure occurs. Do not expose private chain-of-thought or narrate every command.

A specialist handoff reports:
- files changed;
- contract/assumptions relied on;
- focused tests added/run;
- validation result;
- unresolved issues or work outside ownership.

Final integration reports:
- what changed;
- important decisions;
- specialists used;
- validation/CI evidence;
- failures/skips;
- unresolved follow-up.

Do not claim success merely because a specialist returned successfully; inspect the integrated state and required evidence.
