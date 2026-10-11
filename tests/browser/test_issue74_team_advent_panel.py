"""Rendered acceptance for the issue #74 team Advent puzzle panel."""

import asyncio
import json
import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, LiveServerTestCase, override_settings

from quiz.application import start_game
from quiz.contracts import Actor, StartGame
from quiz.models import AccountRole, FragmentAward, TeamRun


class Issue74TeamAdventPanelBrowserTests(LiveServerTestCase):
    def setUp(self):
        if not os.environ.get("TEST_DATABASE_PATH"):
            self.skipTest("requires disposable file-backed TEST_DATABASE_PATH")

        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        games = root / "games"
        package = games / "christmas-2026-demo"
        shutil.copytree(settings.BASE_DIR / "games" / "christmas-2026-demo", package)
        (package / "a" / "clue.mp3").write_bytes(b"ID3-issue-74-private-audio")

        config_file = package / "game.json"
        config = json.loads(config_file.read_text())
        first = config["teams"]["a"]["puzzles"][0]
        first["title"] = "De brief van de nachtwacht"
        first["body"] = (
            "Lees de lange kerstbrief aandachtig. Combineer de gouden letter met "
            "de aanwijzing op de hoge afbeelding en luister daarna naar het "
            "audiofragment. Dit verhaal blijft ook op een smalle telefoon volledig "
            "leesbaar zonder dat de antwoordbediening buiten beeld schuift."
        )
        first["media"] = [
            {
                "type": "image",
                "path": "a/star.png",
                "alt": "Hoge privéaanwijzing voor team A",
            },
            {"type": "audio", "path": "a/clue.mp3"},
        ]
        second = config["teams"]["a"]["puzzles"][1]
        second["title"] = "De vraag zonder media"
        second["body"] = "Welke twee cijfers vormen samen het getal vierentwintig?"
        second["media"] = []
        config_file.write_text(json.dumps(config))

        scope = override_settings(
            QUIZ_GAMES_ROOT=games,
            QUIZ_SNAPSHOT_ROOT=root / "snapshots",
        )
        scope.enable()
        self.addCleanup(scope.disable)

        users = get_user_model()
        admin_user = users.objects.create_user("issue74-browser-admin")
        self.team_user = users.objects.create_user("issue74-browser-team")
        AccountRole.objects.create(user=admin_user, role="admin")
        AccountRole.objects.create(user=self.team_user, role="team", team_id="a")
        self.run_id = start_game(
            Actor(admin_user.pk, "admin"),
            StartGame(str(uuid4()), "christmas-2026-demo"),
        ).run_id
        TeamRun.objects.filter(run_id=self.run_id, team_id="a").update(
            points=12,
            hint_tokens=2,
            reverse_active=True,
        )
        FragmentAward.objects.create(
            run_id=self.run_id,
            team_id="a",
            puzzle_id="a-14",
            fragment="C",
        )
        FragmentAward.objects.create(
            run_id=self.run_id,
            team_id="a",
            puzzle_id="a-15",
            fragment="A",
        )

        client = Client()
        client.force_login(self.team_user)
        self.session_cookie = client.cookies["sessionid"].value
        screenshot_dir = os.environ.get("UI74_SCREENSHOT_DIR")
        self.screenshot_dir = Path(screenshot_dir) if screenshot_dir else None
        if self.screenshot_dir:
            self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    async def _page(
        self,
        browser,
        viewport,
        *,
        reduced_motion="no-preference",
        without_issue74_css=False,
    ):
        context = await browser.new_context(
            viewport=viewport,
            reduced_motion=reduced_motion,
        )
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
        if without_issue74_css:
            await context.route(
                "**/issue74-team-advent.css",
                lambda route: route.abort(),
            )
        page = await context.new_page()
        await page.goto(f"{self.live_server_url}/team/")
        await page.locator(".team-advent-panel").wait_for()
        return context, page

    async def _screenshot(self, page, name):
        if self.screenshot_dir:
            await page.screenshot(
                path=self.screenshot_dir / name,
                full_page=True,
            )

    async def _watch_polls(self, page):
        await page.evaluate(
            """() => {
                window.__issue74PollSwaps = 0;
                const target = document.getElementById('game-status');
                new MutationObserver(records => {
                    if (records.some(record => record.type === 'childList')) {
                        window.__issue74PollSwaps += 1;
                    }
                }).observe(target, {childList: true});
            }"""
        )

    async def _press_across_two_polls(self, page, locator, marker):
        await locator.scroll_into_view_if_needed()
        await locator.evaluate("(el, key) => { window[key] = el; }", marker)
        box = await locator.bounding_box()
        self.assertIsNotNone(box)
        point = {
            "x": box["x"] + box["width"] / 2,
            "y": box["y"] + box["height"] / 2,
        }
        await page.mouse.move(point["x"], point["y"])
        await page.mouse.down()
        await page.wait_for_function(
            "() => window.__issue74PollSwaps >= 2",
            timeout=5000,
        )
        self.assertTrue(
            await locator.evaluate("(el, key) => window[key] === el", marker)
        )
        self.assertTrue(
            await locator.evaluate(
                """(el, point) => {
                    const hit = document.elementFromPoint(point.x, point.y);
                    return hit === el || el.contains(hit);
                }""",
                point,
            )
        )
        await page.mouse.up()

    def test_rendered_phone_tablet_media_and_polling_interactions(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                contexts = []
                try:
                    before_context, before = await self._page(
                        browser,
                        {"width": 390, "height": 844},
                        without_issue74_css=True,
                    )
                    contexts.append(before_context)
                    await self._screenshot(before, "issue74-before-390.png")

                    context, page = await self._page(
                        browser,
                        {"width": 390, "height": 844},
                    )
                    contexts.append(context)
                    self.assertEqual(await page.locator(".advent-door").count(), 0)
                    self.assertIn(
                        "De brief van de nachtwacht",
                        await page.locator(".team-advent-panel").inner_text(),
                    )
                    self.assertIn(
                        "12",
                        await page.locator(".resource-card--coins").inner_text(),
                    )
                    self.assertIn(
                        "Actief",
                        await page.locator(".resource-card--reverse").inner_text(),
                    )
                    self.assertIn(
                        "C",
                        await page.locator(".resource-card--fragments").inner_text(),
                    )
                    self.assertTrue(
                        await page.get_by_role(
                            "button", name="Winkel", exact=False
                        ).is_visible()
                    )
                    self.assertEqual(await page.locator(".puzzle-image").count(), 1)
                    audio = page.locator("audio.puzzle-audio")
                    self.assertEqual(await audio.count(), 1)
                    self.assertIsNone(await audio.get_attribute("autoplay"))
                    self.assertEqual(await audio.get_attribute("preload"), "metadata")

                    hint = page.locator("[data-hint-action]")
                    skip = page.locator("[data-skip-action]")
                    hint_box = await hint.bounding_box()
                    skip_box = await skip.bounding_box()
                    self.assertIsNotNone(hint_box)
                    self.assertIsNotNone(skip_box)
                    self.assertLess(abs(hint_box["y"] - skip_box["y"]), 8)
                    self.assertGreater(skip_box["x"], hint_box["x"])
                    self.assertTrue(
                        await page.evaluate(
                            "document.documentElement.scrollWidth <= window.innerWidth"
                        )
                    )

                    answer = page.locator("#answer-input")
                    await answer.focus()
                    await page.keyboard.type("kerstbrief")
                    await answer.evaluate(
                        """el => {
                            el.setSelectionRange(5, 5);
                            window.__issue74AnswerNode = el;
                        }"""
                    )
                    await audio.evaluate("el => { window.__issue74AudioNode = el; }")
                    await hint.evaluate("el => { window.__issue74HintNode = el; }")
                    await skip.evaluate("el => { window.__issue74SkipNode = el; }")
                    await self._watch_polls(page)
                    await page.wait_for_function(
                        "() => window.__issue74PollSwaps >= 2",
                        timeout=5000,
                    )
                    self.assertTrue(
                        await answer.evaluate(
                            """el => window.__issue74AnswerNode === el
                                && document.activeElement === el"""
                        )
                    )
                    self.assertEqual(await answer.input_value(), "kerstbrief")
                    self.assertEqual(
                        await answer.evaluate("el => el.selectionStart"),
                        5,
                    )
                    self.assertTrue(
                        await audio.evaluate("el => window.__issue74AudioNode === el")
                    )
                    self.assertTrue(
                        await hint.evaluate("el => window.__issue74HintNode === el")
                    )
                    self.assertTrue(
                        await skip.evaluate("el => window.__issue74SkipNode === el")
                    )
                    await page.keyboard.press("Tab")
                    self.assertTrue(
                        await page.locator(".answer-form .button-primary").evaluate(
                            "el => document.activeElement === el"
                        )
                    )
                    await page.keyboard.press("Shift+Tab")
                    self.assertTrue(
                        await answer.evaluate("el => document.activeElement === el")
                    )
                    await self._screenshot(
                        page,
                        "issue74-after-390-long-mixed-media.png",
                    )

                    await page.evaluate("() => { window.__issue74PollSwaps = 0; }")
                    await self._press_across_two_polls(
                        page,
                        hint,
                        "__issue74HintPointerNode",
                    )
                    await page.locator(".hint-card").wait_for(timeout=5000)
                    await page.evaluate("() => { window.__issue74PollSwaps = 0; }")
                    skip = page.locator("[data-skip-action]")
                    await self._press_across_two_polls(
                        page,
                        skip,
                        "__issue74SkipPointerNode",
                    )
                    await page.get_by_text("De vraag zonder media").wait_for(
                        timeout=5000
                    )

                    narrow_context, narrow = await self._page(
                        browser,
                        {"width": 320, "height": 720},
                    )
                    contexts.append(narrow_context)
                    self.assertEqual(
                        await narrow.locator(".puzzle-media-list").count(),
                        0,
                    )
                    narrow_hint = await narrow.locator(
                        "[data-hint-action]"
                    ).bounding_box()
                    narrow_skip = await narrow.locator(
                        "[data-skip-action]"
                    ).bounding_box()
                    self.assertIsNotNone(narrow_hint)
                    self.assertIsNotNone(narrow_skip)
                    self.assertGreater(narrow_skip["y"], narrow_hint["y"] + 20)
                    self.assertTrue(
                        await narrow.evaluate(
                            "document.documentElement.scrollWidth <= window.innerWidth"
                        )
                    )
                    await self._screenshot(narrow, "issue74-after-320-no-media.png")

                    tablet_context, tablet = await self._page(
                        browser,
                        {"width": 768, "height": 1024},
                    )
                    contexts.append(tablet_context)
                    self.assertTrue(
                        await tablet.evaluate(
                            "document.documentElement.scrollWidth <= window.innerWidth"
                        )
                    )
                    await self._screenshot(tablet, "issue74-after-768-tablet.png")

                    reduced_context, reduced = await self._page(
                        browser,
                        {"width": 390, "height": 844},
                        reduced_motion="reduce",
                    )
                    contexts.append(reduced_context)
                    self.assertEqual(
                        await reduced.evaluate(
                            "matchMedia('(prefers-reduced-motion: reduce)').matches"
                        ),
                        True,
                    )
                    await self._screenshot(
                        reduced,
                        "issue74-after-390-reduced-motion.png",
                    )
                finally:
                    for context in reversed(contexts):
                        await context.close()
                    await browser.close()

        asyncio.run(check())

    def test_puzzle_25_keeps_answer_and_disables_skip_at_320(self):
        TeamRun.objects.filter(run_id=self.run_id, team_id="a").update(
            current_number=25,
        )

        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                context, page = await self._page(
                    browser,
                    {"width": 320, "height": 720},
                )
                try:
                    self.assertTrue(await page.locator("#answer-input").is_enabled())
                    skip = page.locator("[data-skip-action]")
                    self.assertTrue(await skip.is_disabled())
                    self.assertIn(
                        "Laatste vraag",
                        await skip.get_attribute("data-skip-disabled-label"),
                    )
                    self.assertEqual(
                        await page.locator("form[action='/team/action/skip/']").count(),
                        0,
                    )
                    self.assertTrue(
                        await page.evaluate(
                            "document.documentElement.scrollWidth <= window.innerWidth"
                        )
                    )
                    await self._screenshot(page, "issue74-after-320-final-puzzle.png")
                finally:
                    await context.close()
                    await browser.close()

        asyncio.run(check())
