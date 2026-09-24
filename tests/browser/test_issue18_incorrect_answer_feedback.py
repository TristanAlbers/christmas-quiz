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

    def test_wrong_submission_triggers_once_per_post_and_polling_does_not_replay(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                context, page = await self._page(browser)
                try:
                    await page.evaluate(
                        """window.__wrongAnswerEffects = 0;
                        new MutationObserver(records => {
                          for (const record of records) {
                            for (const node of record.addedNodes) {
                              if (
                                node.id === 'incorrect-answer-effect' &&
                                node.classList?.contains('incorrect-answer-effect--active')
                              ) {
                                window.__wrongAnswerEffects += 1;
                              }
                            }
                          }
                        }).observe(document.body, {childList: true, subtree: true});"""
                    )

                    await page.locator("#answer-input").fill("green")
                    await page.locator(".answer-form .button-primary").click()
                    await page.locator(
                        "#incorrect-answer-effect.incorrect-answer-effect--active"
                    ).wait_for()
                    self.assertIn(
                        "Incorrect answer. Try again.",
                        await page.locator("#action-feedback").inner_text(),
                    )
                    self.assertEqual(await page.evaluate("window.__wrongAnswerEffects"), 1)
                    self.assertEqual(await page.locator("#answer-input").count(), 1)
                    self.assertTrue(await page.locator("#answer-input").is_enabled())

                    await page.wait_for_timeout(1300)
                    self.assertEqual(await page.evaluate("window.__wrongAnswerEffects"), 1)

                    await page.locator("#answer-input").fill("blue")
                    await page.locator(".answer-form .button-primary").click()
                    await page.wait_for_function("window.__wrongAnswerEffects === 2")
                    await page.wait_for_timeout(700)
                    self.assertEqual(await page.evaluate("window.__wrongAnswerEffects"), 2)

                    await page.locator("#answer-input").fill("red")
                    await page.locator(".answer-form .button-primary").click()
                    await page.get_by_text(
                        "Correct answer. Puzzle completed.", exact=True
                    ).wait_for()
                    await page.wait_for_timeout(700)
                    self.assertEqual(await page.evaluate("window.__wrongAnswerEffects"), 2)
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
                        "1.75s",
                    )
                    self.assertIn(
                        "Incorrect answer. Try again.",
                        await page.locator("#action-feedback").inner_text(),
                    )
                finally:
                    await context.close()
                    await browser.close()

        asyncio.run(check())
