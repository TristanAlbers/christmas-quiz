# Browser acceptance

Run Chromium against a disposable, file-backed SQLite test database from the
freshly built `dev` image:

```sh
docker compose --profile dev build dev
docker compose run --rm \
  -e TEST_DATABASE_PATH=/tmp/christmas-quiz-browser.sqlite3 \
  dev test tests.browser.test_live_sync
```

The Django test runner creates and destroys this test database. The live server
and Playwright share only that test database; they never use `./var/quiz.sqlite3`.
The tests use a temporary snapshot directory and close the browser after each
case. `DEBUG=False` is inherited from the Compose dev service.
