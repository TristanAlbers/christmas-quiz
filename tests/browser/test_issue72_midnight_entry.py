"""Real Django/Chromium acceptance for Midnight Advent entry and READY (#72)."""

import asyncio
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import LiveServerTestCase, override_settings

from quiz.application import reset_game, start_game
from quiz.contracts import Actor, RunCommand, StartGame
from quiz.models import AccountRole


class MidnightEntryBrowserTests(LiveServerTestCase):
    def setUp(self):
        if not os.environ.get("TEST_DATABASE_PATH"):
            self.skipTest("requires disposable file-backed TEST_DATABASE_PATH")
        self.snapshots = TemporaryDirectory()
        self.addCleanup(self.snapshots.cleanup)
        settings = override_settings(QUIZ_SNAPSHOT_ROOT=Path(self.snapshots.name))
        settings.enable()
        self.addCleanup(settings.disable)
        users = get_user_model()
        self.admin = users.objects.create_user(
            "midnight-admin", password="admin-secret"
        )
        AccountRole.objects.create(user=self.admin, role="admin")
        for letter in ("a", "b"):
            user = users.objects.create_user(
                f"team-{letter}", password=f"team-{letter}-secret"
            )
            AccountRole.objects.create(user=user, role="team", team_id=letter)

    async def _screenshot(self, page, name):
        root = os.environ.get("UI72_SCREENSHOT_DIR")
        if root:
            directory = Path(root)
            directory.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(directory / f"{name}.png"), full_page=True)

    async def _assert_narrow(self, page, width):
        dimensions = await page.evaluate(
            """() => ({
                viewport: window.innerWidth,
                html: document.documentElement.scrollWidth,
            })"""
        )
        self.assertEqual(dimensions["viewport"], width)
        self.assertLessEqual(dimensions["html"], width + 1)

    def test_real_team_login_and_private_ready_at_both_phone_widths(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                try:
                    for width in (320, 390):
                        context = await browser.new_context(
                            viewport={"width": width, "height": 844},
                            reduced_motion="reduce",
                        )
                        page = await context.new_page()
                        try:
                            await page.goto(f"{self.live_server_url}/")
                            await page.get_by_role(
                                "heading", name="Quizzmass"
                            ).wait_for()
                            await self._assert_narrow(page, width)
                            await self._screenshot(page, f"landing-{width}")

                            await page.get_by_role(
                                "link", name="Inloggen als team"
                            ).click()
                            self.assertEqual(
                                await page.locator("html").get_attribute("lang"), "nl"
                            )
                            await self._assert_narrow(page, width)
                            await self._screenshot(page, f"team-login-{width}")
                            await page.get_by_label("Pincode").focus()
                            self.assertEqual(
                                await page.evaluate("document.activeElement.id"),
                                await page.get_by_label("Pincode").get_attribute("id"),
                            )
                            focus = await page.get_by_label("Pincode").evaluate(
                                "(el) => getComputedStyle(el).outlineStyle"
                            )
                            self.assertNotEqual(focus, "none")

                            await page.get_by_label(
                                "Team", exact=True
                            ).select_option("a")
                            await page.get_by_label("Pincode").fill("incorrect")
                            await page.get_by_role(
                                "button", name="Naar de quiz"
                            ).click()
                            await page.get_by_text(
                                "Ongeldige inloggegevens."
                            ).wait_for()
                            self.assertTrue(page.url.endswith("/login/"))

                            await page.get_by_label("Pincode").fill("team-a-secret")
                            await page.get_by_role(
                                "button", name="Naar de quiz"
                            ).click()
                            await page.locator(".team-ready").wait_for()
                            self.assertTrue(page.url.endswith("/team/"))
                            self.assertIn(
                                "Team A", await page.locator(".team-ready").inner_text()
                            )
                            self.assertEqual(
                                await page.locator("#answer-input").count(), 0
                            )
                            self.assertEqual(
                                await page.locator(".team-resource-bar").count(), 0
                            )
                            self.assertEqual(
                                await page.locator("#question-pane img").count(), 0
                            )
                            self.assertNotIn(
                                "Demo A1", await page.locator("#live-game").inner_text()
                            )
                            self.assertEqual(
                                await page.locator("#poller").get_attribute(
                                    "hx-trigger"
                                ),
                                "every 500ms [!document.hidden], "
                                "visibilitychange[!document.hidden] from:document",
                            )
                            await self._assert_narrow(page, width)
                            await self._screenshot(page, f"team-ready-a-{width}")
                            await page.wait_for_timeout(1100)
                            self.assertEqual(
                                await page.locator(".team-ready").count(), 1
                            )
                        finally:
                            await context.close()
                finally:
                    await browser.close()

        asyncio.run(check())

    def test_admin_auth_and_team_b_ready_are_role_separated(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                try:
                    context = await browser.new_context(
                        viewport={"width": 320, "height": 844}
                    )
                    page = await context.new_page()
                    await page.goto(f"{self.live_server_url}/admin-login/")
                    await self._assert_narrow(page, 320)
                    await self._screenshot(page, "admin-login-320")
                    await page.get_by_label("Gebruikersnaam").focus()
                    self.assertNotEqual(
                        await page.get_by_label("Gebruikersnaam").evaluate(
                            "(el) => getComputedStyle(el).outlineStyle"
                        ),
                        "none",
                    )
                    await page.get_by_label("Gebruikersnaam").fill("midnight-admin")
                    await page.get_by_label("Wachtwoord").fill("incorrect")
                    await page.get_by_role("button", name="Open Game Master").click()
                    await page.get_by_text("Ongeldige inloggegevens.").wait_for()
                    await self._assert_narrow(page, 320)
                    await page.set_viewport_size({"width": 390, "height": 844})
                    await self._assert_narrow(page, 390)
                    await self._screenshot(page, "admin-login-390")
                    await page.get_by_label("Wachtwoord").fill("admin-secret")
                    await page.get_by_role("button", name="Open Game Master").click()
                    self.assertTrue(page.url.endswith("/admin-game/"))
                    await page.get_by_role("heading", name="Game Master").wait_for()
                    await self._screenshot(page, "admin-ready-390")
                    await self._assert_narrow(page, 390)

                    await page.get_by_role("button", name="Uitloggen").click()
                    await page.goto(f"{self.live_server_url}/login/")
                    await page.get_by_label("Team", exact=True).select_option("b")
                    await page.get_by_label("Pincode").fill("team-b-secret")
                    await page.get_by_role("button", name="Naar de quiz").click()
                    await page.locator(".team-ready").wait_for()
                    waiting = await page.locator(".team-ready").inner_text()
                    self.assertIn("Team B", waiting)
                    self.assertNotIn("Team A", waiting)
                    self.assertNotIn("Demo A1", await page.locator("body").inner_text())
                    await self._screenshot(page, "team-ready-b-390")
                finally:
                    await context.close()
                    await browser.close()

        asyncio.run(check())

    def test_server_start_replaces_waiting_without_changing_poller(self):
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
                    await page.get_by_label("Pincode").fill("team-a-secret")
                    await page.get_by_role("button", name="Naar de quiz").click()
                    await page.locator(".team-ready").wait_for()
                    poller = await page.locator("#poller").element_handle()
                    started = await asyncio.to_thread(
                        start_game,
                        Actor(self.admin.pk, "admin"),
                        StartGame(str(uuid4()), "christmas-2026-demo"),
                    )
                    await page.locator("#answer-input").wait_for(timeout=6000)
                    self.assertEqual(await page.locator(".team-ready").count(), 0)
                    self.assertTrue(
                        await page.evaluate(
                            "(node) => node === document.querySelector('#poller')",
                            poller,
                        )
                    )
                    self.assertEqual(
                        await page.locator(".team-resource-bar").count(), 1
                    )
                    await self._screenshot(page, "team-active-transition-390")
                    await asyncio.to_thread(
                        reset_game,
                        Actor(self.admin.pk, "admin"),
                        RunCommand(str(uuid4()), started.run_id),
                    )
                    await page.locator(".team-ready").wait_for(timeout=6000)
                    self.assertEqual(await page.locator("#answer-input").count(), 0)
                    self.assertEqual(
                        await page.locator(".team-resource-bar").count(), 0
                    )
                    self.assertEqual(
                        await page.locator("#question-pane img").count(), 0
                    )
                    self.assertNotIn(
                        "Demo A1", await page.locator("body").inner_text()
                    )
                    await self._screenshot(page, "team-ready-after-reset-390")
                finally:
                    await context.close()
                    await browser.close()

        asyncio.run(check())
