# Scaffold operation and validation

This is an application skeleton. It serves a public placeholder page and a
small `/health/` response; no game or login workflow has been built yet.

## First start

1. Copy `.env.example` to `.env`. Set a long random `DJANGO_SECRET_KEY`,
   `DJANGO_ALLOWED_HOSTS` for client hostnames/IPs, and `QUIZ_BIND_ADDRESS` to
   the LAN/VPN interface to publish. Do not commit `.env`.
2. Create `var/` on the host with `mkdir -p var`. The container runs as UID/GID
   `1000:1000`; make this directory writable by that identity. If the host
   user has another UID, arrange ownership/ACLs first. The app keeps
   `quiz.sqlite3`, future `snapshots/`, and future `backups/` here.
3. Run `docker compose up -d --build`. The container applies migrations at
   startup, then starts one Gunicorn `gthread` worker with four threads.
   `./games` is mounted read-only.
4. Inspect `docker compose ps` and `docker compose logs -f app`. The health
   check queries `http://127.0.0.1:8000/health/` inside the container.

Compose sets `DEBUG=False`. WhiteNoise serves collected CSS and the bundled
HTMX 2.0.10 file from the image; `collectstatic` runs during image build.
The health response contains no game state and does not test database
readiness. Compose reports unhealthy state but does not restart a still-running
process by itself.

## Validation

```sh
docker compose build app
docker compose up -d app
docker compose ps
docker compose exec app python manage.py check
docker compose exec app python manage.py makemigrations --check --dry-run
docker compose exec app python manage.py test tests.integration.test_scaffold
docker compose run --rm --entrypoint ruff dev check .
curl -f http://127.0.0.1:8000/health/
curl -f http://127.0.0.1:8000/
# Request the hashed /static/quiz/... URLs emitted by the page, too.
```

The `dev` image includes Ruff and Playwright with Chromium for later browser
tests. Use `docker compose run --rm --entrypoint python dev -m playwright --version`
to check its browser dependency. The `app` image stays small. A custom host
bind address or port changes the curl address/port.
