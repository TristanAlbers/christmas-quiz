"""Phase 5 presentation and polling-stability browser acceptance."""

import asyncio
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import Client, LiveServerTestCase, override_settings
from django.utils import timezone

from quiz.application import force_complete_current, start_game
from quiz.contracts import Actor, AdminPuzzle, StartGame
from quiz.models import AccountRole, MusicQuiz, PuzzleProgress, TeamRun


class PhaseFiveBrowserTests(LiveServerTestCase):
    def setUp(self):
        if not os.environ.get("TEST_DATABASE_PATH"):
            self.skipTest("requires disposable file-backed TEST_DATABASE_PATH")
        self.snapshots = TemporaryDirectory()
        self.addCleanup(self.snapshots.cleanup)
        scope = override_settings(QUIZ_SNAPSHOT_ROOT=Path(self.snapshots.name))
        scope.enable()
        self.addCleanup(scope.disable)

        users = get_user_model()
        self.admin_user = users.objects.create_user("phase5-browser-admin")
        self.a_user = users.objects.create_user("phase5-browser-a")
        self.b_user = users.objects.create_user("phase5-browser-b")
        AccountRole.objects.create(user=self.admin_user, role="admin")
        AccountRole.objects.create(user=self.a_user, role="team", team_id="a")
        AccountRole.objects.create(user=self.b_user, role="team", team_id="b")
        self.admin = Actor(self.admin_user.pk, "admin")
        self.run_id = start_game(
            self.admin, StartGame(str(uuid4()), "christmas-2026-demo")
        ).run_id

        self.cookies = {}
        for role, user in (
            ("admin", self.admin_user),
            ("a", self.a_user),
            ("b", self.b_user),
        ):
            client = Client()
            client.force_login(user)
            self.cookies[role] = client.cookies["sessionid"].value

    async def _page(self, browser, path, viewport, cookie=None):
        context = await browser.new_context(viewport=viewport)
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

    def _finish_music_gathering(self):
        MusicQuiz.objects.filter(run_id=self.run_id).update(
            music_elapsed_ms=60_000,
            music_clock_anchor=timezone.now(),
        )

    def test_responsive_calendars_finish_states_and_live_interaction_stability(self):
        self._put_both_teams_on_door_25()

        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                b_context, team = await self._page(
                    browser, "/team/", {"width": 390, "height": 844}, self.cookies["b"]
                )
                admin_context, admin = await self._page(
                    browser,
                    "/admin-game/",
                    {"width": 768, "height": 1024},
                    self.cookies["admin"],
                )
                tv_context, tv = await self._page(
                    browser, "/overview/", {"width": 1920, "height": 1080}
                )
                try:
                    self.assertEqual(await team.locator(".advent-door").count(), 0)
                    self.assertEqual(await admin.locator(".advent-door").count(), 50)
                    self.assertEqual(await tv.locator(".advent-door").count(), 50)
                    resources = team.locator(".team-resource-bar")
                    self.assertEqual(
                        await resources.locator(".resource-card").count(), 4
                    )
                    self.assertTrue(
                        await resources.evaluate(
                            "(bar, pane) => Boolean(bar.compareDocumentPosition(pane) "
                            "& Node.DOCUMENT_POSITION_FOLLOWING)",
                            await team.locator("#question-pane").element_handle(),
                        )
                    )
                    self.assertEqual(
                        await team.locator(".resource-card--hint").count(), 0
                    )
                    self.assertEqual(
                        await team.locator("[data-hint-action]").count(), 1
                    )
                    self.assertEqual(
                        await team.locator(".resource-card--reverse").count(), 1
                    )
                    final_skip = team.locator("[data-skip-action]")
                    self.assertEqual(await final_skip.count(), 1)
                    self.assertTrue(await final_skip.is_disabled())
                    self.assertIn("Overslaan", await final_skip.inner_text())
                    self.assertIn("Laatste vraag", await final_skip.inner_text())
                    self.assertEqual(
                        await team.locator(".shop-item--freeze").count(), 1
                    )
                    for page in (team, admin, tv):
                        self.assertTrue(
                            await page.evaluate(
                                "document.documentElement.scrollWidth "
                                "<= window.innerWidth"
                            )
                        )
                    public_text = (
                        await tv.locator("#overview-state").inner_text()
                    ).lower()
                    for private_word in (
                        "points",
                        "hint",
                        "fragment",
                        "reverse",
                        "freeze",
                    ):
                        self.assertNotIn(private_word, public_text)

                    answer = team.locator("#answer-input")
                    await answer.fill("nort")
                    await answer.focus()
                    await answer.evaluate(
                        """el => {
                            el.setSelectionRange(2, 2);
                            window.__answerNode = el;
                        }"""
                    )
                    await asyncio.to_thread(
                        force_complete_current,
                        self.admin,
                        AdminPuzzle(str(uuid4()), self.run_id, "a", "a-25"),
                    )
                    await team.get_by_text(
                        "Team A is als eerste klaar."
                    ).wait_for(timeout=5000)
                    self.assertEqual(
                        await team.locator(".shop-item--freeze").count(), 0
                    )
                    self.assertTrue(
                        await answer.evaluate(
                            "el => window.__answerNode === el "
                            "&& document.activeElement === el"
                        )
                    )
                    self.assertEqual(await answer.input_value(), "nort")
                    self.assertEqual(
                        await answer.evaluate("el => el.selectionStart"), 2
                    )
                    self.assertEqual(await team.locator(".advent-door").count(), 0)
                    self.assertTrue(
                        await team.locator("[data-skip-action]").is_disabled()
                    )

                    await answer.fill("north")
                    await team.locator(".answer-form .button-primary").click()
                    await team.locator(
                        ".endgame-team-result--complete"
                    ).wait_for(timeout=5000)
                    self.assertEqual(await team.locator("#answer-input").count(), 0)
                    self.assertEqual(await team.locator(".advent-door").count(), 0)
                    await tv.get_by_text("De adventrace is voorbij").wait_for(
                        timeout=5000
                    )
                    self.assertEqual(
                        await tv.locator(
                            ".endgame-tv-final__team--winner strong"
                        ).inner_text(),
                        "Team A",
                    )
                    await admin.get_by_text("Team A was als eerste klaar").wait_for(
                        timeout=5000
                    )
                finally:
                    await tv_context.close()
                    await admin_context.close()
                    await b_context.close()
                    await browser.close()

        asyncio.run(check())

    def test_new_door_animates_once_and_correct_answer_celebrates_team(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                team_context, team = await self._page(
                    browser, "/team/", {"width": 390, "height": 844}, self.cookies["a"]
                )
                tv_context, tv = await self._page(
                    browser, "/overview/", {"width": 1920, "height": 1080}
                )
                try:
                    self.assertEqual(
                        await tv.locator(".advent-door-opening-echo").count(), 0
                    )
                    await tv.evaluate(
                        """window.__doorAnimations = 0;
                        new MutationObserver(records => {
                          for (const record of records) {
                            for (const node of record.addedNodes) {
                              if (node.classList?.contains(
                                'advent-door-opening-echo'
                              )) {
                                window.__doorAnimations += 1;
                              }
                            }
                          }
                        }).observe(document.body, {childList: true, subtree: true});"""
                    )

                    self.assertEqual(
                        await team.locator("#answer-input").count(),
                        1,
                        await team.content(),
                    )
                    await team.locator("#answer-input").fill("red")
                    await team.locator(".answer-form .button-primary").click()
                    completion = team.locator(
                        ".door-completion:not(.door-completion--idle)"
                    )
                    await completion.wait_for()
                    await tv.locator(".advent-door-opening-echo").wait_for(timeout=5000)
                    self.assertEqual(await tv.evaluate("window.__doorAnimations"), 1)
                    self.assertEqual(
                        await tv.locator(
                            '.advent-progress[data-team-id="a"] [data-door-number="1"]'
                        ).get_attribute("aria-label"),
                        "Vakje 1: voltooid",
                    )
                    self.assertEqual(
                        await tv.locator(
                            '.advent-progress[data-team-id="b"] [data-door-number="2"]'
                        ).get_attribute("aria-label"),
                        "Vakje 2: vergrendeld",
                    )
                    await tv.wait_for_timeout(2100)
                    self.assertEqual(await tv.evaluate("window.__doorAnimations"), 1)

                    await tv.reload()
                    await tv.wait_for_timeout(800)
                    self.assertEqual(
                        await tv.locator(".advent-door-opening-echo").count(), 0
                    )
                finally:
                    await team_context.close()
                    await tv_context.close()
                    await browser.close()

        asyncio.run(check())

    def test_music_question_has_eleven_visible_steps_on_every_surface(self):
        for number in range(1, 14):
            force_complete_current(
                self.admin,
                AdminPuzzle(str(uuid4()), self.run_id, "a", f"a-{number}"),
            )

        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                contexts = []
                try:
                    for path, viewport, cookie in (
                        ("/team/", {"width": 390, "height": 844}, self.cookies["a"]),
                        (
                            "/admin-game/",
                            {"width": 768, "height": 1024},
                            self.cookies["admin"],
                        ),
                        ("/overview/", {"width": 1920, "height": 1080}, None),
                    ):
                        context, page = await self._page(
                            browser, path, viewport, cookie
                        )
                        contexts.append(context)
                        await page.locator(".music-progress").wait_for()
                        self.assertEqual(await page.locator(".music-step").count(), 11)
                        self.assertEqual(
                            await page.locator(".music-step--current").count(), 0
                        )
                        if path == "/team/":
                            self.assertEqual(
                                await page.locator(
                                    "#game-status .music-status"
                                ).count(),
                                0,
                            )
                            self.assertEqual(
                                await page.get_by_text(
                                    "Maak je klaar voor de Muziek Quiz", exact=False
                                ).count(),
                                1,
                            )
                        else:
                            await page.get_by_text(
                                "Muziek Quiz begint zo", exact=False
                            ).wait_for()

                    await asyncio.to_thread(self._finish_music_gathering)
                    for context in contexts:
                        page = context.pages[0]
                        await page.locator(".music-step--current").wait_for(
                            timeout=5000
                        )
                        self.assertEqual(
                            await page.locator(".music-step--current").count(), 1
                        )
                    self.assertEqual(
                        await contexts[0]
                        .pages[0]
                        .get_by_text("Vraag 1 van 11", exact=False)
                        .count(),
                        0,
                    )
                    for context in contexts[1:]:
                        await (
                            context.pages[0]
                            .get_by_text("Vraag 1 van 11", exact=False)
                            .wait_for()
                        )
                finally:
                    for context in contexts:
                        await context.close()
                    await browser.close()

        asyncio.run(check())
