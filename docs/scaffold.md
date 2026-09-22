# Scaffold operation and validation

Phase 1 provides a development demo: two team logins, two named admin accounts,
admin Start, and two sample puzzles per team. The demo is not the event package.

## First start

1. Copy `.env.example` to `.env`. Set a long random `DJANGO_SECRET_KEY`,
   `DJANGO_ALLOWED_HOSTS` for client hostnames/IPs, and `QUIZ_BIND_ADDRESS` to
   the LAN/VPN interface to publish. Set distinct team PINs of at least six
   digits and distinct admin passwords of at least 12 characters. Do not commit
   `.env`.
2. Create `var/` on the host with `mkdir -p var`. The container runs as UID/GID
   `1000:1000`; make this directory writable by that identity. If the host
   user has another UID, arrange ownership/ACLs first. The app keeps
   `quiz.sqlite3`, `snapshots/`, and future `backups/` here.
3. Run `docker compose up -d --build`. The container applies migrations at
   startup, provisions `team-a`, `team-b`, `admin-one`, and `admin-two` from
   the four `.env` credentials, then starts one Gunicorn `gthread` worker with
   four threads. To rotate a credential, change `.env` and run
   `docker compose up -d --force-recreate app`; `docker compose restart app`
   keeps the existing container environment. The team login is `/login/`; admins use
   `/admin-login/`. The game master starts the development demo at
   `/admin-game/`.
   `./games` is mounted read-only.
4. Inspect `docker compose ps` and `docker compose logs -f app`. The health
   check queries `http://127.0.0.1:8000/health/` inside the container.

Compose sets `DEBUG=False`. WhiteNoise serves collected CSS and the bundled
HTMX 2.0.10 file from the image; `collectstatic` runs during image build.
The health response contains no game state and does not test database
readiness. Compose reports unhealthy state but does not restart a still-running
process by itself.

Do not run these startup or migration commands against an existing event
`./var` merely to validate a change. Use a separate Compose project and an
override that bind-mounts a disposable runtime directory at `/app/var`.

## Validation

Use a disposable runtime when an event database may exist. In a fresh shell,
create an override and set a distinct Compose project and port before running
the commands below:

```sh
mkdir -p /tmp/christmas-quiz-validation-var
cat > /tmp/christmas-quiz-validation.override.yaml <<'YAML'
services:
  app:
    volumes:
      - /tmp/christmas-quiz-validation-var:/app/var
      - ./games:/app/games:ro
  dev:
    volumes:
      - /tmp/christmas-quiz-validation-var:/app/var
      - ./games:/app/games:ro
YAML
export COMPOSE_FILE=compose.yaml:/tmp/christmas-quiz-validation.override.yaml
export COMPOSE_PROJECT_NAME=christmas_quiz_validation
export QUIZ_PORT=18080
docker compose config --quiet
```

Make the temporary runtime writable by the container's UID/GID `1000:1000`.
The commands below then target only that isolated project. Run Chromium using
the disposable file-backed database command in `tests/browser/README.md`.

```sh
docker compose --profile dev build app dev
docker compose up -d app
docker compose ps
docker compose exec app python manage.py check
docker compose exec app python manage.py makemigrations --check --dry-run
docker compose exec app python manage.py test tests.integration.test_scaffold
docker compose run --rm --entrypoint ruff dev check .
curl -f http://127.0.0.1:18080/health/
curl -f http://127.0.0.1:18080/
# Request the hashed /static/quiz/... URLs emitted by the page, too.
```

The `dev` image includes Ruff and Playwright with Chromium for later browser
tests. It puts Ruff's cache under `/tmp` and Chromium under `/ms-playwright` so
both work as the non-root container user. Check the browser launch with:

```sh
docker compose run --rm --entrypoint python dev -c 'from playwright.sync_api import sync_playwright; p = sync_playwright().start(); b = p.chromium.launch(); print(b.version); b.close(); p.stop()'
```

The `app` image stays small. A custom host bind address or port changes the
curl address/port.
