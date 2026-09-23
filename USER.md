# Using the Christmas Quiz today

This guide describes the **phase 3.1 development demo** that is implemented now.
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

Before Start, there is no active run. A team sees only `READY` and a waiting
message—no package names or state from an earlier game. A game master opens
`/admin-game/`, selects one valid discovered package, and presses **Start game**.
Invalid packages remain visible but disabled, with a concise diagnostic shown
only to administrators. Merely viewing this list does not create a snapshot.
An accepted Start creates a fresh run and immutable snapshot and opens puzzle 1
for both teams. Simultaneous or repeated Starts cannot create competing runs.

Each team sees only its own current puzzle, points, completed numbers, and
earned fragments. A wrong answer is recorded and leaves the team on the same
puzzle with no point change. A correct answer completes that puzzle, applies
its configured point reward and fragment once, and advances to the next puzzle.
For the supplied demo, Team A starts with 3 points and receives 4 points and
`DEMO-A-STAR` after puzzle 1, then sees puzzle 2. Team B progresses separately.
The browser polls the server every 500 ms while visible; reloading or logging
back in reads persisted state. Team identity and answer correctness are decided
by the server.

While the game is running, a team can buy a generic Hint token for the configured
cost (1 point in the demo). Tokens remain after progression. Using one on the
current puzzle reveals its hint only to that team and consumes one token. The
same hint cannot consume a second token. An admin can reveal it without using a
token. A team can Skip its current puzzle immediately for the configured cost
(2 points in the demo); Skip grants the same completion reward and fragment as
a correct answer. Insufficient points reject the purchase or Skip. There is no
Skip inventory.

The admin page shows both teams and supports pause/resume, signed point changes,
current-puzzle force completion, immediate Hint reveal, full reset, direct
Freeze, and unfreeze. Pausing blocks team gameplay and hides the current puzzle
until resume; it preserves each team's position, inventory, and exact effect
time remaining. Point removal cannot make a balance negative. **Reset full
game** asks for confirmation, archives the active run, preserves its snapshot,
facts, receipts, and audit history, and leaves no active replacement run. Teams
then see only the waiting state, while administrators return to package
selection. The next Start may choose the same or a different package and always
creates a fresh run and snapshot from that package's current source files. The
admin view polls every 500 ms.

During Advent play a team can immediately spend the configured Freeze cost (3
points in the demo) to Freeze its opponent for five minutes of Advent gameplay
time. Freeze is not inventory. A frozen team sees its state and authoritative
countdown, but cannot retrieve its puzzle, revealed Hint, answer/shop controls,
or private media. An admin can remove Freeze immediately. A team can buy one
active Uno Reverse (2 points in the demo); this is private to its owner and the
admins. A valid player Freeze consumes the target's Reverse, charges the
attacker, and Freezes the attacker instead. Admin Freeze applies directly and
does not consume Reverse.

The gameplay clock is persisted. Pause preserves remaining Freeze time across
refresh, disconnect, and restart. Unexpected downtime while the persisted state
is `ADVENT_QUIZ` counts as gameplay time; downtime while persistently `PAUSED`
does not. Client countdown values never authorize expiry. There is no Challenge,
Music Quiz, TV overview, or finished-game view in this phase.
Completing sample puzzle 2 leaves the team with no further sample puzzle; it
does not mark either team or the global game finished. A package extended to
puzzle 13 cannot progress beyond puzzle 12 until the mandatory Music Quiz is
implemented.

## Add or edit packages before Start

The admin READY page discovers direct package directories under `games/`, such
as [`games/christmas-2026-demo/game.json`](games/christmas-2026-demo/game.json).
The directory name and JSON `package_id` must match. Edit the JSON and its
referenced files under the same package directory **before** starting a run.
The package is declarative data; it cannot execute Python code. Credentials
belong in `.env`, never in a package. Rich authoring/import/export tools are not
implemented yet.

The phase 3 top level requires exactly `schema_version: 3`, `package_id`,
`initial_points`, `hint_cost`, `skip_cost`, `freeze_cost`,
`uno_reverse_cost`, and `teams`. All five point values are nonnegative integers.
Existing version 1 and 2 snapshots remain readable, but mechanics without a
snapshotted configured price are unavailable for those runs.
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
all required puzzle entries. Media paths must stay within the package.

Start validates the package, copies its JSON and every referenced media file
into a digest-checked snapshot under `./var/snapshots`, and pins that snapshot
to the run. Editing or deleting the source package **after** Start does not
change the active run. The app serves private media from the pinned snapshot
only to the owning team while that asset belongs to its current visible
puzzle. Private media is never served from the public static directory. Source
package edits or deletion cannot change or break an active run. After Reset,
editing a source package and selecting it again creates a different snapshot
whose new run sees the edited content.

## Restart, recovery, and validation

`docker compose restart app` restarts the **server process**. It keeps the
active run because `./var/quiz.sqlite3` and `./var/snapshots` are persistent.
A browser refresh or login after restart reads the saved attempts, rewards,
fragments, and current puzzle. Do not edit or delete the database or pinned
snapshot directories while a run is active.

Restarting the server is **not** resetting the game. An active Advent clock
continues across restart, while a paused clock stays stopped. Use the admin
**Reset full game** button to end the active run and return to package selection;
it does not create another run. Do not delete SQLite files or snapshots as a
reset workaround. Migration `0004_retire_legacy_ready_runs` safely deactivates
active READY shells created by older phase-2/phase-3 resets while preserving
their database rows and snapshot references. A tested backup and restore
procedure is not available yet.

For validation, use a separate Compose project and disposable `/app/var`
mount. Follow the exact isolation setup in [docs/scaffold.md](docs/scaffold.md)
before running migrations or tests, so an existing event database is not
touched. After that setup, the phase 3.1 checks are:

```sh
docker compose --profile dev build app dev
docker compose up -d app
docker compose exec app python manage.py check
docker compose exec app python manage.py makemigrations --check --dry-run
docker compose run --rm --entrypoint ruff dev check .
docker compose run --rm -e TEST_DATABASE_PATH=/tmp/quiz-phase31-tests.sqlite3 \
  dev test tests.domain tests.integration tests.security
docker compose run --rm -e TEST_DATABASE_PATH=/tmp/quiz-phase31-browser.sqlite3 \
  dev test tests.browser
```

The two test databases are disposable file-backed SQLite databases created by
Django's test runner. The browser suite uses Chromium and an isolated live
server; it exercises real polling, answer submission, and reconnect behavior.
