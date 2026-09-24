"""Browser acceptance for Phase 3 team polling and simple effect controls.

Run only with TEST_DATABASE_PATH set to a disposable file. The browser suite is
optional when Chromium is unavailable, but an installed harness must run it.
"""

import asyncio
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import LiveServerTestCase, override_settings

from quiz.application import (
    admin_freeze,
    admin_unfreeze,
    freeze_opponent,
    get_team_state,
    start_game,
)
from quiz.contracts import Actor, AdminTeam, RunCommand, StartGame
from quiz.models import AccountRole


class PhaseThreeBrowserTests(LiveServerTestCase):
    def setUp(self):
        if not os.environ.get("TEST_DATABASE_PATH"):
            self.skipTest("requires disposable file-backed TEST_DATABASE_PATH")
        self.snapshots = TemporaryDirectory()
        self.addCleanup(self.snapshots.cleanup)
        scope = override_settings(QUIZ_SNAPSHOT_ROOT=Path(self.snapshots.name))
        scope.enable()
        self.addCleanup(scope.disable)
        users = get_user_model()
        self.admin_user = users.objects.create_user("phase3-browser-admin")
        self.a_user = users.objects.create_user("phase3-browser-a")
        self.b_user = users.objects.create_user("phase3-browser-b")
        AccountRole.objects.create(user=self.admin_user, role="admin")
        AccountRole.objects.create(user=self.a_user, role="team", team_id="a")
        AccountRole.objects.create(user=self.b_user, role="team", team_id="b")
        self.admin = Actor(self.admin_user.pk, "admin")
        self.a = Actor(self.a_user.pk, "team", "a")
        self.b = Actor(self.b_user.pk, "team", "b")
        self.run_id = start_game(
            self.admin, StartGame(str(uuid4()), "christmas-2026-demo")
        ).run_id

        self.client.force_login(self.a_user)
        self.a_session_cookie = self.client.cookies["sessionid"].value

    async def _page_for(self, playwright, path):
        browser = await playwright.chromium.launch()
        context = await browser.new_context()
        host = urlparse(self.live_server_url).hostname
        await context.add_cookies(
            [
                {
                    "name": "sessionid",
                    "value": self.a_session_cookie,
                    "domain": host,
                    "path": "/",
                }
            ]
        )
        page = await context.new_page()
        await page.goto(f"{self.live_server_url}{path}")
        return browser, context, page

    def test_team_poll_hides_and_restores_puzzle_across_admin_freeze(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser, context, page = await self._page_for(playwright, "/team/")
                try:
                    await page.get_by_text("Demo A1", exact=False).wait_for()
                    self.assertEqual(
                        await page.locator(
                            "form[action='/team/action/freeze/']"
                        ).count(),
                        1,
                    )
                    self.assertEqual(
                        await page.locator(
                            "form[action='/team/action/purchase-reverse/']"
                        ).count(),
                        1,
                    )
                    await asyncio.to_thread(
                        admin_freeze,
                        self.admin,
                        AdminTeam(str(uuid4()), self.run_id, "a"),
                    )
                    await page.locator(".state-panel-freeze").wait_for(timeout=5000)
                    freeze_surface = page.locator(".freeze-surface")
                    await freeze_surface.wait_for(timeout=5000)
                    self.assertEqual(await freeze_surface.count(), 1)
                    self.assertIn(
                        "Your team is frozen",
                        await page.locator(".freeze-message").inner_text(),
                    )
                    self.assertEqual(await page.locator("#answer-input").count(), 0)
                    self.assertEqual(
                        await page.locator("#team-actions form").count(), 0
                    )
                    self.assertNotIn(
                        "Demo A1", await page.locator("#live-game").inner_text()
                    )
                    self.assertEqual(
                        await page.locator("#question-pane img").count(), 0
                    )
                    self.assertNotIn(
                        "Hint tokens", await page.locator("#live-game").inner_text()
                    )
                    surface_handle = await freeze_surface.element_handle()
                    await page.wait_for_timeout(1100)
                    self.assertTrue(
                        await page.evaluate(
                            "([surface]) => surface === "
                            "document.querySelector('.freeze-surface')",
                            [surface_handle],
                        )
                    )

                    await asyncio.to_thread(
                        admin_unfreeze,
                        self.admin,
                        AdminTeam(str(uuid4()), self.run_id, "a"),
                    )
                    await page.get_by_text("Demo A1", exact=False).wait_for(
                        timeout=5000
                    )
                    self.assertEqual(await page.locator("#answer-input").count(), 1)
                    self.assertEqual(await page.locator(".freeze-surface").count(), 0)
                    self.assertEqual(
                        await page.locator(
                            "form[action='/team/action/freeze/']"
                        ).count(),
                        1,
                    )
                finally:
                    await context.close()
                    await browser.close()

        asyncio.run(check())

    def test_reverse_purchase_and_redirected_attack_update_the_team_view(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser, context, page = await self._page_for(playwright, "/team/")
                try:
                    reverse_form = page.locator(
                        "form[action='/team/action/purchase-reverse/']"
                    )
                    await reverse_form.locator("button[type=submit]").click()
                    await page.get_by_text("Uno Reverse active", exact=False).wait_for(
                        timeout=5000
                    )
                    self.assertIn(
                        "Uno Reverse active",
                        await page.locator(".state-panel-puzzle").inner_text(),
                    )
                    self.assertEqual(await reverse_form.count(), 0)
                    state = await asyncio.to_thread(get_team_state, self.a)
                    self.assertTrue(state.uno_reverse_active)

                    await asyncio.to_thread(
                        freeze_opponent,
                        self.b,
                        RunCommand(str(uuid4()), self.run_id),
                    )
                    await page.get_by_text(
                        "Uno Reverse inactive", exact=False
                    ).wait_for(timeout=5000)
                    await reverse_form.wait_for(timeout=5000)
                    state = await asyncio.to_thread(get_team_state, self.a)
                    attacker = await asyncio.to_thread(get_team_state, self.b)
                    self.assertEqual(state.team_state, "PUZZLE")
                    self.assertFalse(state.uno_reverse_active)
                    self.assertEqual(attacker.team_state, "FREEZE")
                    self.assertEqual(await page.locator("#answer-input").count(), 1)
                finally:
                    await context.close()
                    await browser.close()

        asyncio.run(check())
