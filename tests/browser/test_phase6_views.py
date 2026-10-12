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

        screenshot_dir = os.environ.get("UI82_SCREENSHOT_DIR")
        self.screenshot_dir = Path(screenshot_dir) if screenshot_dir else None
        if self.screenshot_dir:
            self.screenshot_dir.mkdir(parents=True, exist_ok=True)

        self.cookies = {}
        for name, user in (
            ("admin", self.admin_user),
            ("a", self.a_user),
            ("b", self.b_user),
        ):
            client = Client()
            client.force_login(user)
            self.cookies[name] = client.cookies["sessionid"].value

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

    async def _screenshot(self, page, name):
        if self.screenshot_dir:
            await page.screenshot(path=self.screenshot_dir / name, full_page=False)

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
                    # Reproduce the opponent's shop staying open through the
                    # authoritative Challenge takeover and 500 ms action swap.
                    await b_page.get_by_role("button", name="Winkel").click()
                    await b_page.locator("#team-shop-dialog[open]").wait_for()
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

                    for page, team_id in ((a_page, "A"), (b_page, "B")):
                        stage = page.locator(".challenge-stage--starting")
                        await stage.wait_for(timeout=5000)
                        await page.locator("#team-shop-dialog").wait_for(
                            state="detached", timeout=5000
                        )
                        self.assertEqual(
                            await page.locator(".shop-item").count(), 0
                        )
                        self.assertEqual(
                            await page.locator("#challenge-answer-input").count(), 0
                        )
                        status = page.locator(".challenge-status--active strong")
                        self.assertIn(f"Team {team_id}", await status.inner_text())
                        self.assertTrue(await status.is_visible())
                    self.assertIn(
                        "Jullie zijn de uitdaging gestart",
                        await a_page.locator(".challenge-status--active").inner_text(),
                    )
                    self.assertIn(
                        "Het andere team heeft jullie uitgedaagd",
                        await b_page.locator(".challenge-status--active").inner_text(),
                    )
                    await tv_page.get_by_text(
                        "Verzamel je team — de uitdaging begint zo",
                        exact=True,
                    ).wait_for(timeout=5000)
                    tv_starting = await tv_page.locator(
                        ".challenge-overview"
                    ).inner_text()
                    self.assertIn("kerstuitdaging · 1 van 2", tv_starting.lower())
                    self.assertEqual(
                        await tv_page.get_by_role(
                            "heading", name="Team A daagt Team B uit"
                        ).count(),
                        1,
                    )
                    self.assertNotIn("Rendierenappel", tv_starting)
                    self.assertNotIn(
                        "gloeiende rode neus",
                        await tv_page.locator(".challenge-overview").text_content(),
                    )
                    await self._screenshot(
                        tv_page, "challenge-gathering-tv-1920x1080.png"
                    )
                    clock = await a_page.locator(
                        ".team-advent-meta > span:last-child"
                    ).bounding_box()
                    stage_box = await a_page.locator(
                        ".challenge-stage"
                    ).bounding_box()
                    self.assertIsNotNone(clock)
                    self.assertIsNotNone(stage_box)
                    self.assertLessEqual(
                        clock["y"] + clock["height"], stage_box["y"] - 4
                    )
                    await self._screenshot(
                        a_page, "challenge-gathering-team-a-390x844.png"
                    )
                    self.assertEqual(
                        await tv_page.locator(".public-calendar-grid").count(), 0
                    )

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
                    # Match the accepted #74 phone legibility floor, while
                    # keeping the V4 Challenge question visibly dominant.
                    for selector, minimum_px in (
                        (".team-advent-meta > span:last-child", 15),
                        (".challenge-status--active strong", 14),
                        (".challenge-stage__kicker", 14),
                        (".challenge-question-phone > span", 14),
                        (".challenge-question-phone h2", 18),
                        (".challenge-question-phone p", 22),
                        (".challenge-answer-form label", 15),
                        (".challenge-answer-form button", 16),
                        (".challenge-stage__footnote", 14),
                    ):
                        font_px = await a_page.locator(selector).evaluate(
                            "el => parseFloat(getComputedStyle(el).fontSize)"
                        )
                        self.assertGreaterEqual(
                            font_px, minimum_px, f"{selector}: {font_px}px"
                        )
                    self.assertGreaterEqual(
                        await tv_page.locator(
                            ".challenge-overview__question p"
                        ).evaluate(
                            "el => parseFloat(getComputedStyle(el).fontSize)"
                        ),
                        36,
                    )
                    # Let the one-shot start acknowledgement clear before comparison.
                    await a_page.wait_for_timeout(5200)
                    await self._screenshot(
                        tv_page, "challenge-active-tv-1920x1080.png"
                    )
                    await self._screenshot(
                        a_page, "challenge-active-team-a-390x844.png"
                    )

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


    def test_team_b_initiates_reconnects_and_narrow_long_text_stays_readable(self):
        initiate_challenge(self.b, RunCommand(str(uuid4()), self.run_id))

        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                phone_context, phone = await self._page(
                    browser,
                    "/team/",
                    {"width": 320, "height": 720},
                    self.cookies["a"],
                )
                tv_context, tv = await self._page(
                    browser, "/overview/", {"width": 1920, "height": 1080}
                )
                try:
                    await phone.locator(".challenge-stage--starting").wait_for()
                    await tv.locator(".challenge-overview--starting").wait_for()
                    for page in (phone, tv):
                        self.assertNotIn(
                            "De vijfde kerstdag",
                            await page.locator("body").inner_text(),
                        )
                    self.assertEqual(
                        await phone.locator("#challenge-answer-input").count(), 0
                    )

                    # Refresh cannot expose the question before grace expiry.
                    await phone.reload()
                    await tv.reload()
                    self.assertEqual(
                        await phone.locator("#challenge-answer-input").count(), 0
                    )
                    self.assertNotIn(
                        "gouden ringen",
                        await tv.locator(".challenge-overview").inner_text(),
                    )

                    await self._finish_grace_period()
                    await phone.locator("#challenge-answer-input").wait_for(
                        timeout=5000
                    )
                    await tv.get_by_text(
                        "De vijfde kerstdag", exact=True
                    ).wait_for(timeout=5000)
                    await phone.emulate_media(reduced_motion="reduce")
                    self.assertTrue(
                        await phone.evaluate(
                            "matchMedia('(prefers-reduced-motion: reduce)').matches"
                        )
                    )
                    self.assertLessEqual(
                        await phone.evaluate(
                            "document.documentElement.scrollWidth"
                        ),
                        320,
                    )
                    # Layout-only stress: long server-shaped content must wrap.
                    await phone.locator(".challenge-question-phone p").evaluate(
                        "el => el.textContent = el.textContent.repeat(9)"
                    )
                    self.assertLessEqual(
                        await phone.evaluate(
                            "document.documentElement.scrollWidth"
                        ),
                        320,
                    )
                    self.assertGreater(
                        await phone.evaluate(
                            "document.documentElement.scrollHeight"
                        ),
                        720,
                    )
                    clock = phone.locator(".team-advent-meta")
                    self.assertTrue(await clock.evaluate(
                        "el => getComputedStyle(el).position === 'absolute'"
                    ))
                    self.assertTrue(await clock.is_visible())
                    self.assertTrue(await clock.evaluate(
                        "el => el.closest('.app-shell') !== null"
                    ))
                    clock_before = (await clock.bounding_box())["y"]
                    await phone.evaluate(
                        "window.scrollTo(0, document.documentElement.scrollHeight)"
                    )
                    await phone.wait_for_function("window.scrollY > 30")
                    clock_after = (await clock.bounding_box())["y"]
                    self.assertLess(clock_after, clock_before - 30)

                    await phone.reload()
                    await phone.locator("#challenge-answer-input").wait_for(
                        timeout=5000
                    )
                    self.assertIn(
                        "gouden ringen",
                        await phone.locator(".challenge-question-phone").inner_text(),
                    )
                    await phone.set_viewport_size({"width": 768, "height": 1024})
                    self.assertLessEqual(
                        await phone.evaluate(
                            "document.documentElement.scrollWidth"
                        ),
                        768,
                    )
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
                            "5",
                        ),
                    )
                    await phone.locator(".freeze-message").wait_for(
                        timeout=5000
                    )
                    await tv.locator(".public-calendar-grid").wait_for(
                        timeout=5000
                    )
                finally:
                    await tv_context.close()
                    await phone_context.close()
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
                    self.assertEqual(
                        await tv_page.get_by_role(
                            "heading", name="Team A daagt Team B uit"
                        ).count(),
                        1,
                    )
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
