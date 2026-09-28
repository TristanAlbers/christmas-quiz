"""Browser regressions for stable interactive DOM under 500 ms polling."""

import asyncio
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import Client, LiveServerTestCase, override_settings

from quiz.application import admin_freeze, admin_unfreeze, start_game
from quiz.contracts import Actor, AdminTeam, StartGame
from quiz.models import AccountRole, TeamRun


class InteractionStabilityBrowserTests(LiveServerTestCase):
    def setUp(self):
        if not os.environ.get("TEST_DATABASE_PATH"):
            self.skipTest("requires disposable file-backed TEST_DATABASE_PATH")
        self.snapshots = TemporaryDirectory()
        self.addCleanup(self.snapshots.cleanup)
        scope = override_settings(QUIZ_SNAPSHOT_ROOT=Path(self.snapshots.name))
        scope.enable()
        self.addCleanup(scope.disable)

        users = get_user_model()
        self.admin_user = users.objects.create_user("stability-admin")
        self.team_user = users.objects.create_user("stability-team")
        AccountRole.objects.create(user=self.admin_user, role="admin")
        AccountRole.objects.create(user=self.team_user, role="team", team_id="a")

        self.admin = Actor(self.admin_user.pk, "admin")
        self.run_id = start_game(
            self.admin,
            StartGame(str(uuid4()), "christmas-2026-demo"),
        ).run_id

        admin_client = Client()
        admin_client.force_login(self.admin_user)
        self.admin_session_cookie = admin_client.cookies["sessionid"].value

        team_client = Client()
        team_client.force_login(self.team_user)
        self.team_session_cookie = team_client.cookies["sessionid"].value

    async def _page_for(self, playwright, path, session_cookie=None):
        browser = await playwright.chromium.launch()
        context = await browser.new_context()
        if session_cookie is not None:
            host = urlparse(self.live_server_url).hostname
            await context.add_cookies(
                [
                    {
                        "name": "sessionid",
                        "value": session_cookie,
                        "domain": host,
                        "path": "/",
                    }
                ]
            )
        page = await context.new_page()
        await page.goto(f"{self.live_server_url}{path}")
        return browser, context, page

    async def _watch_swaps(self, page, target_id):
        await page.evaluate(
            """targetId => {
                window.__pollSwaps = 0;
                const target = document.getElementById(targetId);
                const observer = new MutationObserver(records => {
                    if (records.some(record => record.type === 'childList')) {
                        window.__pollSwaps += 1;
                    }
                });
                observer.observe(target, {childList: true});
            }""",
            target_id,
        )

    async def _wait_for_two_swaps(self, page):
        await page.wait_for_function(
            "() => window.__pollSwaps >= 2",
            timeout=5000,
        )

    def test_team_pointer_press_survives_poll_and_submits_once(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser, context, page = await self._page_for(
                    playwright,
                    "/team/",
                    self.team_session_cookie,
                )
                try:
                    await page.get_by_text("Demo A1", exact=False).wait_for()
                    launcher = page.get_by_role("button", name="Winkel")
                    await launcher.focus()
                    await page.keyboard.press("Enter")
                    shop = page.locator("#team-shop-dialog")
                    await shop.wait_for(state="visible")
                    self.assertTrue(await shop.evaluate("el => el.open"))
                    await page.keyboard.press("Escape")
                    await shop.wait_for(state="hidden")
                    self.assertTrue(
                        await launcher.evaluate("el => document.activeElement === el")
                    )
                    await launcher.click()
                    await self._watch_swaps(page, "game-status")
                    button = page.get_by_role("button", name="Hint kopen (1)")
                    await button.scroll_into_view_if_needed()
                    await button.evaluate(
                        """el => {
                            window.__pressedButton = el;
                            window.__openShop = el.closest('dialog');
                        }"""
                    )
                    box = await button.bounding_box()
                    self.assertIsNotNone(box)
                    pointer_x = box["x"] + box["width"] / 2
                    pointer_y = box["y"] + box["height"] / 2
                    self.assertTrue(
                        await button.evaluate(
                            """(el, point) =>
                                document.elementFromPoint(point.x, point.y) === el""",
                            {"x": pointer_x, "y": pointer_y},
                        )
                    )
                    await page.mouse.move(
                        pointer_x,
                        pointer_y,
                    )
                    await page.mouse.down()
                    await self._wait_for_two_swaps(page)
                    self.assertTrue(
                        await button.evaluate("el => window.__pressedButton === el")
                    )
                    self.assertTrue(
                        await shop.evaluate(
                            "el => window.__openShop === el && el.open"
                        )
                    )
                    self.assertTrue(
                        await button.evaluate(
                            """(el, point) =>
                                document.elementFromPoint(point.x, point.y) === el""",
                            {"x": pointer_x, "y": pointer_y},
                        )
                    )
                    await page.mouse.up()
                    await (
                        page.locator("[data-hint-action]")
                        .filter(has_text="1 beschikbaar")
                        .wait_for(timeout=5000)
                    )
                    await page.locator("#team-shop-dialog").wait_for(
                        state="hidden", timeout=5000
                    )
                    self.assertFalse(
                        await page.locator("#team-shop-dialog").evaluate(
                            "el => el.open"
                        )
                    )
                finally:
                    await context.close()
                    await browser.close()

        asyncio.run(check())
        team = TeamRun.objects.get(run_id=self.run_id, team_id="a")
        self.assertEqual(team.points, 2)
        self.assertEqual(team.hint_tokens, 1)

    def test_admin_point_input_survives_polls_and_mutates_once(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser, context, page = await self._page_for(
                    playwright,
                    "/admin-game/",
                    self.admin_session_cookie,
                )
                try:
                    await page.get_by_text("Adventquiz", exact=True).wait_for()
                    await self._watch_swaps(page, "admin-state")
                    controls = page.locator(
                        "section[aria-label='Bediening voor Team A']"
                    )
                    field = controls.locator("input[name='delta']")
                    await field.fill("2")
                    await field.focus()
                    await field.evaluate("el => window.__pointInput = el")
                    await self._wait_for_two_swaps(page)
                    self.assertTrue(
                        await field.evaluate("el => window.__pointInput === el")
                    )
                    self.assertEqual(await field.input_value(), "2")
                    self.assertTrue(
                        await field.evaluate("el => document.activeElement === el")
                    )
                    await controls.get_by_role(
                        "button", name="Punten toepassen"
                    ).click()
                    await page.get_by_text("5 punten", exact=False).wait_for(
                        timeout=5000
                    )
                finally:
                    await context.close()
                    await browser.close()

        asyncio.run(check())
        team = TeamRun.objects.get(run_id=self.run_id, team_id="a")
        self.assertEqual(team.points, 5)

    def test_admin_controls_reconcile_on_freeze_and_unfreeze(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser, context, page = await self._page_for(
                    playwright,
                    "/admin-game/",
                    self.admin_session_cookie,
                )
                try:
                    controls = page.locator(
                        "section[aria-label='Bediening voor Team A']"
                    )
                    await controls.get_by_role(
                        "button", name="Team bevriezen", exact=True
                    ).wait_for()
                    await asyncio.to_thread(
                        admin_freeze,
                        self.admin,
                        AdminTeam(str(uuid4()), self.run_id, "a"),
                    )
                    await controls.get_by_role(
                        "button", name="Team ontdooien", exact=True
                    ).wait_for(timeout=5000)
                    self.assertEqual(
                        await controls.get_by_role(
                            "button", name="Team bevriezen", exact=True
                        ).count(),
                        0,
                    )

                    await asyncio.to_thread(
                        admin_unfreeze,
                        self.admin,
                        AdminTeam(str(uuid4()), self.run_id, "a"),
                    )
                    await controls.get_by_role(
                        "button", name="Team bevriezen", exact=True
                    ).wait_for(timeout=5000)
                finally:
                    await context.close()
                    await browser.close()

        asyncio.run(check())

    def test_themed_button_hover_keeps_hitbox_stationary(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser, context, page = await self._page_for(
                    playwright,
                    "/login/",
                )
                try:
                    button = page.locator(".theme-button")
                    await button.wait_for()
                    before = await button.bounding_box()
                    self.assertIsNotNone(before)
                    await button.hover()
                    await page.wait_for_timeout(200)
                    after = await button.bounding_box()
                    self.assertIsNotNone(after)
                    for key in ("x", "y", "width", "height"):
                        self.assertAlmostEqual(before[key], after[key], places=2)
                finally:
                    await context.close()
                    await browser.close()

        asyncio.run(check())
