"""Browser acceptance for issue #41's Dutch-first runtime surfaces."""

import asyncio
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import Client, LiveServerTestCase, override_settings

from quiz.application import start_game
from quiz.contracts import Actor, StartGame
from quiz.models import AccountRole


class Issue41DutchFirstBrowserTests(LiveServerTestCase):
    def setUp(self):
        if not os.environ.get("TEST_DATABASE_PATH"):
            self.skipTest("requires disposable file-backed TEST_DATABASE_PATH")
        self.snapshots = TemporaryDirectory()
        self.addCleanup(self.snapshots.cleanup)
        scope = override_settings(QUIZ_SNAPSHOT_ROOT=Path(self.snapshots.name))
        scope.enable()
        self.addCleanup(scope.disable)

        users = get_user_model()
        self.admin_user = users.objects.create_user("issue41-admin")
        self.team_user = users.objects.create_user("issue41-team")
        AccountRole.objects.create(user=self.admin_user, role="admin")
        AccountRole.objects.create(user=self.team_user, role="team", team_id="a")
        self.admin = Actor(self.admin_user.pk, "admin")
        start_game(self.admin, StartGame(str(uuid4()), "christmas-2026-demo"))

        self.team_cookie = self._session_cookie(self.team_user)
        self.admin_cookie = self._session_cookie(self.admin_user)

    def _session_cookie(self, user):
        client = Client()
        client.force_login(user)
        return client.cookies["sessionid"].value

    async def _authenticated_page(self, playwright, cookie, path, viewport):
        browser = await playwright.chromium.launch()
        context = await browser.new_context(viewport=viewport)
        host = urlparse(self.live_server_url).hostname
        await context.add_cookies(
            [{"name": "sessionid", "value": cookie, "domain": host, "path": "/"}]
        )
        page = await context.new_page()
        await page.goto(f"{self.live_server_url}{path}")
        return browser, context, page

    def test_team_runtime_is_dutch_and_hides_internal_state_names(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser, context, page = await self._authenticated_page(
                    playwright,
                    self.team_cookie,
                    "/team/",
                    {"width": 390, "height": 844},
                )
                try:
                    await page.get_by_role(
                        "button", name="Antwoord insturen"
                    ).wait_for()
                    html_lang = await page.locator("html").get_attribute("lang")
                    self.assertEqual(html_lang, "nl")
                    visible = await page.locator("body").inner_text()
                    self.assertIn("Uitloggen", visible)
                    self.assertIn("Antwoord", visible)
                    self.assertIn("Winkel", visible)
                    self.assertNotIn("ADVENT_QUIZ", visible)
                    self.assertNotIn("PUZZLE", visible)
                    self.assertNotIn("Submit answer", visible)
                    self.assertNotIn("Log out", visible)
                finally:
                    await context.close()
                    await browser.close()

        asyncio.run(check())

    def test_public_and_admin_surfaces_use_dutch_presentation_labels(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                overview_browser = await playwright.chromium.launch()
                overview_context = await overview_browser.new_context(
                    viewport={"width": 1920, "height": 1080}
                )
                overview = await overview_context.new_page()
                await overview.goto(f"{self.live_server_url}/overview/")
                try:
                    await overview.get_by_role("heading", name="Quizzmass").wait_for()
                    self.assertEqual(
                        await overview.locator("html").get_attribute("lang"), "nl"
                    )
                    public_text = await overview.locator("#overview-state").inner_text()
                    self.assertIn("De adventrace is begonnen", public_text)
                    self.assertIn("Adventkalender", public_text)
                    self.assertNotIn("ADVENT_QUIZ", public_text)
                    self.assertNotIn("Advent calendar", public_text)
                finally:
                    await overview_context.close()
                    await overview_browser.close()

                browser, context, admin = await self._authenticated_page(
                    playwright,
                    self.admin_cookie,
                    "/admin-game/",
                    {"width": 768, "height": 1024},
                )
                try:
                    await admin.get_by_role("heading", name="Game Master").wait_for()
                    admin_lang = await admin.locator("html").get_attribute("lang")
                    self.assertEqual(admin_lang, "nl")
                    admin_text = await admin.locator("body").inner_text()
                    self.assertIn("huidige spelstatus", admin_text.lower())
                    self.assertIn("Adventquiz", admin_text)
                    self.assertIn("Bediening Team A", admin_text)
                    self.assertNotIn("ADVENT_QUIZ", admin_text)
                    self.assertNotIn("PUZZLE", admin_text)
                    self.assertNotIn("Authoritative game state", admin_text)
                finally:
                    await context.close()
                    await browser.close()

        asyncio.run(check())

    def test_login_validation_is_dutch(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                context = await browser.new_context(
                    viewport={"width": 390, "height": 844}
                )
                page = await context.new_page()
                try:
                    await page.goto(f"{self.live_server_url}/login/")
                    html_lang = await page.locator("html").get_attribute("lang")
                    self.assertEqual(html_lang, "nl")
                    await page.get_by_label("Team", exact=True).select_option("a")
                    await page.get_by_label("Pincode").fill("verkeerd")
                    await page.get_by_role("button", name="Naar de quiz").click()
                    await page.get_by_text("Ongeldige inloggegevens.").wait_for()
                    page_text = await page.locator("body").inner_text()
                    self.assertNotIn("Invalid credentials", page_text)
                finally:
                    await context.close()
                    await browser.close()

        asyncio.run(check())
