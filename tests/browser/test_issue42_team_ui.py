"""Browser acceptance for issue #42's simplified team puzzle experience."""

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
from quiz.models import AccountRole, TeamRun


class Issue42TeamUiBrowserTests(LiveServerTestCase):
    def setUp(self):
        if not os.environ.get("TEST_DATABASE_PATH"):
            self.skipTest("requires disposable file-backed TEST_DATABASE_PATH")
        self.snapshots = TemporaryDirectory()
        self.addCleanup(self.snapshots.cleanup)
        scope = override_settings(QUIZ_SNAPSHOT_ROOT=Path(self.snapshots.name))
        scope.enable()
        self.addCleanup(scope.disable)

        users = get_user_model()
        self.admin_user = users.objects.create_user("issue42-admin")
        self.team_user = users.objects.create_user("issue42-team")
        AccountRole.objects.create(user=self.admin_user, role="admin")
        AccountRole.objects.create(user=self.team_user, role="team", team_id="a")
        self.admin = Actor(self.admin_user.pk, "admin")
        self.run_id = start_game(
            self.admin,
            StartGame(str(uuid4()), "christmas-2026-demo"),
        ).run_id

        client = Client()
        client.force_login(self.team_user)
        self.session_cookie = client.cookies["sessionid"].value

    async def _page(self, playwright):
        browser = await playwright.chromium.launch()
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
        return browser, context, page

    async def _watch_game_status_swaps(self, page):
        await page.evaluate(
            """() => {
                window.__issue42PollSwaps = 0;
                const target = document.getElementById('game-status');
                const observer = new MutationObserver(records => {
                    if (records.some(record => record.type === 'childList')) {
                        window.__issue42PollSwaps += 1;
                    }
                });
                observer.observe(target, {childList: true});
            }"""
        )

    async def _wait_for_two_polls(self, page):
        await page.wait_for_function(
            "() => window.__issue42PollSwaps >= 2",
            timeout=5000,
        )

    def test_phone_hierarchy_and_disabled_action_states(self):
        TeamRun.objects.filter(run_id=self.run_id, team_id="a").update(
            points=1,
            hint_tokens=0,
        )

        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser, context, page = await self._page(playwright)
                try:
                    await page.get_by_text("Demo A1", exact=False).wait_for()

                    self.assertEqual(await page.locator(".status-row").count(), 0)
                    self.assertEqual(
                        await page.locator(".resource-card--hint").count(), 0
                    )
                    self.assertNotIn(
                        "ADVENT_QUIZ",
                        await page.locator("#live-game").inner_text(),
                    )

                    points = page.locator(".resource-card--coins")
                    self.assertIn("1", await points.inner_text())
                    self.assertIn("punten", (await points.inner_text()).lower())
                    self.assertEqual(
                        await page.locator(".resource-card--fragments").count(), 1
                    )
                    self.assertEqual(
                        await page.locator(".resource-card--reverse").count(), 1
                    )

                    answer = page.locator("#answer-input")
                    hint = page.locator("[data-hint-action]")
                    skip = page.locator("[data-skip-action]")
                    self.assertTrue(await answer.is_visible())
                    self.assertTrue(await hint.is_disabled())
                    self.assertIn("0 beschikbaar", await hint.inner_text())
                    self.assertTrue(await skip.is_disabled())
                    self.assertIn("2 punten", await skip.inner_text())
                    self.assertIn("1 punt tekort", await skip.inner_text())

                    answer_box = await answer.bounding_box()
                    hint_box = await hint.bounding_box()
                    skip_box = await skip.bounding_box()
                    self.assertIsNotNone(answer_box)
                    self.assertIsNotNone(hint_box)
                    self.assertIsNotNone(skip_box)
                    self.assertLess(answer_box["y"], hint_box["y"])
                    self.assertLess(hint_box["y"], skip_box["y"])
                    self.assertTrue(
                        await page.evaluate(
                            "document.documentElement.scrollWidth <= window.innerWidth"
                        )
                    )
                finally:
                    await context.close()
                    await browser.close()

        asyncio.run(check())

    def test_hint_and_skip_pointer_presses_survive_normal_polls(self):
        TeamRun.objects.filter(run_id=self.run_id, team_id="a").update(
            points=2,
            hint_tokens=1,
        )

        async def press_across_polls(page, locator, marker):
            await locator.scroll_into_view_if_needed()
            await locator.evaluate(
                "(el, key) => { window[key] = el; }",
                marker,
            )
            box = await locator.bounding_box()
            self.assertIsNotNone(box)
            x = box["x"] + box["width"] / 2
            y = box["y"] + box["height"] / 2
            await page.mouse.move(x, y)
            await page.mouse.down()
            await self._wait_for_two_polls(page)
            self.assertTrue(
                await locator.evaluate(
                    "(el, key) => window[key] === el",
                    marker,
                )
            )
            self.assertTrue(
                await locator.evaluate(
                    """(el, point) => {
                        const hit = document.elementFromPoint(point.x, point.y);
                        return hit === el || el.contains(hit);
                    }""",
                    {"x": x, "y": y},
                )
            )
            await page.mouse.up()

        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser, context, page = await self._page(playwright)
                try:
                    await page.get_by_text("Demo A1", exact=False).wait_for()
                    await self._watch_game_status_swaps(page)

                    hint = page.locator("[data-hint-action]")
                    self.assertFalse(await hint.is_disabled())
                    await press_across_polls(page, hint, "__issue42HintButton")
                    await page.locator(".hint-card").wait_for(timeout=5000)
                    self.assertIn(
                        "0 beschikbaar",
                        await page.locator("[data-hint-action]").inner_text(),
                    )

                    # Rebase the helper counter so the second pointer press must span
                    # two fresh polls rather than reuse the first press' observations.
                    await page.evaluate("() => { window.__issue42PollSwaps = 0; }")

                    skip = page.locator("[data-skip-action]")
                    self.assertFalse(await skip.is_disabled())
                    await press_across_polls(page, skip, "__issue42SkipButton")
                    await page.get_by_text("Demo A2", exact=False).wait_for(
                        timeout=5000
                    )
                finally:
                    await context.close()
                    await browser.close()

        asyncio.run(check())
        team = TeamRun.objects.get(run_id=self.run_id, team_id="a")
        self.assertEqual(team.current_number, 2)
        self.assertEqual(team.hint_tokens, 0)
