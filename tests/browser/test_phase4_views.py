"""Browser acceptance for synchronized phase-4 team and TV Music views."""

import asyncio
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import Client, LiveServerTestCase, override_settings

from quiz.application import force_complete_current, start_game
from quiz.contracts import Actor, AdminPuzzle, StartGame
from quiz.models import AccountRole


class PhaseFourBrowserTests(LiveServerTestCase):
    def setUp(self):
        if not os.environ.get("TEST_DATABASE_PATH"):
            self.skipTest("requires disposable file-backed TEST_DATABASE_PATH")
        self.snapshots = TemporaryDirectory()
        self.addCleanup(self.snapshots.cleanup)
        scope = override_settings(QUIZ_SNAPSHOT_ROOT=Path(self.snapshots.name))
        scope.enable()
        self.addCleanup(scope.disable)
        users = get_user_model()
        admin_user = users.objects.create_user("phase4-browser-admin")
        self.a_user = users.objects.create_user("phase4-browser-a")
        self.b_user = users.objects.create_user("phase4-browser-b")
        AccountRole.objects.create(user=admin_user, role="admin")
        AccountRole.objects.create(user=self.a_user, role="team", team_id="a")
        AccountRole.objects.create(user=self.b_user, role="team", team_id="b")
        admin = Actor(admin_user.pk, "admin")
        self.run_id = start_game(
            admin, StartGame(str(uuid4()), "christmas-2026-demo")
        ).run_id
        for number in range(1, 14):
            force_complete_current(
                admin,
                AdminPuzzle(str(uuid4()), self.run_id, "a", f"a-{number}"),
            )

        self.cookies = {}
        for team_id, user in (("a", self.a_user), ("b", self.b_user)):
            client = Client()
            client.force_login(user)
            self.cookies[team_id] = client.cookies["sessionid"].value

    async def _team_page(self, browser, team_id):
        context = await browser.new_context()
        host = urlparse(self.live_server_url).hostname
        await context.add_cookies(
            [
                {
                    "name": "sessionid",
                    "value": self.cookies[team_id],
                    "domain": host,
                    "path": "/",
                }
            ]
        )
        page = await context.new_page()
        await page.goto(f"{self.live_server_url}/team/")
        return context, page

    def test_both_teams_and_tv_advance_without_replacing_active_input(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                a_context, a_page = await self._team_page(browser, "a")
                b_context, b_page = await self._team_page(browser, "b")
                tv_context = await browser.new_context()
                tv_page = await tv_context.new_page()
                await tv_page.goto(f"{self.live_server_url}/overview/")
                try:
                    for page in (a_page, b_page, tv_page):
                        await page.get_by_text(
                            "Question 1 of 11", exact=False
                        ).wait_for()
                    field = a_page.locator("#music-answer-input")
                    await field.fill("still typing")
                    await field.focus()
                    await a_page.wait_for_timeout(1200)
                    self.assertEqual(await field.input_value(), "still typing")
                    self.assertTrue(
                        await field.evaluate("el => document.activeElement === el")
                    )

                    b_field = b_page.locator("#music-answer-input")
                    await b_field.fill("jingle bells")
                    await b_page.get_by_role(
                        "button", name="Submit Music answer"
                    ).click()
                    for page in (a_page, b_page, tv_page):
                        await page.get_by_text(
                            "Question 2 of 11", exact=False
                        ).wait_for(timeout=5000)
                    overview = await tv_page.locator("#overview-state").inner_text()
                    self.assertIn("Team B\n1", overview)
                    self.assertIn("Last point: Team B", overview)
                    self.assertEqual(await a_page.locator("#answer-input").count(), 0)
                finally:
                    await tv_context.close()
                    await b_context.close()
                    await a_context.close()
                    await browser.close()

        asyncio.run(check())
