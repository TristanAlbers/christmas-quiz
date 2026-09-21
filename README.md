# Christmas Escape Room Quiz

A self-hosted Django application for two isolated teams, two game masters, and
a public TV view. The current implementation is an **application scaffold**:
it starts, serves a health endpoint and local static files, and has no login,
puzzles, or gameplay yet.

For setup, Compose commands, validation, and persistent-directory permissions,
read [docs/scaffold.md](docs/scaffold.md). The approved architecture is in
[docs/architecture.md](docs/architecture.md), and the next slice's contracts and
exact file ownership are in [docs/contracts-first-slice.md](docs/contracts-first-slice.md).

The game rules are governed by
[christmas-2026-game-rules-state-semantics.md](christmas-2026-game-rules-state-semantics.md),
followed by [Design.md](Design.md), [Views.md](Views.md), and
[Game States.md](Game%20States.md). Repository work follows [AGENTS.md](AGENTS.md).
