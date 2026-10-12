"""Phase 6 Challenge presentation and polling-stability browser acceptance."""

import asyncio
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import Client, LiveServerTestCase, override_settings

from quiz.application import (
    get_team_state,
    initiate_challenge,
    start_game,
    submit_challenge_answer,
)
from quiz.contracts import Actor, RunCommand, StartGame, SubmitChallengeAnswer
from quiz.domain.phase6 import CHALLENGE_GRACE_PERIOD_MS
from quiz.models import AccountRole, Challenge, Run, TeamRun


class PhaseSixBrowserTests(LiveServerTestCase):
    def setUp(self):
        if not os.environ.get("TEST_DATABASE_PATH"):
            self.skipTest("requires disposable file-backed TEST_DATABASE_PATH")
        self.snapshots = TemporaryDirectory()
        self.addCleanup(self.snapshots.cleanup)
        scope = override_settings(QUIZ_SNAPSHOT_ROOT=Path(self.snapshots.name))
        scope.enable()
        self.addCleanup(scope.disable)

        users = get_user_model()
        self.admin_user = users.objects.create_user("phase6-browser-admin")
        self.a_user = users.objects.create_user("phase6-browser-a")
        self.b_user = users.objects.create_user("phase6-browser-b")
        AccountRole.objects.create(user=self.admin_user, role="admin")
        AccountRole.objects.create(user=self.a_user, role="team", team_id="a")
        AccountRole.objects.create(user=self.b_user, role="team", team_id="b")
        self.admin = Actor(self.admin_user.pk, "admin")
        self.a = Actor(self.a_user.pk, "team", "a")
        self.b = Actor(self.b_user.pk, "team", "b")
        self.run_id = start_game(
            self.admin, StartGame(str(uuid4()), "christmas-2026-demo")
        ).run_id

        self.cookies = {}
        for name, user in (
            ("admin", self.admin_user),
            ("a", self.a_user),
            ("b", self.b_user),
        ):
            client = Client()
            client.force_login(user)
            self.cookies[name] = client.cookies["sessionid"].value

    async def _screenshot(self, page, name):
        directory = os.environ.get("UI82_SCREENSHOT_DIR")
        if directory:
            output = Path(directory)
            output.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(output / f"{name}.png"))

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

    async def _finish_grace_period(self):
        challenge = await asyncio.to_thread(
            Challenge.objects.get,
            run_id=self.run_id,
            status="active",
        )
        await asyncio.to_thread(
            Run.objects.filter(pk=self.run_id).update,
            gameplay_elapsed_ms=(
                challenge.started_gameplay_ms + CHALLENGE_GRACE_PERIOD_MS
            ),
            advent_clock_anchor=None,
        )

    def test_free_start_gathering_tv_takeover_and_wrong_attempt_stability(self):
        TeamRun.objects.filter(run_id=self.run_id, team_id="a").update(points=0)

        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                a_context, a_page = await self._page(
                    browser,
                    "/team/",
                    {"width": 390, "height": 844},
                    self.cookies["a"],
                )
                b_context, b_page = await self._page(
                    browser,
                    "/team/",
                    {"width": 390, "height": 844},
                    self.cookies["b"],
                )
                tv_context, tv_page = await self._page(
                    browser,
                    "/overview/",
                    {"width": 1920, "height": 1080},
                )
                try:
                    await a_page.get_by_role("button", name="Winkel").click()
                    challenge_item = a_page.locator(".shop-item--challenge")
                    challenge_text = await challenge_item.inner_text()
                    self.assertIn("gratis en beschikbaar", challenge_text)
                    self.assertNotIn("punten nodig", challenge_text.lower())
                    start = challenge_item.get_by_role(
                        "button", name="Gratis uitdaging starten"
                    )
                    self.assertFalse(await start.is_disabled())

                    run_field = challenge_item.locator('input[name="run_id"]')
                    await run_field.evaluate(
                        "(el, value) => el.value = value", str(uuid4())
                    )
                    await start.click()
                    await a_page.locator("#action-feedback").get_by_text(
                        "Actie geweigerd", exact=False
                    ).wait_for(timeout=5000)
                    await run_field.evaluate(
                        "(el, value) => el.value = value", self.run_id
                    )
                    await start.click()

                    for page in (a_page, b_page):
                        stage = page.locator(".challenge-stage--starting")
                        await stage.wait_for(timeout=5000)
                        self.assertEqual(
                            await page.locator("#challenge-answer-input").count(), 0
                        )
                    self.assertIn(
                        "Jullie zijn deze uitdaging gestart",
                        await a_page.locator(".challenge-stage").inner_text(),
                    )
                    self.assertIn(
                        "Jullie zijn uitgedaagd",
                        await b_page.locator(".challenge-stage").inner_text(),
                    )
                    await tv_page.get_by_text(
                        "Verzamel je team — de uitdaging begint zo",
                        exact=True,
                    ).wait_for(timeout=5000)
                    tv_starting = await tv_page.locator(
                        ".challenge-overview"
                    ).inner_text()
                    self.assertIn("kerstuitdaging · 1 van 2", tv_starting.lower())
                    self.assertIn("Team A daagt Team B uit", tv_starting)
                    self.assertNotIn("Rendierenappel", tv_starting)
                    self.assertEqual(
                        await tv_page.locator(".public-calendar-grid").count(), 0
                    )
                    self.assertNotIn("gloeiende rode neus", tv_starting.lower())
                    self.assertNotIn("rudolph", tv_starting.lower())
                    for page in (a_page, b_page):
                        stage_text = await page.locator(".challenge-stage").inner_text()
                        self.assertNotIn("gloeiende rode neus", stage_text.lower())
                    # Both phones and the TV must visibly count down from 30
                    # without replacing the stable phone question pane.
                    initial_seconds = []
                    for page in (a_page, b_page, tv_page):
                        seconds = await page.locator(
                            "[data-challenge-countdown]"
                        ).evaluate("el => Number(el.textContent.match(/\\d+/)?.[0])")
                        self.assertGreaterEqual(seconds, 27)
                        self.assertLessEqual(seconds, 30)
                        initial_seconds.append(seconds)
                    await self._screenshot(tv_page, "challenge-gathering-tv-1920x1080")
                    await self._screenshot(a_page, "challenge-gathering-phone-390x844")
                    await a_page.wait_for_timeout(1300)
                    for page, initial in zip(
                        (a_page, b_page, tv_page), initial_seconds
                    ):
                        seconds = await page.locator(
                            "[data-challenge-countdown]"
                        ).evaluate("el => Number(el.textContent.match(/\\d+/)?.[0])")
                        self.assertLess(seconds, initial)

                    await self._finish_grace_period()
                    for page in (a_page, b_page):
                        await page.locator("#challenge-answer-input").wait_for(
                            timeout=5000
                        )
                    await tv_page.get_by_text(
                        "Rendierenappel", exact=True
                    ).wait_for(timeout=5000)
                    tv_live = await tv_page.locator(".challenge-overview").inner_text()
                    self.assertIn("gloeiende rode neus", tv_live)
                    self.assertIn("Het eerste juiste antwoord", tv_live)
                    self.assertNotIn("rudolph", tv_live.lower())
                    self.assertNotIn("challenge-a-reindeer", tv_live)
                    # The test advances the 30-second grace artificially; let the
                    # genuine short-lived start notification expire before capture.
                    await a_page.get_by_text(
                        "De uitdaging begint. Verzamel je team!", exact=True
                    ).wait_for(state="hidden", timeout=7000)
                    # Visibility is a geometry requirement: DOM text can be
                    # present yet hidden by the card's constrained flex box.
                    body_visibility = await tv_page.locator(
                        ".challenge-overview__body-scroll p"
                    ).evaluate("""el => {
                        const text = el.getBoundingClientRect();
                        const reader = el.parentElement.getBoundingClientRect();
                        const card = el.closest(
                            ".challenge-overview__question"
                        ).getBoundingClientRect();
                        return {
                            height: text.height,
                            visible: Math.min(text.bottom, reader.bottom, card.bottom)
                                - Math.max(text.top, reader.top, card.top),
                        };
                    }""")
                    self.assertGreater(body_visibility["height"], 35)
                    self.assertGreaterEqual(
                        body_visibility["visible"],
                        body_visibility["height"] - 2,
                    )
                    await self._screenshot(tv_page, "challenge-active-tv-1920x1080")
                    # A longer public question must remain readable on an
                    # unattended TV even through 500ms HTMX replacements.
                    # Stress only the rendered public text, not game authority.
                    long_body = ("Een vraag voor beide teams. " * 90).strip()
                    await tv_page.evaluate(
                        """body => {
                            const render = () => {
                                const card = document.querySelector(
                                    "[data-tv-challenge-key]"
                                );
                                if (card) card.querySelector("p").textContent = body;
                            };
                            window.__longTvQuestion = event => {
                                if (event.detail.target?.id === "overview-state") {
                                    render();
                                }
                            };
                            document.body.addEventListener(
                                "htmx:afterSwap", window.__longTvQuestion
                            );
                            render();
                        }""",
                        long_body,
                    )
                    self.assertGreater(
                        await tv_page.locator("[data-tv-challenge-key]").evaluate(
                            "el => el.scrollHeight - el.clientHeight"
                        ),
                        300,
                    )
                    heading_y = await tv_page.locator(
                        ".challenge-overview__question h3"
                    ).evaluate("el => el.getBoundingClientRect().top")
                    await tv_page.wait_for_function(
                        "() => document.querySelector("
                        "'[data-tv-challenge-key]')?.scrollTop > 80",
                        timeout=10000,
                    )
                    # A long title now shares the automatic reading flow
                    # with the body instead of clipping the latter.
                    self.assertLess(
                        await tv_page.locator(
                            ".challenge-overview__question h3"
                        ).evaluate("el => el.getBoundingClientRect().top"),
                        heading_y - 50,
                    )
                    card_bottom = await tv_page.locator(
                        ".challenge-overview__question"
                    ).evaluate("el => el.getBoundingClientRect().bottom")
                    seal_top = await tv_page.locator(
                        ".challenge-overview__seal"
                    ).evaluate("el => el.getBoundingClientRect().top")
                    self.assertLess(card_bottom, seal_top)
                    await self._screenshot(
                        tv_page, "challenge-long-question-tv-1920x1080"
                    )
                    self.assertEqual(
                        await tv_page.locator(
                            ".challenge-overview__question"
                        ).count(),
                        1,
                    )
                    await tv_page.evaluate(
                        """() => document.body.removeEventListener(
                            "htmx:afterSwap", window.__longTvQuestion
                        )"""
                    )
                    # Compare computed typography against the approved #74
                    # Advent phone sizes rather than trusting visual scaling.
                    for selector, minimum_px in (
                        (".challenge-stage__paper h2", 28.7),
                        (".challenge-stage__paper p", 19.0),
                        (".challenge-answer-form label", 15.0),
                        ("#challenge-answer-input", 16.0),
                        (".challenge-answer-form button", 16.0),
                    ):
                        rendered_px = await a_page.locator(selector).evaluate(
                            "el => parseFloat(getComputedStyle(el).fontSize)"
                        )
                        self.assertGreaterEqual(
                            rendered_px, minimum_px, selector
                        )
                    self.assertTrue(
                        await a_page.evaluate(
                            "document.documentElement.scrollWidth <= innerWidth"
                        )
                    )
                    await self._screenshot(a_page, "challenge-active-phone-390x844")

                    answer = a_page.locator("#challenge-answer-input")
                    request_id = a_page.locator(
                        '.challenge-answer-form input[name="request_id"]'
                    )
                    old_request_id = await request_id.input_value()
                    await answer.fill("snata")
                    await answer.focus()
                    await answer.evaluate(
                        """el => {
                            el.setSelectionRange(2, 2);
                            window.__challengeAnswer = el;
                        }"""
                    )
                    await a_page.wait_for_timeout(1100)
                    self.assertTrue(
                        await answer.evaluate("el => window.__challengeAnswer === el")
                    )
                    await answer.press("Enter")
                    await a_page.get_by_text(
                        "Onjuist antwoord op de uitdaging. Probeer het opnieuw."
                    ).wait_for(timeout=5000)
                    self.assertTrue(
                        await answer.evaluate(
                            "el => window.__challengeAnswer === el "
                            "&& document.activeElement === el"
                        )
                    )
                    self.assertEqual(await answer.input_value(), "snata")
                    self.assertEqual(
                        await answer.evaluate("el => el.selectionStart"), 2
                    )
                    self.assertNotEqual(await request_id.input_value(), old_request_id)

                    challenge = await asyncio.to_thread(
                        Challenge.objects.get, run_id=self.run_id
                    )
                    await asyncio.to_thread(
                        submit_challenge_answer,
                        self.b,
                        SubmitChallengeAnswer(
                            str(uuid4()),
                            self.run_id,
                            str(challenge.id),
                            challenge.question_id,
                            "rudolph",
                        ),
                    )
                    await a_page.get_by_text(
                        "Het andere team heeft gewonnen", exact=True
                    ).wait_for(timeout=5000)
                    await b_page.get_by_text(
                        "Jullie hebben de uitdaging gewonnen", exact=True
                    ).wait_for(timeout=5000)
                    calendar = tv_page.locator(".public-calendar-grid")
                    await calendar.first.wait_for(state="visible", timeout=5000)
                    self.assertEqual(
                        await tv_page.locator(".challenge-overview").count(), 0
                    )
                    self.assertEqual(await calendar.count(), 1)
                    for page in (a_page, b_page, tv_page):
                        self.assertTrue(
                            await page.evaluate(
                                "document.documentElement.scrollWidth "
                                "<= window.innerWidth"
                            )
                        )
                finally:
                    await tv_context.close()
                    await b_context.close()
                    await a_context.close()
                    await browser.close()

        asyncio.run(check())

    def test_initiator_win_freeze_admin_monitoring_and_tv_state(self):
        initiate_challenge(self.a, RunCommand(str(uuid4()), self.run_id))

        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                b_context, b_page = await self._page(
                    browser,
                    "/team/",
                    {"width": 390, "height": 844},
                    self.cookies["b"],
                )
                admin_context, admin_page = await self._page(
                    browser,
                    "/admin-game/",
                    {"width": 768, "height": 1024},
                    self.cookies["admin"],
                )
                tv_context, tv_page = await self._page(
                    browser, "/overview/", {"width": 1920, "height": 1080}
                )
                try:
                    monitor = admin_page.locator(".admin-challenge")
                    await monitor.wait_for()
                    text = await monitor.inner_text()
                    self.assertIn("uitdaging 1 van 2", text.lower())
                    self.assertIn("Team A", text)
                    self.assertIn("uitdager", text.lower())
                    self.assertIn("Team B", text)
                    self.assertIn("Geen punten afgeschreven", text)
                    self.assertIn("Voorbereiding", text)
                    await tv_page.locator(".challenge-overview--starting").wait_for(
                        timeout=5000
                    )
                    self.assertEqual(
                        await tv_page.locator(".public-calendar-grid").count(), 0
                    )

                    await self._finish_grace_period()
                    await b_page.locator("#challenge-answer-input").wait_for(
                        timeout=5000
                    )
                    await admin_page.get_by_text(
                        "De puzzel is actief.", exact=False
                    ).wait_for(timeout=5000)
                    await tv_page.get_by_text(
                        "Rendierenappel", exact=True
                    ).wait_for(timeout=5000)
                    tv_text = await tv_page.locator(
                        ".challenge-overview"
                    ).inner_text()
                    self.assertIn("Team A daagt Team B uit", tv_text)
                    self.assertNotIn("rudolph", tv_text.lower())
                    self.assertNotIn("challenge-a-reindeer", tv_text)

                    challenge = await asyncio.to_thread(
                        Challenge.objects.get, run_id=self.run_id
                    )
                    await asyncio.to_thread(
                        submit_challenge_answer,
                        self.a,
                        SubmitChallengeAnswer(
                            str(uuid4()),
                            self.run_id,
                            str(challenge.id),
                            challenge.question_id,
                            "rudolph",
                        ),
                    )
                    await b_page.get_by_text(
                        "Jullie team is bevroren", exact=True
                    ).wait_for(timeout=5000)
                    freeze_text = await b_page.locator(".freeze-message").inner_text()
                    self.assertIn("Jullie team is bevroren", freeze_text)
                    self.assertNotIn("Rendierenappel", freeze_text)
                    await admin_page.get_by_text(
                        "Team A heeft gewonnen.", exact=False
                    ).wait_for(timeout=5000)
                    self.assertIn(
                        "direct vijf minuten Freeze",
                        await monitor.inner_text(),
                    )
                    calendar = tv_page.locator(".public-calendar-grid")
                    await calendar.first.wait_for(state="visible", timeout=5000)
                    self.assertEqual(
                        await tv_page.locator(".challenge-overview").count(), 0
                    )
                    self.assertEqual(await calendar.count(), 1)
                    for page in (b_page, admin_page, tv_page):
                        self.assertTrue(
                            await page.evaluate(
                                "document.documentElement.scrollWidth "
                                "<= window.innerWidth"
                            )
                        )
                finally:
                    await tv_context.close()
                    await admin_context.close()
                    await b_context.close()
                    await browser.close()

        asyncio.run(check())

        state = get_team_state(self.b)
        self.assertEqual(state.team_state, "FREEZE")
