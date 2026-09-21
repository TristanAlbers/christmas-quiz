# Codex agent setup for the Christmas Quiz

This package contains four project-scoped Codex agents and shared repository instructions tailored to the Christmas Escape Room Quiz specifications.

## Included files

```text
AGENTS.md
.codex/
├── config.toml
└── agents/
    ├── architect.toml
    ├── game_engine.toml
    ├── persistence_security.toml
    └── test_invariants.toml
```

The agent files intentionally do not select a model. They inherit the model and reasoning settings from the parent Codex session, which keeps the setup compatible with the models available on your current plan.

## Install

Copy `AGENTS.md` and the complete `.codex` directory into the root of the implementation repository. Keep the four specification Markdown files at the repository root, or update the paths in `AGENTS.md` if you move them.

Start a new Codex session from the repository root after copying the files. Codex reads `AGENTS.md` once when a run/session starts.

## Recommended first prompt

```text
Start the implementation of the Christmas Escape Room Quiz as a multi-agent project.

Act as the lead integrator and use the architect, game_engine,
persistence_security, and test_invariants custom agents.

First inspect the repository and all four specification documents. Have the
architect establish the minimal architecture, module boundaries, shared
contracts, decision record, and a staged implementation plan. Do not let agents
choose conflicting interpretations of the specifications.

Then implement only the first vertical slice:
login as Team A -> retrieve Team A state -> show puzzle 1 -> persist a wrong
attempt without advancing -> accept the correct answer -> execute canonical
completion atomically -> award the configured reward -> advance to puzzle 2 ->
record an immutable event -> reload the persisted state.

Include a security test proving Team A cannot read or modify Team B state and
transaction/integration tests for completion. Do not implement Freeze, Music
Quiz, Challenge, Uno Reverse, or visual polish yet.

Before parallel edits, assign file/module ownership and identify shared
contracts. Have the architect review and integrate all work, run the full
relevant validation, and report decisions, changed files, test results, and
remaining risks.
```

## Suggested expansion order

After the first vertical slice is stable:

1. Sequential progression and configuration validation.
2. Admin monitoring and basic controls.
3. Points and Hint tokens.
4. Immediate Skip action through canonical completion.
5. Freeze and recoverable gameplay timers.
6. Uno Reverse.
7. Music Quiz.
8. Challenge.
9. Fragments and final puzzle.
10. Emergency tooling and visual polish.

The dedicated team frontend, admin/TV frontend, and game-package agents are intentionally not included yet. Add them after the backend contracts and first vertical slice are stable.
