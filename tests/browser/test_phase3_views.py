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
from django.test import Client, LiveServerTestCase, override_settings

from quiz.application import (
    admin_freeze,
    admin_unfreeze,
    start_game,
)
from quiz.contracts import Actor, AdminTeam, StartGame
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

        a_client = Client()
        a_client.force_login(self.a_user)
        self.a_session_cookie = a_client.cookies["sessionid"].value
        b_client = Client()
        b_client.force_login(self.b_user)
        self.b_session_cookie = b_client.cookies["sessionid"].value

    async def _page_for(self, playwright, path, session_cookie=None):
        browser = await playwright.chromium.launch()
        context = await browser.new_context()
        host = urlparse(self.live_server_url).hostname
        await context.add_cookies(
            [
                {
                    "name": "sessionid",
                    "value": session_cookie or self.a_session_cookie,
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

    def test_reverse_purchase_closes_shop_and_redirected_attack_animates_both_teams(
        self,
    ):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser_a, context_a, page_a = await self._page_for(
                    playwright, "/team/", self.a_session_cookie
                )
                browser_b, context_b, page_b = await self._page_for(
                    playwright, "/team/", self.b_session_cookie
                )
                try:
                    await page_a.get_by_role(
                        "button", name="Shop Power-ups"
                    ).click()
                    reverse_form = page_a.locator(
                        "form[action='/team/action/purchase-reverse/']"
                    )
                    await reverse_form.locator("button[type=submit]").click()
                    await page_a.locator("#team-shop-dialog").wait_for(
                        state="hidden", timeout=5000
                    )
                    await page_a.get_by_text(
                        "Uno Reverse active", exact=False
                    ).wait_for(timeout=5000)
                    self.assertIn(
                        "purchased and armed",
                        await page_a.locator("#action-feedback").inner_text(),
                    )
                    self.assertFalse(
                        await page_a.locator("#gameplay-event").is_visible()
                    )

                    await page_b.get_by_role(
                        "button", name="Shop Power-ups"
                    ).click()
                    freeze_button = page_b.get_by_role(
                        "button", name="Freeze opponent (3)"
                    )
                    await freeze_button.click()
                    await page_b.locator("#team-shop-dialog").wait_for(
                        state="hidden", timeout=5000
                    )

                    reflected = page_b.locator(
                        "#gameplay-event.gameplay-event--attacker-reversed"
                    )
                    saved = page_a.locator(
                        "#gameplay-event.gameplay-event--saved"
                    )
                    await reflected.wait_for(state="visible", timeout=5000)
                    await saved.wait_for(state="visible", timeout=5000)
                    self.assertIn("Freeze launched", await reflected.inner_text())
                    self.assertIn(
                        "Uno Reverse sent your Freeze back!",
                        await reflected.inner_text(),
                    )
                    self.assertIn("Your Reverse saved you!", await saved.inner_text())

                    await page_b.locator(".state-panel-freeze").wait_for(timeout=5000)
                    self.assertEqual(await page_b.locator("#answer-input").count(), 0)
                    self.assertEqual(await page_a.locator("#answer-input").count(), 1)
                    self.assertIn(
                        "Uno Reverse inactive",
                        await page_a.locator(".team-resource-bar").inner_text(),
                    )

                    await page_a.wait_for_timeout(3200)
                    self.assertFalse(await saved.is_visible())
                    self.assertFalse(await reflected.is_visible())

                    await page_a.reload()
                    self.assertFalse(
                        await page_a.locator("#gameplay-event").is_visible()
                    )
                    self.assertEqual(await page_a.locator("#answer-input").count(), 1)
                finally:
                    await context_a.close()
                    await browser_a.close()
                    await context_b.close()
                    await browser_b.close()

        asyncio.run(check())

    def test_freeze_target_eligibility_updates_while_shop_is_open(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser, context, page = await self._page_for(playwright, "/team/")
                try:
                    await page.get_by_role(
                        "button", name="Shop Power-ups"
                    ).click()
                    shop = page.locator("#team-shop-dialog")
                    await shop.wait_for(state="visible")
                    self.assertTrue(
                        await page.get_by_role(
                            "button", name="Freeze opponent (3)"
                        ).is_enabled()
                    )

                    await asyncio.to_thread(
                        admin_freeze,
                        self.admin,
                        AdminTeam(str(uuid4()), self.run_id, "b"),
                    )
                    unavailable = page.get_by_role(
                        "button", name="Freeze unavailable"
                    )
                    await unavailable.wait_for(timeout=5000)
                    self.assertTrue(await shop.evaluate("el => el.open"))
                    self.assertTrue(await unavailable.is_disabled())
                    self.assertIn(
                        "Opponent is already frozen",
                        await page.locator(".shop-item--freeze").inner_text(),
                    )

                    await asyncio.to_thread(
                        admin_unfreeze,
                        self.admin,
                        AdminTeam(str(uuid4()), self.run_id, "b"),
                    )
                    await page.get_by_role(
                        "button", name="Freeze opponent (3)"
                    ).wait_for(timeout=5000)
                    self.assertTrue(await shop.evaluate("el => el.open"))
                finally:
                    await context.close()
                    await browser.close()

        asyncio.run(check())

    def test_normal_freeze_animates_attacker_then_victim_before_lock_view(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser_a, context_a, page_a = await self._page_for(
                    playwright, "/team/", self.a_session_cookie
                )
                browser_b, context_b, page_b = await self._page_for(
                    playwright, "/team/", self.b_session_cookie
                )
                try:
                    await page_a.get_by_role(
                        "button", name="Shop Power-ups"
                    ).click()
                    await page_a.get_by_role(
                        "button", name="Freeze opponent (3)"
                    ).click()
                    await page_a.locator("#team-shop-dialog").wait_for(
                        state="hidden", timeout=5000
                    )

                    attack = page_a.locator(
                        "#gameplay-event.gameplay-event--attacker"
                    )
                    impact = page_b.locator(
                        "#gameplay-event.gameplay-event--victim"
                    )
                    await attack.wait_for(state="visible", timeout=5000)
                    await impact.wait_for(state="visible", timeout=5000)
                    self.assertIn("Direct hit!", await attack.inner_text())
                    self.assertIn("You have been frozen!", await impact.inner_text())
                    await page_b.locator(".state-panel-freeze").wait_for(timeout=5000)
                    self.assertEqual(await page_b.locator("#answer-input").count(), 0)

                    await page_b.wait_for_timeout(3400)
                    self.assertFalse(await impact.is_visible())
                    self.assertIn(
                        "Your team is frozen",
                        await page_b.locator(".freeze-message").inner_text(),
                    )
                    await page_b.reload()
                    self.assertFalse(
                        await page_b.locator("#gameplay-event").is_visible()
                    )
                finally:
                    await context_a.close()
                    await browser_a.close()
                    await context_b.close()
                    await browser_b.close()

        asyncio.run(check())

    def test_rejected_shop_purchase_stays_open_without_success_animation(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser, context, page = await self._page_for(playwright, "/team/")
                try:
                    await page.get_by_role(
                        "button", name="Shop Power-ups"
                    ).click()
                    await page.get_by_role(
                        "button", name="Buy Uno Reverse (2)"
                    ).click()
                    await page.locator("#team-shop-dialog").wait_for(
                        state="hidden", timeout=5000
                    )

                    await page.get_by_role(
                        "button", name="Shop Power-ups"
                    ).click()
                    shop = page.locator("#team-shop-dialog")
                    await page.get_by_role(
                        "button", name="Freeze opponent (3)"
                    ).click()
                    await page.locator("#shop-feedback").get_by_text(
                        "Action rejected: insufficient points"
                    ).wait_for(timeout=5000)
                    self.assertTrue(await shop.evaluate("el => el.open"))
                    self.assertFalse(
                        await page.locator("#gameplay-event").is_visible()
                    )
                finally:
                    await context.close()
                    await browser.close()

        asyncio.run(check())

    def test_freeze_attack_reduced_motion_keeps_static_feedback(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser, context, page = await self._page_for(playwright, "/team/")
                try:
                    await page.emulate_media(reduced_motion="reduce")
                    await page.get_by_role(
                        "button", name="Shop Power-ups"
                    ).click()
                    await page.get_by_role(
                        "button", name="Freeze opponent (3)"
                    ).click()
                    event = page.locator(
                        "#gameplay-event.gameplay-event--attacker"
                    )
                    await event.wait_for(state="visible", timeout=5000)
                    self.assertIn("Direct hit!", await event.inner_text())
                    self.assertEqual(
                        await page.locator(
                            ".gameplay-event__stage--attack"
                        ).evaluate("el => getComputedStyle(el).animationName"),
                        "gameplay-static-first",
                    )
                finally:
                    await context.close()
                    await browser.close()

        asyncio.run(check())
