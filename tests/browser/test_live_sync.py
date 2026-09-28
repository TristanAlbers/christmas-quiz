"""Chromium acceptance for authenticated HTMX polling and command ordering.

Run only with TEST_DATABASE_PATH set to a disposable file. The live server and
browser never access the mounted event database in ./var.
"""

import asyncio
import os
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import LiveServerTestCase, override_settings

from quiz.application import start_game, submit_answer
from quiz.contracts import Actor, StartGame, SubmitAnswer
from quiz.models import AccountRole, Attempt


class LiveSyncBrowserTests(LiveServerTestCase):
    def setUp(self):
        if not os.environ.get("TEST_DATABASE_PATH"):
            self.skipTest("requires disposable file-backed TEST_DATABASE_PATH")
        self.snapshots = TemporaryDirectory()
        self.addCleanup(self.snapshots.cleanup)
        scope = override_settings(QUIZ_SNAPSHOT_ROOT=Path(self.snapshots.name))
        scope.enable()
        self.addCleanup(scope.disable)
        users = get_user_model()
        admin = users.objects.create_user("browser-admin", password="admin-pin")
        self.a = users.objects.create_user("browser-a", password="a-pin")
        AccountRole.objects.create(user=admin, role="admin")
        AccountRole.objects.create(user=self.a, role="team", team_id="a")
        self.actor = Actor(self.a.pk, "team", "a")
        self.run_id = start_game(
            Actor(admin.pk, "admin"), StartGame(str(uuid4()), "christmas-2026-demo")
        ).run_id
        self.client.force_login(self.a)
        self.session_cookie = self.client.cookies["sessionid"].value

    async def _open_team_page(self, playwright):
        browser = await playwright.chromium.launch()
        context = await browser.new_context()
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
        page_errors = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        await page.goto(f"{self.live_server_url}/team/")
        await page.locator("#answer-input").wait_for()
        return browser, context, page, page_errors

    async def _wait_for_three_state_polls(self, page):
        baseline = await page.evaluate("window.__gameStatusSwaps")
        await page.wait_for_function(
            "baseline => window.__gameStatusSwaps >= baseline + 3",
            arg=baseline,
            timeout=5000,
        )

    async def _watch_state_polls(self, page):
        await page.evaluate(
            """() => {
                window.__gameStatusSwaps = 0;
                const status = document.getElementById('game-status');
                const observer = new MutationObserver(records => {
                    if (records.some(record => record.type === 'childList')) {
                        window.__gameStatusSwaps += 1;
                    }
                });
                observer.observe(status, {childList: true});
            }"""
        )

    def test_wrong_answer_feedback_survives_later_polls(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser, context, page, _ = await self._open_team_page(playwright)
                try:
                    await self._watch_state_polls(page)
                    await page.locator("#answer-input").fill("green")
                    await page.locator(
                        "#question-pane form[action='/team/answer/'] "
                        "button[type=submit]"
                    ).click()
                    feedback = page.locator("#action-feedback")
                    await feedback.filter(
                        has_text="Incorrect answer. Try again."
                    ).wait_for()
                    await self._wait_for_three_state_polls(page)
                    self.assertIn("Incorrect answer", await feedback.inner_text())
                    question = await page.locator("#question-pane").inner_text()
                    self.assertIn("Demo A1", question)
                finally:
                    await context.close()
                    await browser.close()

        asyncio.run(check())
        self.assertEqual(
            Attempt.objects.filter(team_id="a", is_correct=False).count(), 1
        )

    def test_rejected_hint_feedback_survives_later_polls(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser, context, page, _ = await self._open_team_page(playwright)
                try:
                    await self._watch_state_polls(page)
                    hint_action = page.locator("[data-hint-action]")
                    self.assertTrue(await hint_action.is_disabled())
                    async with page.expect_response(
                        lambda response: "/team/action/use-hint/" in response.url
                        and response.status == 409
                    ):
                        await page.locator(
                            "form[action='/team/action/use-hint/']"
                        ).evaluate("form => form.requestSubmit()")
                    feedback = page.locator("#action-feedback")
                    await feedback.filter(has_text="no hint tokens").wait_for()
                    await self._wait_for_three_state_polls(page)
                    self.assertIn("no hint tokens", await feedback.inner_text())
                    question = await page.locator("#question-pane").inner_text()
                    self.assertIn("Demo A1", question)
                finally:
                    await context.close()
                    await browser.close()

        asyncio.run(check())

    def test_poll_preserves_typing_focus_and_serves_local_static(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser, context, page, page_errors = await self._open_team_page(
                    playwright
                )
                try:
                    self.assertFalse(settings.DEBUG)
                    script_url = await page.locator("script[src]").first.get_attribute(
                        "src"
                    )
                    script_response = await context.request.get(
                        f"{self.live_server_url}{script_url}"
                    )
                    stylesheet_urls = await page.locator(
                        "link[rel=stylesheet]"
                    ).evaluate_all(
                        "links => links.map(link => link.getAttribute('href'))"
                    )
                    self.assertGreaterEqual(len(stylesheet_urls), 1)
                    self.assertEqual(script_response.status, 200)
                    self.assertRegex(script_url, r"\.[0-9a-f]{12}\.js$")
                    for stylesheet_url in stylesheet_urls:
                        stylesheet_response = await context.request.get(
                            f"{self.live_server_url}{stylesheet_url}"
                        )
                        self.assertEqual(stylesheet_response.status, 200)
                        self.assertRegex(
                            stylesheet_url, r"\.[0-9a-f]{12}\.css$"
                        )
                    self.assertTrue(
                        await page.evaluate("Boolean(window.htmx)"),
                        f"script={script_url} HTTP={script_response.status} "
                        f"page_errors={page_errors}",
                    )
                    self.assertEqual(await page.locator("#live-game").count(), 1)
                    field = page.locator("#answer-input")
                    two_polls = asyncio.Event()
                    poll_responses = 0

                    def count_polls(response):
                        nonlocal poll_responses
                        if "/team/state/" in response.url:
                            poll_responses += 1
                            if poll_responses >= 2:
                                two_polls.set()

                    page.on("response", count_polls)
                    await field.fill("typing continues")
                    await field.focus()
                    await field.evaluate("el => el.setSelectionRange(4, 4)")
                    await asyncio.wait_for(two_polls.wait(), 5)
                    self.assertEqual(await field.input_value(), "typing continues")
                    self.assertTrue(
                        await field.evaluate("el => document.activeElement === el")
                    )
                    self.assertEqual(await field.evaluate("el => el.selectionStart"), 4)
                    self.assertEqual(await page.locator("#live-game").count(), 1)
                finally:
                    await context.close()
                    await browser.close()

        asyncio.run(check())

    def test_answer_post_replaces_slow_poll_and_late_reply_cannot_overwrite(self):
        async def check():
            from playwright.async_api import Error as PlaywrightError
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser, context, page, _ = await self._open_team_page(playwright)
                poll_held = asyncio.Event()
                poll_release = asyncio.Event()
                post_seen = asyncio.Event()
                post_release = asyncio.Event()
                poll_count = 0

                async def intercept_poll(route):
                    nonlocal poll_count
                    poll_count += 1
                    if not poll_held.is_set():
                        response = await route.fetch()
                        poll_held.set()
                        await poll_release.wait()
                        try:
                            await route.fulfill(response=response)
                        except PlaywrightError:
                            # HTMX can abort this deliberately obsolete request.
                            return
                    else:
                        await route.continue_()

                async def intercept_post(route):
                    post_seen.set()
                    await post_release.wait()
                    await route.continue_()

                await page.route(re.compile(r"/team/state/(?:\?|$)"), intercept_poll)
                await page.route("**/team/answer/", intercept_post)
                try:
                    await asyncio.wait_for(poll_held.wait(), 5)
                    await page.locator("#answer-input").fill("red")
                    submit_task = asyncio.create_task(
                        page.locator(
                            "#question-pane form[action='/team/answer/'] "
                            "button[type=submit]"
                        ).click()
                    )
                    await asyncio.wait_for(post_seen.wait(), 5)
                    count_during_command = poll_count
                    await page.wait_for_timeout(1100)
                    self.assertEqual(poll_count, count_during_command)
                    post_release.set()
                    await submit_task
                    await page.get_by_text("Demo A2", exact=False).wait_for(
                        timeout=5000
                    )
                    poll_release.set()
                    await page.wait_for_timeout(600)
                    self.assertIn(
                        "Demo A2", await page.locator("#live-game").inner_text()
                    )
                    self.assertEqual(await page.locator("#live-game").count(), 1)
                finally:
                    post_release.set()
                    poll_release.set()
                    await context.close()
                    await browser.close()

        asyncio.run(check())
        self.assertEqual(
            Attempt.objects.filter(team_id="a", is_correct=True).count(), 1
        )

    def test_reconnect_and_return_to_visible_tab_reconcile_server_state(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser, context, page, _ = await self._open_team_page(playwright)
                try:
                    await context.set_offline(True)
                    other_tab = await context.new_page()
                    await other_tab.bring_to_front()
                    await asyncio.to_thread(
                        submit_answer,
                        self.actor,
                        SubmitAnswer(str(uuid4()), self.run_id, "a-1", "red"),
                    )
                    await context.set_offline(False)
                    await page.bring_to_front()
                    await page.get_by_text("Demo A2", exact=False).wait_for(
                        timeout=5000
                    )
                    self.assertEqual(await page.locator("#answer-input").count(), 1)
                finally:
                    await context.close()
                    await browser.close()

        asyncio.run(check())
