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

from quiz.application import admin_freeze, admin_unfreeze, start_game
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

        self.client.force_login(self.a_user)
        self.a_session_cookie = self.client.cookies["sessionid"].value

    async def _page_for(self, playwright, path):
        browser = await playwright.chromium.launch()
        context = await browser.new_context(viewport={"width": 390, "height": 844})
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
                        await page.locator(".team-playing-time").count(), 0
                    )
                    self.assertEqual(
                        await page.locator("[data-gameplay-ms]").count(), 0
                    )
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
                        "Jullie team is bevroren",
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
                        "Fragmenten", await page.locator("#live-game").inner_text()
                    )
                    self.assertEqual(
                        await page.locator(".team-playing-time").count(), 0
                    )
                    self.assertEqual(
                        await page.locator("[data-gameplay-ms]").count(), 0
                    )

                    geometry = await page.evaluate(
                        """() => {
                            const rect = selector => {
                                const element = document.querySelector(selector);
                                const box = element.getBoundingClientRect();
                                return {
                                    left: box.left,
                                    top: box.top,
                                    right: box.right,
                                    bottom: box.bottom,
                                    width: box.width,
                                    height: box.height,
                                };
                            };
                            return {
                                viewport: {
                                    width: window.innerWidth,
                                    height: window.innerHeight,
                                },
                                surface: rect('.freeze-surface'),
                                lock: rect('#game-status'),
                                message: rect('.freeze-message'),
                            };
                        }"""
                    )
                    for layer in ("surface", "lock"):
                        self.assertAlmostEqual(
                            geometry[layer]["left"], 0, delta=1
                        )
                        self.assertAlmostEqual(
                            geometry[layer]["top"], 0, delta=1
                        )
                        self.assertAlmostEqual(
                            geometry[layer]["width"],
                            geometry["viewport"]["width"],
                            delta=1,
                        )
                        self.assertAlmostEqual(
                            geometry[layer]["height"],
                            geometry["viewport"]["height"],
                            delta=1,
                        )

                    edge_treatment = await freeze_surface.evaluate(
                        """element => {
                            const surface = getComputedStyle(element);
                            const before = getComputedStyle(element, '::before');
                            const after = getComputedStyle(element, '::after');
                            return {
                                borderWidths: [
                                    surface.borderTopWidth,
                                    surface.borderRightWidth,
                                    surface.borderBottomWidth,
                                    surface.borderLeftWidth,
                                ],
                                beforeInset: [
                                    before.top,
                                    before.right,
                                    before.bottom,
                                    before.left,
                                ],
                                afterInset: [
                                    after.top,
                                    after.right,
                                    after.bottom,
                                    after.left,
                                ],
                                surfaceBackground: surface.backgroundImage,
                                beforeBackground: before.backgroundImage,
                                afterBackground: after.backgroundImage,
                            };
                        }"""
                    )
                    self.assertEqual(
                        edge_treatment["borderWidths"], ["0px"] * 4
                    )
                    self.assertEqual(edge_treatment["beforeInset"], ["0px"] * 4)
                    self.assertEqual(edge_treatment["afterInset"], ["0px"] * 4)
                    self.assertNotEqual(edge_treatment["surfaceBackground"], "none")
                    self.assertNotEqual(edge_treatment["beforeBackground"], "none")
                    self.assertNotEqual(edge_treatment["afterBackground"], "none")

                    self.assertGreaterEqual(geometry["message"]["left"], 8)
                    self.assertGreaterEqual(geometry["message"]["top"], 8)
                    self.assertLessEqual(
                        geometry["message"]["right"],
                        geometry["viewport"]["width"] - 8,
                    )
                    self.assertLessEqual(
                        geometry["message"]["bottom"],
                        geometry["viewport"]["height"] - 8,
                    )

                    await page.set_viewport_size({"width": 568, "height": 320})
                    await page.evaluate(
                        "() => { document.documentElement.style.fontSize = '32px'; }"
                    )
                    freeze_lock = page.locator("#game-status")
                    overflow = await freeze_lock.evaluate(
                        """element => ({
                            clientHeight: element.clientHeight,
                            scrollHeight: element.scrollHeight,
                        })"""
                    )
                    self.assertGreater(
                        overflow["scrollHeight"], overflow["clientHeight"]
                    )
                    await page.locator(".freeze-message").hover()
                    await page.mouse.wheel(0, 1000)
                    await page.wait_for_timeout(1100)
                    scroll_top = await freeze_lock.evaluate(
                        "element => element.scrollTop"
                    )
                    self.assertGreater(scroll_top, 0)
                    timer_box = await page.locator(".freeze-timer").bounding_box()
                    self.assertIsNotNone(timer_box)
                    self.assertLessEqual(
                        timer_box["y"] + timer_box["height"], 312
                    )
                    await page.evaluate(
                        "() => { document.documentElement.style.fontSize = ''; }"
                    )
                    await page.set_viewport_size({"width": 390, "height": 844})

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
