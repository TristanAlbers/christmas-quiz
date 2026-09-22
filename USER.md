# Using the Christmas Quiz today

This guide describes the **phase 1 development demo** that is implemented now.
It has two isolated teams, two named game masters, and two sample puzzles per
team. It is not the authored Christmas event, and completing sample puzzle 2
does not finish the game.

## Set up the server

The Linux host needs Docker and Docker Compose. From the repository root:

1. Copy `.env.example` to `.env` and replace every placeholder. Keep `.env`
   private; it is ignored by Git.
2. Create `./var` and make it writable by UID/GID `1000:1000`, the account used
   inside the container. This directory holds the SQLite database and pinned
   game snapshots. Keep it on local persistent storage.
3. Run `docker compose up -d --build`. Startup applies migrations, provisions
   the four accounts below, and starts Gunicorn. It mounts `./games` read only.
4. Run `docker compose ps` and `docker compose logs --tail=50 app`. Open
   `http://<configured-host>:<QUIZ_PORT>/health/` for a basic service check.
   The health response does not verify the database or game state.

The `.env` settings are:

| Variable | Set it to |
| --- | --- |
| `DJANGO_SECRET_KEY` | A long random secret. Keep it stable across restarts so existing sessions remain valid. |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hostnames or IP addresses that players will actually use. |
| `QUIZ_BIND_ADDRESS` | The LAN/VPN interface to publish on. The example's `127.0.0.1` allows only local access. |
| `QUIZ_PORT` | Host port, default `8000`; the container listens on port `8000`. |
| `QUIZ_TEAM_A_PIN`, `QUIZ_TEAM_B_PIN` | Separate numeric PINs, each at least six digits. |
| `QUIZ_ADMIN_ONE_PASSWORD`, `QUIZ_ADMIN_TWO_PASSWORD` | Separate passwords, each at least 12 characters. |

Compose requires the four credential variables. It fixes `DJANGO_DEBUG=false`
and stores the database at `/app/var/quiz.sqlite3`. The example PIN values are
deliberately invalid placeholders; replace them before starting. Account
provisioning runs on **every** app start. To rotate a credential, change `.env`
and recreate the app container with `docker compose up -d --force-recreate app`.
`docker compose restart app` reuses the existing container environment and
does **not** load changed `.env` values.

## Log in and play the demo

Open the home page at `/`. Teams use `/login/`: choose Team A or Team B and
enter that team's PIN. The accounts are named `team-a` and `team-b`, but the
team login form asks for a team choice and PIN. Game masters use
`/admin-login/` with username `admin-one` or `admin-two` and the matching
password. After login, follow the home-page link to the Team or Admin view.
Log out with the button on the page.

Before Start, a team view shows `READY` and no puzzle. A game master opens
`/admin-game/` and presses **Start development demo**. The current admin UI
starts only package ID `christmas-2026-demo`; it has no package selector.
Start opens puzzle 1 for both teams. A second Start does not create another
active run.

Each team sees only its own current puzzle, points, completed numbers, and
earned fragments. A wrong answer is recorded and leaves the team on the same
puzzle with no point change. A correct answer completes that puzzle, applies
its configured point reward and fragment once, and advances to the next puzzle.
For the supplied demo, Team A starts with 3 points and receives 4 points and
`DEMO-A-STAR` after puzzle 1, then sees puzzle 2. Team B progresses separately.
The browser polls the server every 500 ms while visible; reloading or logging
back in reads persisted state. Team identity and answer correctness are decided
by the server.

The demo defines hints in its package, but there is no Hint purchase, reveal,
or admin hint action yet. There is no Skip, pause, attack, Challenge, Music Quiz,
TV overview, or finished-game view in this phase. Completing sample puzzle 2
leaves the team with no further sample puzzle; it does not mark either team or
the global game finished.

## Edit the demo before Start

