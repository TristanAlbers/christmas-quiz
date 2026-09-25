"""Phase 6 Challenge presentation and polling-stability browser acceptance."""

import asyncio
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import Client, LiveServerTestCase, override_settings

from quiz.application import (
    get_team_state,
    initiate_challenge,
    start_game,
    submit_challenge_answer,
)
from quiz.contracts import Actor, RunCommand, StartGame, SubmitChallengeAnswer
from quiz.models import AccountRole, Challenge, Run, TeamRun


class PhaseSixBrowserTests(LiveServerTestCase):
    def setUp(self):
        if not os.environ.get("TEST_DATABASE_PATH"):
            self.skipTest("requires disposable file-backed TEST_DATABASE_PATH")
        self.snapshots = TemporaryDirectory()
        self.addCleanup(self.snapshots.cleanup)
        scope = override_settings(QUIZ_SNAPSHOT_ROOT=Path(self.snapshots.name))
        scope.enable()
        self.addCleanup(scope.disable)

        users = get_user_model()
        self.admin_user = users.objects.create_user("phase6-browser-admin")
        self.a_user = users.objects.create_user("phase6-browser-a")
        self.b_user = users.objects.create_user("phase6-browser-b")
        AccountRole.objects.create(user=self.admin_user, role="admin")
        AccountRole.objects.create(user=self.a_user, role="team", team_id="a")
        AccountRole.objects.create(user=self.b_user, role="team", team_id="b")
        self.admin = Actor(self.admin_user.pk, "admin")
        self.a = Actor(self.a_user.pk, "team", "a")
        self.b = Actor(self.b_user.pk, "team", "b")
        self.run_id = start_game(
            self.admin, StartGame(str(uuid4()), "christmas-2026-demo")
        ).run_id

        self.cookies = {}
        for name, user in (
            ("admin", self.admin_user),
            ("a", self.a_user),
            ("b", self.b_user),
        ):
            client = Client()
            client.force_login(user)
            self.cookies[name] = client.cookies["sessionid"].value

    async def _page(self, browser, path, viewport, cookie=None):
        context = await browser.new_context(viewport=viewport)
        if cookie:
            host = urlparse(self.live_server_url).hostname
            await context.add_cookies(
                [{"name": "sessionid", "value": cookie, "domain": host, "path": "/"}]
            )
        page = await context.new_page()
        await page.goto(f"{self.live_server_url}{path}")
        return context, page

    async def _finish_grace_period(self):
        await asyncio.to_thread(
            Run.objects.filter(pk=self.run_id).update,
            gameplay_elapsed_ms=15_000,
            advent_clock_anchor=None,
        )

    def test_free_start_gathering_tv_takeover_and_wrong_attempt_stability(self):
        TeamRun.objects.filter(run_id=self.run_id, team_id="a").update(points=0)

        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                a_context, a_page = await self._page(
                    browser,
                    "/team/",
                    {"width": 390, "height": 844},
                    self.cookies["a"],
                )
                b_context, b_page = await self._page(
                    browser,
                    "/team/",
                    {"width": 390, "height": 844},
                    self.cookies["b"],
                )
                tv_context, tv_page = await self._page(
                    browser,
                    "/overview/",
                    {"width": 1920, "height": 1080},
                )
                try:
                    await a_page.get_by_role(
                        "button", name="Shop Power-ups & sabotage"
                    ).click()
                    challenge_item = a_page.locator(".shop-item--challenge")
                    challenge_text = await challenge_item.inner_text()
                    self.assertIn("free & available", challenge_text)
                    self.assertNotIn("need", challenge_text.lower())
                    start = challenge_item.get_by_role(
                        "button", name="Start free Challenge"
                    )
                    self.assertFalse(await start.is_disabled())

                    run_field = challenge_item.locator('input[name="run_id"]')
                    await run_field.evaluate(
                        "(el, value) => el.value = value", str(uuid4())
                    )
                    await start.click()
                    await a_page.locator("#action-feedback").get_by_text(
                        "Action rejected: stale run", exact=True
                    ).wait_for(timeout=5000)
                    await run_field.evaluate(
                        "(el, value) => el.value = value", self.run_id
                    )
                    await start.click()

                    for page in (a_page, b_page):
                        stage = page.locator(".challenge-stage--starting")
                        await stage.wait_for(timeout=5000)
                        self.assertEqual(
                            await page.locator("#challenge-answer-input").count(), 0
                        )
                    self.assertIn(
                        "You started this Challenge",
                        await a_page.locator(".challenge-stage").inner_text(),
                    )
                    self.assertIn(
                        "You were challenged",
                        await b_page.locator(".challenge-stage").inner_text(),
                    )
                    await tv_page.get_by_text(
                        "Gather around — the Challenge is about to begin",
                        exact=True,
                    ).wait_for(timeout=5000)
                    tv_starting = await tv_page.locator(".challenge-overview").inner_text()
                    self.assertIn("Challenge · 1 of 2", tv_starting)
                    self.assertIn("Team A challenged Team B", tv_starting)
                    self.assertNotIn("Reindeer roll call", tv_starting)

                    await self._finish_grace_period()
                    for page in (a_page, b_page):
                        await page.locator("#challenge-answer-input").wait_for(
                            timeout=5000
                        )
                    await tv_page.get_by_text("Reindeer roll call", exact=True).wait_for(
                        timeout=5000
                    )
                    tv_live = await tv_page.locator(".challenge-overview").inner_text()
                    self.assertIn("glowing red nose", tv_live)
                    self.assertIn("First correct answer", tv_live)

                    answer = a_page.locator("#challenge-answer-input")
                    request_id = a_page.locator(
                        '.challenge-answer-form input[name="request_id"]'
                    )
                    old_request_id = await request_id.input_value()
                    await answer.fill("snata")
                    await answer.focus()
                    await answer.evaluate(
                        """el => {
                            el.setSelectionRange(2, 2);
                            window.__challengeAnswer = el;
                        }"""
                    )
                    await a_page.wait_for_timeout(1100)
                    self.assertTrue(
                        await answer.evaluate("el => window.__challengeAnswer === el")
                    )
                    await answer.press("Enter")
                    await a_page.get_by_text(
                        "Incorrect Challenge answer. Keep trying."
                    ).wait_for(timeout=5000)
                    self.assertTrue(
                        await answer.evaluate(
                            "el => window.__challengeAnswer === el "
                            "&& document.activeElement === el"
                        )
                    )
                    self.assertEqual(await answer.input_value(), "snata")
                    self.assertEqual(
                        await answer.evaluate("el => el.selectionStart"), 2
                    )
                    self.assertNotEqual(await request_id.input_value(), old_request_id)

                    challenge = await asyncio.to_thread(
                        Challenge.objects.get, run_id=self.run_id
                    )
                    await asyncio.to_thread(
                        submit_challenge_answer,
                        self.b,
                        SubmitChallengeAnswer(
                            str(uuid4()),
                            self.run_id,
                            str(challenge.id),
                            challenge.question_id,
                            "rudolph",
                        ),
                    )
                    await a_page.get_by_text("The rival team won", exact=True).wait_for(
                        timeout=5000
                    )
                    await b_page.get_by_text(
                        "You won the Challenge", exact=True
                    ).wait_for(timeout=5000)
                    await tv_page.get_by_text(
                        "Advent Quiz in progress", exact=True
                    ).wait_for(timeout=5000)
                    self.assertEqual(
                        await tv_page.locator(".challenge-overview").count(), 0
                    )
                    for page in (a_page, b_page, tv_page):
                        self.assertTrue(
                            await page.evaluate(
                                "document.documentElement.scrollWidth "
                                "<= window.innerWidth"
                            )
                        )
                finally:
                    await tv_context.close()
                    await b_context.close()
                    await a_context.close()
                    await browser.close()

        asyncio.run(check())

    def test_initiator_win_freeze_admin_monitoring_and_tv_state(self):
        initiate_challenge(self.a, RunCommand(str(uuid4()), self.run_id))

        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                b_context, b_page = await self._page(
                    browser,
                    "/team/",
                    {"width": 390, "height": 844},
                    self.cookies["b"],
                )
                admin_context, admin_page = await self._page(
                    browser,
                    "/admin-game/",
                    {"width": 768, "height": 1024},
                    self.cookies["admin"],
                )
                tv_context, tv_page = await self._page(
                    browser, "/overview/", {"width": 1920, "height": 1080}
                )
                try:
                    monitor = admin_page.locator(".admin-challenge")
                    await monitor.wait_for()
                    text = await monitor.inner_text()
                    self.assertIn("Challenge 1 of 2", text)
                    self.assertIn("Team A", text)
                    self.assertIn("initiator", text.lower())
                    self.assertIn("Team B", text)
                    self.assertIn("No points charged", text)
                    self.assertIn("Gathering period", text)
                    await tv_page.locator(".challenge-overview--starting").wait_for(
                        timeout=5000
                    )

                    await self._finish_grace_period()
                    await b_page.locator("#challenge-answer-input").wait_for(
                        timeout=5000
                    )
                    await admin_page.get_by_text(
                        "Puzzle is live.", exact=False
                    ).wait_for(timeout=5000)
                    await tv_page.get_by_text("Reindeer roll call", exact=True).wait_for(
                        timeout=5000
                    )
                    tv_text = (await tv_page.locator(".challenge-overview").inner_text())
                    self.assertIn("Team A challenged Team B", tv_text)
                    self.assertNotIn("rudolph", tv_text.lower())
                    self.assertNotIn("challenge-a-reindeer", tv_text)

                    challenge = await asyncio.to_thread(
                        Challenge.objects.get, run_id=self.run_id
                    )
                    await asyncio.to_thread(
                        submit_challenge_answer,
                        self.a,
                        SubmitChallengeAnswer(
                            str(uuid4()),
                            self.run_id,
                            str(challenge.id),
                            challenge.question_id,
                            "rudolph",
                        ),
                    )
                    await b_page.get_by_text(
                        "Your team is frozen", exact=True
                    ).wait_for(timeout=5000)
                    freeze_text = await b_page.locator(".freeze-message").inner_text()
                    self.assertIn("Your team is frozen", freeze_text)
                    self.assertNotIn("Reindeer roll call", freeze_text)
                    await admin_page.get_by_text("Team A won.", exact=False).wait_for(
                        timeout=5000
                    )
                    self.assertIn(
                        "direct five-minute Freeze", await monitor.inner_text()
                    )
                    await tv_page.get_by_text(
                        "Advent Quiz in progress", exact=True
                    ).wait_for(timeout=5000)
                    self.assertEqual(
                        await tv_page.locator(".challenge-overview").count(), 0
                    )
                    for page in (b_page, admin_page, tv_page):
                        self.assertTrue(
                            await page.evaluate(
                                "document.documentElement.scrollWidth "
                                "<= window.innerWidth"
                            )
                        )
                finally:
                    await tv_context.close()
                    await admin_context.close()
                    await b_context.close()
                    await browser.close()

        asyncio.run(check())

        state = get_team_state(self.b)
        self.assertEqual(state.team_state, "FREEZE")
