"""Endgame celebration presentation and polling-safety acceptance."""

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
from quiz.models import AccountRole, PuzzleProgress, TeamRun


class EndgameCelebrationBrowserTests(LiveServerTestCase):
    def setUp(self):
        if not os.environ.get("TEST_DATABASE_PATH"):
            self.skipTest("requires disposable file-backed TEST_DATABASE_PATH")
        self.snapshots = TemporaryDirectory()
        self.addCleanup(self.snapshots.cleanup)
        scope = override_settings(QUIZ_SNAPSHOT_ROOT=Path(self.snapshots.name))
        scope.enable()
        self.addCleanup(scope.disable)

        users = get_user_model()
        self.admin_user = users.objects.create_user("endgame-browser-admin")
        self.a_user = users.objects.create_user("endgame-browser-a")
        self.b_user = users.objects.create_user("endgame-browser-b")
        AccountRole.objects.create(user=self.admin_user, role="admin")
        AccountRole.objects.create(user=self.a_user, role="team", team_id="a")
        AccountRole.objects.create(user=self.b_user, role="team", team_id="b")
        self.admin = Actor(self.admin_user.pk, "admin")
        self.run_id = start_game(
            self.admin, StartGame(str(uuid4()), "christmas-2026-demo")
        ).run_id

        directory = os.environ.get("UI83_SCREENSHOT_DIR")
        self.screenshot_dir = Path(directory) if directory else None
        if self.screenshot_dir:
            self.screenshot_dir.mkdir(parents=True, exist_ok=True)

        self.cookies = {}
        for role, user in (("a", self.a_user), ("b", self.b_user)):
            client = Client()
            client.force_login(user)
            self.cookies[role] = client.cookies["sessionid"].value

    async def _page(self, browser, path, viewport, cookie=None, **context_options):
        context = await browser.new_context(viewport=viewport, **context_options)
        if cookie:
            host = urlparse(self.live_server_url).hostname
            await context.add_cookies(
                [{"name": "sessionid", "value": cookie, "domain": host, "path": "/"}]
            )
        page = await context.new_page()
        await page.goto(f"{self.live_server_url}{path}")
        return context, page

    def _put_both_teams_on_door_25(self):
        PuzzleProgress.objects.filter(run_id=self.run_id, number__lt=25).update(
            completed=True, reward_awarded=True, completion_route="admin_force"
        )
        TeamRun.objects.filter(run_id=self.run_id).update(current_number=25, points=10)

    async def _shot(self, page, filename):
        if self.screenshot_dir:
            await page.screenshot(path=self.screenshot_dir / filename)

    async def _count_shows(self, page):
        await page.evaluate(
            """() => {
                const overlay = document.getElementById('endgame-celebration');
                window.__endgameShows = 0;
                window.__endgameNode = overlay;
                new MutationObserver(() => {
                    if (overlay.classList.contains('endgame-celebration--visible')) {
                        window.__endgameShows += 1;
                    }
                }).observe(overlay, {attributes: true, attributeFilter: ['class']});
            }"""
        )

    def test_first_finisher_celebrates_once_without_disrupting_runner_up(self):
        self._put_both_teams_on_door_25()

        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                a_context, team_a = await self._page(
                    browser, "/team/", {"width": 390, "height": 844}, self.cookies["a"]
                )
                b_context, team_b = await self._page(
                    browser, "/team/", {"width": 390, "height": 844}, self.cookies["b"]
                )
                tv_context, tv = await self._page(
                    browser, "/overview/", {"width": 1920, "height": 1080}
                )
                try:
                    for page in (team_a, team_b, tv):
                        await self._count_shows(page)

                    answer = team_b.locator("#answer-input")
                    await answer.fill("still playing")
                    await answer.focus()
                    await answer.evaluate(
                        """el => {
                            el.setSelectionRange(5, 5);
                            window.__answerNode = el;
                        }"""
                    )

                    await asyncio.to_thread(
                        force_complete_current,
                        self.admin,
                        AdminPuzzle(str(uuid4()), self.run_id, "a", "a-25"),
                    )

                    winner = team_a.locator(
                        '#endgame-celebration[data-endgame-result="winner"]'
                        '.endgame-celebration--visible'
                    )
                    runner_up = team_b.locator(
                        '#endgame-celebration[data-endgame-result="runner-up"]'
                        '.endgame-celebration--visible'
                    )
                    overview = tv.locator(
                        '#endgame-celebration[data-endgame-result="overview-winner"]'
                        '.endgame-celebration--visible'
                    )
                    await winner.wait_for(timeout=5000)
                    await runner_up.wait_for(timeout=5000)
                    await overview.wait_for(timeout=5000)

                    await team_a.get_by_role(
                        "heading", name="Jullie winnen!"
                    ).wait_for()
                    self.assertFalse(
                        await winner.locator(".endgame-celebration__card").is_visible()
                    )
                    await runner_up.get_by_role(
                        "heading", name="Team A was eerder"
                    ).wait_for()
                    await overview.get_by_role(
                        "heading", name="Team A wint!"
                    ).wait_for()
                    await tv.get_by_text(
                        "Team A heeft gewonnen", exact=False
                    ).wait_for()
                    self.assertEqual(
                        await winner.locator(".endgame-confetti__piece").count(), 88
                    )
                    self.assertEqual(
                        await overview.locator(".endgame-confetti__piece").count(), 120
                    )
                    await tv.locator(
                        '.advent-progress[data-team-id="a"].advent-progress--winner '
                        ".advent-victory-badge"
                    ).wait_for()
                    self.assertEqual(
                        await tv.locator(
                            '.advent-progress[data-team-id="b"] '
                            ".advent-victory-badge"
                        ).count(),
                        0,
                    )
                    # Shoot during the actual fall, not at the start off-screen.
                    await tv.wait_for_timeout(450)
                    self.assertGreaterEqual(
                        await overview.locator(
                            ".endgame-confetti__piece"
                        ).evaluate_all("""els => els.filter(el => {
                            const r = el.getBoundingClientRect();
                            return r.top > 0 && r.top < innerHeight
                                && r.left > 0 && r.left < innerWidth;
                        }).length"""),
                        55,
                    )
                    await self._shot(team_a, "a-first-winner-phone-keyframe-390.png")
                    await self._shot(tv, "a-first-tv-burst-keyframe-1920.png")

                    self.assertTrue(
                        await answer.evaluate(
                            "el => window.__answerNode === el "
                            "&& document.activeElement === el"
                        )
                    )
                    self.assertEqual(await answer.input_value(), "still playing")
                    self.assertEqual(
                        await answer.evaluate("el => el.selectionStart"),
                        5,
                    )
                    self.assertEqual(
                        await runner_up.evaluate(
                            "el => getComputedStyle(el).pointerEvents"
                        ),
                        "none",
                    )

                    await team_b.wait_for_timeout(1200)
                    for page in (team_a, team_b, tv):
                        self.assertEqual(
                            await page.evaluate("window.__endgameShows"),
                            1,
                        )
                        self.assertTrue(
                            await page.locator("#endgame-celebration").evaluate(
                                "el => window.__endgameNode === el"
                            )
                        )

                    for page in (team_a, team_b, tv):
                        await page.reload()
                        await page.wait_for_timeout(900)
                        self.assertFalse(
                            await page.locator("#endgame-celebration").evaluate(
                                "el => el.classList.contains("
                                "'endgame-celebration--visible')"
                            )
                        )
                    await team_b.get_by_text(
                        "Team A is als eerste klaar."
                    ).wait_for()
                    await tv.get_by_text(
                        "Team A heeft gewonnen", exact=False
                    ).wait_for()
                    self.assertEqual(await team_b.locator("#answer-input").count(), 1)
                    self.assertEqual(
                        await team_a.locator(".endgame-team-result--winner").count(), 1
                    )
                    self.assertEqual(await team_a.locator("#answer-input").count(), 0)
                    self.assertEqual(await team_a.locator(".shop-item form").count(), 0)
                    self.assertEqual(await tv.locator(".endgame-tv-ribbon").count(), 1)
                    self.assertEqual(await tv.locator(".advent-progress").count(), 2)
                    self.assertEqual(
                        await tv.locator(".advent-progress--winner").count(), 1
                    )
                    self.assertEqual(
                        await tv.locator(
                            '.advent-progress--winner[data-team-id="a"] '
                            ".advent-victory-badge"
                        ).inner_text(),
                        "✦ Winnaar",
                    )
                    await self._shot(team_a, "a-first-winner-phone-settled-390.png")
                    await self._shot(tv, "a-first-continuing-tv-1920.png")
                    await asyncio.to_thread(
                        force_complete_current,
                        self.admin,
                        AdminPuzzle(str(uuid4()), self.run_id, "b", "b-25"),
                    )
                    await tv.locator(".endgame-tv-final").wait_for(timeout=5000)
                    await team_b.locator(".endgame-team-result--complete").wait_for()
                    self.assertEqual(await team_b.locator("#answer-input").count(), 0)
                    self.assertEqual(
                        await tv.locator(
                            ".advent-progress .advent-door--completed"
                        ).count(),
                        50,
                    )
                    self.assertEqual(
                        await tv.locator(
                            ".endgame-tv-final__team--winner strong"
                        ).inner_text(),
                        "Team A",
                    )
                    await self._shot(team_b, "a-first-second-team-complete-390.png")
                    await tv.wait_for_timeout(1900)
                    self.assertFalse(
                        await tv.locator("#overview-audio-player").is_visible()
                    )
                    await self._shot(tv, "a-first-final-tv-1920.png")
                finally:
                    await tv_context.close()
                    await b_context.close()
                    await a_context.close()
                    await browser.close()

        asyncio.run(check())

    def test_b_first_remains_only_winner_after_a_completes(self):
        self._put_both_teams_on_door_25()

        async def check():
            from playwright.async_api import async_playwright

            # Load after the first finish: durable result, no replayed confetti.
            await asyncio.to_thread(
                force_complete_current,
                self.admin,
                AdminPuzzle(str(uuid4()), self.run_id, "b", "b-25"),
            )
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                b_context, team_b = await self._page(
                    browser, "/team/", {"width": 390, "height": 844}, self.cookies["b"]
                )
                a_context, team_a = await self._page(
                    browser, "/team/", {"width": 390, "height": 844}, self.cookies["a"]
                )
                tv_context, tv = await self._page(
                    browser, "/overview/", {"width": 1920, "height": 1080}
                )
                try:
                    await team_b.locator(".endgame-team-result--winner").wait_for()
                    await team_a.locator("#answer-input").wait_for()
                    self.assertEqual(
                        await tv.locator(".endgame-tv-ribbon").count(), 1
                    )
                    self.assertEqual(await tv.locator(".advent-progress").count(), 2)
                    self.assertEqual(
                        await tv.locator(
                            '.advent-progress--winner[data-team-id="b"] '
                            ".advent-victory-badge"
                        ).count(),
                        1,
                    )
                    self.assertEqual(
                        await tv.locator(
                            '.advent-progress[data-team-id="a"] '
                            ".advent-victory-badge"
                        ).count(),
                        0,
                    )
                    self.assertFalse(
                        await team_b.locator("#endgame-celebration").evaluate(
                            "el => el.classList.contains("
                            "'endgame-celebration--visible')"
                        )
                    )
                    await self._shot(team_b, "b-first-winner-phone-settled-390.png")
                    await self._shot(tv, "b-first-continuing-tv-1920.png")
                    answer = team_a.locator("#answer-input")
                    await answer.fill("still playing")
                    await answer.focus()
                    await asyncio.to_thread(
                        force_complete_current,
                        self.admin,
                        AdminPuzzle(str(uuid4()), self.run_id, "a", "a-25"),
                    )
                    await tv.locator(".endgame-tv-final").wait_for(timeout=5000)
                    await team_a.locator(".endgame-team-result--complete").wait_for()
                    self.assertEqual(
                        await team_b.locator(".endgame-team-result--winner").count(), 1
                    )
                    self.assertEqual(
                        await team_a.locator(".endgame-team-result--winner").count(), 0
                    )
                    self.assertEqual(
                        await tv.locator(
                            ".advent-progress .advent-door--completed"
                        ).count(),
                        50,
                    )
                    await tv.wait_for_timeout(1900)
                    await self._shot(tv, "b-first-final-tv-1920.png")
                finally:
                    await tv_context.close()
                    await a_context.close()
                    await b_context.close()
                    await browser.close()

        asyncio.run(check())

    def test_reduced_motion_keeps_static_winner_result_without_confetti(self):
        self._put_both_teams_on_door_25()

        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                tv_context, tv = await self._page(
                    browser,
                    "/overview/",
                    {"width": 1280, "height": 720},
                    reduced_motion="reduce",
                )
                try:
                    await asyncio.to_thread(
                        force_complete_current,
                        self.admin,
                        AdminPuzzle(str(uuid4()), self.run_id, "a", "a-25"),
                    )
                    overlay = tv.locator(
                        '#endgame-celebration[data-endgame-result="overview-winner"]'
                        '.endgame-celebration--visible'
                    )
                    await overlay.wait_for(timeout=5000)
                    await tv.get_by_text(
                        "Team A heeft gewonnen", exact=False
                    ).wait_for()
                    self.assertEqual(
                        await overlay.locator(".endgame-confetti__piece").count(), 0
                    )
                    self.assertEqual(
                        await overlay.locator(".endgame-celebration__card").evaluate(
                            "el => getComputedStyle(el).animationName"
                        ),
                        "none",
                    )
                finally:
                    await tv_context.close()
                    await browser.close()

        asyncio.run(check())
