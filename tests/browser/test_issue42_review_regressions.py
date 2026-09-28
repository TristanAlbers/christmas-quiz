"""Regression coverage for Codex review findings on issue #42."""

import asyncio
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import Client, LiveServerTestCase, override_settings

from quiz.application import initiate_challenge, start_game, submit_challenge_answer
from quiz.contracts import Actor, RunCommand, StartGame, SubmitChallengeAnswer
from quiz.domain.phase6 import CHALLENGE_GRACE_PERIOD_MS
from quiz.models import AccountRole, Challenge, Run


class Issue42ReviewRegressionBrowserTests(LiveServerTestCase):
    def setUp(self):
        if not os.environ.get("TEST_DATABASE_PATH"):
            self.skipTest("requires disposable file-backed TEST_DATABASE_PATH")
        self.snapshots = TemporaryDirectory()
        self.addCleanup(self.snapshots.cleanup)
        scope = override_settings(QUIZ_SNAPSHOT_ROOT=Path(self.snapshots.name))
        scope.enable()
        self.addCleanup(scope.disable)

        users = get_user_model()
        self.admin_user = users.objects.create_user("issue42-review-admin")
        self.team_user = users.objects.create_user("issue42-review-team")
        AccountRole.objects.create(user=self.admin_user, role="admin")
        AccountRole.objects.create(user=self.team_user, role="team", team_id="a")
        self.admin = Actor(self.admin_user.pk, "admin")
        self.team = Actor(self.team_user.pk, "team", "a")
        self.run_id = start_game(
            self.admin,
            StartGame(str(uuid4()), "christmas-2026-demo"),
        ).run_id

        client = Client()
        client.force_login(self.team_user)
        self.session_cookie = client.cookies["sessionid"].value

    async def _team_page(self, browser):
        context = await browser.new_context(viewport={"width": 390, "height": 844})
        host = urlparse(self.live_server_url).hostname
        await context.add_cookies(
            [
                {
                    "name": "sessionid",
                    "value": self.session_cookie,
                    "domain": host,
                    "path": "/",
                }
            ]
        )
        page = await context.new_page()
        await page.goto(f"{self.live_server_url}/team/")
        return context, page

    def test_team_playing_time_is_intentionally_not_rendered(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                context, page = await self._team_page(browser)
                try:
                    self.assertEqual(
                        await page.locator(".team-playing-time").count(), 0
                    )
                    self.assertEqual(
                        await page.locator("[data-gameplay-ms]").count(), 0
                    )
                    self.assertEqual(
                        await page.get_by_text("Speeltijd", exact=True).count(), 0
                    )
                finally:
                    await context.close()
                    await browser.close()

        asyncio.run(check())

    def test_resolved_challenge_feedback_does_not_reappear_in_fresh_session(self):
        initiate_challenge(self.team, RunCommand(str(uuid4()), self.run_id))
        challenge = Challenge.objects.get(run_id=self.run_id, status="active")
        Run.objects.filter(pk=self.run_id).update(
            gameplay_elapsed_ms=(
                challenge.started_gameplay_ms + CHALLENGE_GRACE_PERIOD_MS
            ),
            advent_clock_anchor=None,
        )

        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                observed_context, observed_page = await self._team_page(browser)
                fresh_context = None
                try:
                    await observed_page.locator(".challenge-status--active").wait_for(
                        timeout=5000
                    )
                    await asyncio.to_thread(
                        submit_challenge_answer,
                        self.team,
                        SubmitChallengeAnswer(
                            str(uuid4()),
                            self.run_id,
                            str(challenge.id),
                            challenge.question_id,
                            "rudolph",
                        ),
                    )

                    observed_result = observed_page.locator(
                        "[data-challenge-result-key]"
                    )
                    await observed_result.wait_for(state="visible", timeout=5000)
                    self.assertIn(
                        "You won the Challenge",
                        await observed_result.inner_text(),
                    )

                    fresh_context, fresh_page = await self._team_page(browser)
                    fresh_result = fresh_page.locator("[data-challenge-result-key]")
                    await fresh_result.wait_for(state="attached", timeout=5000)
                    self.assertFalse(await fresh_result.is_visible())
                    await fresh_page.wait_for_timeout(1200)
                    self.assertFalse(await fresh_result.is_visible())
                finally:
                    if fresh_context is not None:
                        await fresh_context.close()
                    await observed_context.close()
                    await browser.close()

        asyncio.run(check())
