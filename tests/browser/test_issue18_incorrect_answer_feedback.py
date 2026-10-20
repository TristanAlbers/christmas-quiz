"""Browser acceptance for issue #18 incorrect-answer feedback."""

import asyncio
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import LiveServerTestCase, override_settings

from quiz.application import start_game
from quiz.contracts import Actor, StartGame
from quiz.models import AccountRole


class IncorrectAnswerFeedbackBrowserTests(LiveServerTestCase):
    def setUp(self):
        if not os.environ.get("TEST_DATABASE_PATH"):
            self.skipTest("requires disposable file-backed TEST_DATABASE_PATH")

        self.snapshots = TemporaryDirectory()
        self.addCleanup(self.snapshots.cleanup)
        scope = override_settings(QUIZ_SNAPSHOT_ROOT=Path(self.snapshots.name))
        scope.enable()
        self.addCleanup(scope.disable)

        users = get_user_model()
        admin_user = users.objects.create_user("issue18-browser-admin")
        team_user = users.objects.create_user("issue18-browser-a")
        AccountRole.objects.create(user=admin_user, role="admin")
        AccountRole.objects.create(user=team_user, role="team", team_id="a")

        admin = Actor(admin_user.pk, "admin")
        start_game(admin, StartGame(str(uuid4()), "christmas-2026-demo"))

        self.client.force_login(team_user)
        self.session_cookie = self.client.cookies["sessionid"].value

    async def _page(self, browser, *, reduced_motion="no-preference"):
        context = await browser.new_context(
            viewport={"width": 390, "height": 844},
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
        page = await context.new_page()
        await page.goto(f"{self.live_server_url}/team/")
        return context, page

    async def _install_poll_probe(self, page):
        await page.evaluate(
            """() => {
                window.__gameStatusSwaps = 0;
                window.__incorrectAnswerOobSwaps = 0;

                document.body.addEventListener('htmx:oobBeforeSwap', event => {
                  if (event.detail.target?.id === 'incorrect-answer-effect') {
                    window.__incorrectAnswerOobSwaps += 1;
                  }
                });

                const gameStatus = document.getElementById('game-status');
                const gameStatusObserver = new MutationObserver(records => {
                  if (records.some(record => record.type === 'childList')) {
                    window.__gameStatusSwaps += 1;
                  }
                });
                gameStatusObserver.observe(gameStatus, {childList: true});
                window.__gameStatusObserver = gameStatusObserver;
            }"""
        )

    async def _wait_for_poll_swaps(self, page, count=2):
        baseline = await page.evaluate("window.__gameStatusSwaps")
        await page.wait_for_function(
            "([baseline, count]) => window.__gameStatusSwaps >= baseline + count",
            arg=[baseline, count],
            timeout=5000,
        )

    async def _submit_answer(self, page, answer):
        form = page.locator(".answer-form")
        action = await form.get_attribute("hx-post")
        self.assertIsNotNone(action)
        action_path = urlparse(action).path

        await page.locator("#answer-input").fill(answer)
        async with page.expect_response(
            lambda response: response.request.method == "POST"
            and urlparse(response.url).path == action_path
        ) as response_info:
            await page.locator(".answer-form .button-primary").click()
        response = await response_info.value
        self.assertEqual(response.status, 200)
        return await response.text()

    def test_wrong_submission_triggers_once_per_post_and_polling_does_not_replay(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                context, page = await self._page(browser)
                try:
                    await self._install_poll_probe(page)
                    await page.locator("#incorrect-answer-effect").evaluate(
                        "el => { window.__initialWrongAnswerEffect = el; }"
                    )

                    first_response = await self._submit_answer(page, "green")
                    self.assertEqual(
                        first_response.count('id="incorrect-answer-effect"'), 1
                    )
                    self.assertIn(
                        "incorrect-answer-effect--active", first_response
                    )
                    effect = page.locator(
                        "#incorrect-answer-effect.incorrect-answer-effect--active"
                    )
                    await effect.wait_for()
                    self.assertEqual(
                        await page.evaluate("window.__incorrectAnswerOobSwaps"), 1
                    )
                    self.assertFalse(
                        await page.evaluate(
                            """document.getElementById('incorrect-answer-effect')
                            === window.__initialWrongAnswerEffect"""
                        )
                    )
                    self.assertEqual(
                        await effect.evaluate(
                            "el => getComputedStyle(el).animationName"
                        ),
                        "incorrect-answer-overlay",
                    )
                    self.assertEqual(
                        await effect.evaluate(
                            "el => getComputedStyle(el).animationDuration"
                        ),
                        "2.75s",
                    )
                    self.assertIn(
                        "Onjuist antwoord. Probeer het opnieuw.",
                        await page.locator("#action-feedback").inner_text(),
                    )
                    self.assertEqual(await page.locator("#answer-input").count(), 1)
                    self.assertTrue(await page.locator("#answer-input").is_enabled())
                    await effect.evaluate(
                        "el => { window.__firstWrongAnswerEffect = el; }"
                    )

                    await self._wait_for_poll_swaps(page)
                    self.assertEqual(
                        await page.evaluate("window.__incorrectAnswerOobSwaps"), 1
                    )
                    self.assertTrue(
                        await page.evaluate(
                            """document.getElementById('incorrect-answer-effect')
                            === window.__firstWrongAnswerEffect"""
                        )
                    )

                    second_response = await self._submit_answer(page, "blue")
                    self.assertEqual(
                        second_response.count('id="incorrect-answer-effect"'), 1
                    )
                    self.assertIn(
                        "incorrect-answer-effect--active", second_response
                    )
                    await page.wait_for_function(
                        """() => {
                          const effect = document.getElementById(
                            'incorrect-answer-effect'
                          );
                          return effect !== window.__firstWrongAnswerEffect &&
                            effect.classList.contains(
                              'incorrect-answer-effect--active'
                            );
                        }"""
                    )
                    self.assertEqual(
                        await page.evaluate("window.__incorrectAnswerOobSwaps"), 2
                    )
                    second_effect = page.locator(
                        "#incorrect-answer-effect.incorrect-answer-effect--active"
                    )
                    await second_effect.evaluate(
                        "el => { window.__secondWrongAnswerEffect = el; }"
                    )

                    await self._wait_for_poll_swaps(page)
                    self.assertEqual(
                        await page.evaluate("window.__incorrectAnswerOobSwaps"), 2
                    )
                    self.assertTrue(
                        await page.evaluate(
                            """document.getElementById('incorrect-answer-effect')
                            === window.__secondWrongAnswerEffect"""
                        )
                    )

                    correct_response = await self._submit_answer(page, "red")
                    self.assertEqual(
                        correct_response.count('id="incorrect-answer-effect"'), 1
                    )
                    self.assertIn(
                        "incorrect-answer-effect--idle", correct_response
                    )
                    await page.wait_for_function(
                        """() => document.getElementById('incorrect-answer-effect')
                        !== window.__secondWrongAnswerEffect"""
                    )
                    self.assertEqual(
                        await page.evaluate("window.__incorrectAnswerOobSwaps"), 3
                    )
                    await page.locator("#incorrect-answer-effect").evaluate(
                        "el => { window.__clearedWrongAnswerEffect = el; }"
                    )
                    completion = page.locator(
                        '#routine-feedback[data-kind="puzzle_solved"]'
                    )
                    await completion.wait_for(state="visible", timeout=5000)
                    self.assertEqual(
                        await completion.evaluate(
                            "el => getComputedStyle(el).animationDuration"
                        ),
                        "3.5s",
                    )
                    self.assertFalse(
                        await page.locator("#incorrect-answer-effect").is_visible()
                    )

                    await self._wait_for_poll_swaps(page)
                    self.assertEqual(
                        await page.evaluate("window.__incorrectAnswerOobSwaps"), 3
                    )
                    self.assertTrue(
                        await page.evaluate(
                            """document.getElementById('incorrect-answer-effect')
                            === window.__clearedWrongAnswerEffect"""
                        )
                    )
                finally:
                    await context.close()
                    await browser.close()

        asyncio.run(check())

    def test_reduced_motion_uses_static_feedback_card(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                context, page = await self._page(browser, reduced_motion="reduce")
                try:
                    await page.locator("#answer-input").fill("green")
                    await page.locator(".answer-form .button-primary").click()
                    effect = page.locator(
                        "#incorrect-answer-effect.incorrect-answer-effect--active"
                    )
                    await effect.wait_for()
                    card = effect.locator(".incorrect-answer-effect__card")
                    self.assertEqual(
                        await card.evaluate(
                            "el => getComputedStyle(el).animationName"
                        ),
                        "none",
                    )
                    self.assertEqual(
                        await effect.evaluate(
                            "el => getComputedStyle(el).animationDuration"
                        ),
                        "2.75s",
                    )
                    self.assertIn(
                        "Onjuist antwoord. Probeer het opnieuw.",
                        await page.locator("#action-feedback").inner_text(),
                    )
                finally:
                    await context.close()
                    await browser.close()

        asyncio.run(check())