The only package selectable through the current admin UI is
[`games/christmas-2026-demo/game.json`](games/christmas-2026-demo/game.json).
Edit that JSON and its referenced files under the same package directory
**before** starting a run. The package is declarative data; it cannot execute
Python code. Credentials belong in `.env`, never in a package.

The top level requires exactly `schema_version: 1`, `package_id`,
`initial_points`, and `teams`. `initial_points` is a nonnegative integer.
`teams` requires exactly `a` and `b`. Each team has a `puzzles` list with 2–25
entries numbered sequentially from 1. Each puzzle requires `id`, `number`,
`title`, `body`, `validator`, `reward_points`, `hint`, `fragment`, and `media`.
The ID uses letters, numbers, `_`, or `-`; `reward_points` is a nonnegative
integer. `hint` and `fragment` are text or `null`; `media` is a list of
relative paths within the package. The supplied demo's private images are
`a/star.png` and `b/sky.png`.

The supported validators are:

| Validator | Comparison |
| --- | --- |
| `{"type": "text_exact", "answer": "..."}` | Trims surrounding whitespace and ignores case. Internal whitespace still matters. |
| `{"type": "number_exact", "answer": "..."}` | Compares finite decimal values, so `3`, `3.0`, and `+03` are equal. |

For example, this is a valid puzzle entry inside Team A's `puzzles` list:

```json
{
  "id": "a-1",
  "number": 1,
  "title": "North star",
  "body": "Enter the colour shown in your image.",
  "validator": {"type": "text_exact", "answer": "red"},
  "reward_points": 4,
  "hint": "The colour starts with R.",
  "fragment": "DEMO-A-STAR",
  "media": ["a/star.png"]
}
```

Use the linked `game.json` for a complete valid package with both teams and
all required puzzle entries. Media paths must stay within the package; Start
rejects missing files, symlinks, and individual files larger than 20 MB.

Start validates the package, copies its JSON and every referenced media file
into a digest-checked snapshot under `./var/snapshots`, and pins that snapshot
to the run. Editing or deleting the source package **after** Start does not
change the active run. The app serves private media from the pinned snapshot
only to the owning team while that asset belongs to its current visible
puzzle. Private media is never served from the public static directory.
The current UI cannot switch to a newly named package; a general package
selection and authoring workflow is planned for a later phase.

## Restart, recovery, and validation

`docker compose restart app` restarts the **server process**. It keeps the
active run because `./var/quiz.sqlite3` and `./var/snapshots` are persistent.
A browser refresh or login after restart reads the saved attempts, rewards,
fragments, and current puzzle. Do not edit or delete the database or pinned
snapshot directories while a run is active.

Restarting the server is **not** resetting or restarting the game. Phase 1 has
no supported Reset button or command, and a started run cannot be returned to
`READY` through the UI. Do not delete SQLite files or snapshots as a reset
workaround; that would discard history and bypass the game's future reset
rules. Admin reset is planned for phase 2. A tested backup and restore
procedure is also not available yet.

For validation, use a separate Compose project and disposable `/app/var`
mount. Follow the exact isolation setup in [docs/scaffold.md](docs/scaffold.md)
before running migrations or tests, so an existing event database is not
touched. After that setup, the phase 1 checks are:

```sh
docker compose --profile dev build app dev
docker compose up -d app
docker compose exec app python manage.py check
docker compose exec app python manage.py makemigrations --check --dry-run
docker compose run --rm --entrypoint ruff dev check .
docker compose run --rm -e TEST_DATABASE_PATH=/tmp/quiz-phase1-tests.sqlite3 \
  dev test tests.domain tests.integration tests.security
docker compose run --rm -e TEST_DATABASE_PATH=/tmp/quiz-phase1-browser.sqlite3 \
  dev test tests.browser.test_live_sync
```

The two test databases are disposable file-backed SQLite databases created by
Django's test runner. The browser suite uses Chromium and an isolated live
server; it exercises real polling, answer submission, and reconnect behavior.
