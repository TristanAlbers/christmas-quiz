"""Real Django/HTMX visual and lifecycle checks for issue #107."""

import asyncio
import os
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.templatetags.static import static
from django.test import Client, LiveServerTestCase
from django.urls import reverse

from quiz.application import (
    admin_unfreeze,
    force_complete_current,
    get_team_state,
    initiate_challenge,
    start_game,
    submit_challenge_answer,
)
from quiz.contracts import (
    Actor,
    AdminPuzzle,
    AdminTeam,
    RunCommand,
    StartGame,
    SubmitChallengeAnswer,
)
from quiz.domain.phase6 import CHALLENGE_GRACE_PERIOD_MS
from quiz.models import AccountRole, Challenge, PuzzleProgress, Run, TeamRun


class MidnightImpactBrowserTests(LiveServerTestCase):
    def setUp(self):
        if not os.environ.get("TEST_DATABASE_PATH"):
            self.skipTest("requires disposable file-backed TEST_DATABASE_PATH")
        users = get_user_model()
        admin_user = users.objects.create_user("issue107-browser-admin")
        team_user = users.objects.create_user("issue107-browser-team")
        opponent_user = users.objects.create_user("issue107-browser-opponent")
        AccountRole.objects.create(user=admin_user, role="admin")
        AccountRole.objects.create(user=team_user, role="team", team_id="a")
        AccountRole.objects.create(user=opponent_user, role="team", team_id="b")
        self.admin = Actor(admin_user.pk, "admin")
        self.team = Actor(team_user.pk, "team", "a")
        self.opponent = Actor(opponent_user.pk, "team", "b")
        self.run_id = start_game(
            self.admin,
            StartGame(str(uuid4()), "christmas-2026-demo"),
        ).run_id
        TeamRun.objects.filter(run_id=self.run_id).update(points=50)
        client = Client()
        client.force_login(team_user)
        self.session_cookie = client.cookies["sessionid"].value
        self.expected_music_note_url = static("quiz/chocolates/muzieknoot.png")
        opponent_client = Client()
        opponent_client.force_login(opponent_user)
        self.opponent_cookie = opponent_client.cookies["sessionid"].value
        output = os.environ.get("UI107_SCREENSHOT_DIR")
        self.output_dir = Path(output) if output else None
        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)

    async def open_phone(self, playwright, session_cookie=None):
        engine = os.environ.get("ISSUE107_BROWSER_ENGINE", "chromium")
        if engine not in {"chromium", "webkit"}:
            raise ValueError("ISSUE107_BROWSER_ENGINE must be chromium or webkit")
        browser = await getattr(playwright, engine).launch()
        context_options = dict(
            viewport={"width": 390, "height": 844},
            device_scale_factor=1,
            reduced_motion="reduce",
        )
        if self.output_dir:
            raw_video_dir = self.output_dir / ".raw-videos"
            raw_video_dir.mkdir(parents=True, exist_ok=True)
            context_options.update(
                record_video_dir=str(raw_video_dir),
                record_video_size={"width": 390, "height": 844},
            )
        context = await browser.new_context(**context_options)
        host = urlparse(self.live_server_url).hostname
        await context.add_cookies(
            [
                {
                    "name": "sessionid",
                    "value": session_cookie or self.session_cookie,
                    "domain": host,
                    "path": "/",
                }
            ]
        )
        page = await context.new_page()
        response = await page.goto(f"{self.live_server_url}/team/")
        self.assertIsNotNone(response)
        self.assertEqual(response.status, 200)
        await page.locator(".team-advent-panel").wait_for(timeout=5000)
        return browser, context, page

    async def close_phone(self, context, page, video_name):
        video = page.video
        await context.close()
        if not self.output_dir or video is None:
            return
        engine = os.environ.get("ISSUE107_BROWSER_ENGINE", "chromium")
        target = self.output_dir / f"actual-{video_name}-{engine}-390x844.webm"
        raw_path = Path(await video.path())
        await video.save_as(str(target))
        if raw_path != target:
            raw_path.unlink(missing_ok=True)

    async def capture(self, page, name):
        if self.output_dir:
            engine = os.environ.get("ISSUE107_BROWSER_ENGINE", "chromium")
            await page.screenshot(
                path=str(self.output_dir / f"actual-{name}-{engine}-390x844.png"),
                full_page=False,
            )

    async def capture_reference(self, browser):
        reference = os.environ.get("UI107_REFERENCE_HTML")
        if not reference or not self.output_dir:
            return
        reference_path = Path(reference).resolve()
        self.assertTrue(reference_path.is_file())
        references = {
            "solve": ("Puzzel opgelost", 3500),
            "reverse": ("Reverse kopen", 3400),
            "skip": ("Overslaan", 2800),
            "hint": ("Hint kopen", 2700),
        }
        for key, (label, duration_ms) in references.items():
            context = await browser.new_context(
                viewport={"width": 390, "height": 844},
                device_scale_factor=1,
                reduced_motion="reduce",
            )
            page = await context.new_page()
            try:
                await page.goto(reference_path.as_uri())
                await page.get_by_role("button", name=label).click()
                await page.add_style_tag(
                    content="""
                    html,body,main,#qm-motion-next,.qm-stage{margin:0!important;padding:0!important;
                      width:390px!important;height:844px!important;max-width:none!important;
                      min-height:0!important;overflow:hidden!important}
                    body>main>header,.demo-note,.qm-controls{display:none!important}
                    #qm-motion-next .qm-phone{width:390px!important;
                      height:844px!important;
                      border:0!important;border-radius:0!important;box-shadow:none!important}
                    """
                )
                await page.wait_for_timeout(round(duration_ms * 0.62))
                await page.locator(".qm-phone").screenshot(
                    path=str(self.output_dir / f"reference-{key}-hold-390x844.png")
                )
            finally:
                await context.close()

    async def wait_for_film(self, page, kind, expected_duration):
        film = page.locator(f'#routine-feedback[data-kind="{kind}"]')
        await film.wait_for(state="visible", timeout=5000)
        self.assertEqual(
            await film.evaluate("el => getComputedStyle(el).animationDuration"),
            expected_duration,
        )
        self.assertTrue(await page.locator(".app-shell").evaluate("el => el.inert"))
        return film

    def resolve_challenge_for_opponent(self):
        initiate_challenge(
            self.team,
            RunCommand(str(uuid4()), self.run_id),
        )
        challenge = Challenge.objects.get(run_id=self.run_id, status="active")
        Run.objects.filter(pk=self.run_id).update(
            gameplay_elapsed_ms=(
                challenge.started_gameplay_ms + CHALLENGE_GRACE_PERIOD_MS
            ),
            advent_clock_anchor=None,
        )
        submit_challenge_answer(
            self.opponent,
            SubmitChallengeAnswer(
                str(uuid4()),
                self.run_id,
                str(challenge.id),
                challenge.question_id,
                "rudolph",
            ),
        )
        self.assertEqual(get_team_state(self.team).team_state, "PUZZLE")

    def test_all_four_confirmed_actions_use_one_full_motion_surface(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser, context, page = await self.open_phone(playwright)
                try:
                    await self.capture_reference(browser)

                    await page.locator("#answer-input").fill(
                        "Mijn onvoltooide antwoord"
                    )
                    await page.evaluate(
                        "window.__purchaseDraft = "
                        "document.getElementById('answer-input')"
                    )
                    await page.get_by_role("button", name="Winkel", exact=False).click()
                    await page.get_by_role("button", name="Hint kopen (1)").click()
                    film = await self.wait_for_film(page, "hint_purchased", "2.7s")
                    self.assertEqual(
                        await film.locator("h2").inner_text(), "Een lichtpuntje"
                    )
                    self.assertEqual(
                        await film.locator(".routine-feedback__letter").inner_text(),
                        "?",
                    )
                    await page.wait_for_timeout(round(2700 * 0.62))
                    await self.capture(page, "hint-hold")
                    await film.wait_for(state="hidden", timeout=4000)
                    self.assertEqual(
                        await page.locator("#answer-input").input_value(),
                        "Mijn onvoltooide antwoord",
                    )
                    self.assertTrue(await page.evaluate(
                        "window.__purchaseDraft === "
                        "document.getElementById('answer-input')"
                    ))
                    await self.capture(page, "hint-settled")

                    await page.get_by_role("button", name="Winkel", exact=False).click()
                    await page.get_by_role(
                        "button", name="Uno Reverse kopen (2)"
                    ).click()
                    film = await self.wait_for_film(page, "reverse_purchased", "3.4s")
                    self.assertEqual(
                        await film.locator("h2").inner_text(), "Reverse staat klaar"
                    )
                    purchase_paths = await film.locator("svg path").evaluate_all(
                        "paths => paths.map(path => path.getAttribute('d'))"
                    )
                    shop_paths = await page.locator(
                        ".shop-item--reverse .resource-reverse-card__symbol svg path"
                    ).evaluate_all("paths => paths.map(path => path.getAttribute('d'))")
                    self.assertEqual(purchase_paths, shop_paths)
                    await page.wait_for_timeout(round(3400 * 0.62))
                    await self.capture(page, "reverse-hold")
                    await film.wait_for(state="hidden", timeout=4500)
                    self.assertEqual(
                        await page.locator("#answer-input").input_value(),
                        "Mijn onvoltooide antwoord",
                    )
                    self.assertTrue(await page.evaluate(
                        "window.__purchaseDraft === "
                        "document.getElementById('answer-input')"
                    ))
                    reverse_text = await page.locator(
                        ".resource-card--reverse"
                    ).inner_text()
                    self.assertIn("ACTIEF", reverse_text.upper())
                    await self.capture(page, "reverse-settled")

                    await page.locator("[data-skip-action]").click()
                    film = await self.wait_for_film(page, "puzzle_skipped", "2.8s")
                    self.assertEqual(
                        await film.locator("h2").inner_text(), "Een deur verder"
                    )
                    self.assertEqual(
                        await film.locator(
                            ".routine-feedback__page--current strong"
                        ).inner_text(),
                        "1",
                    )
                    self.assertEqual(
                        await film.locator(
                            ".routine-feedback__page--next strong"
                        ).inner_text(),
                        "2",
                    )
                    await page.wait_for_timeout(round(2800 * 0.62))
                    await self.capture(page, "skip-hold")
                    await film.wait_for(state="hidden", timeout=4000)
                    await self.capture(page, "skip-settled")

                    await page.locator("#answer-input").fill("3")
                    await page.evaluate(
                        """() => document.body.addEventListener(
                          'routineFeedbackConfirmed',
                          event => { window.__issue107Detail = event.detail; },
                          {once:true}
                        )"""
                    )
                    await page.get_by_role("button", name="Antwoord insturen").click()
                    film = await self.wait_for_film(page, "puzzle_solved", "3.5s")
                    solved_film_text = (await film.inner_text()).lower()
                    self.assertEqual(
                        await film.locator("h2").inner_text(), "Goed gevonden!"
                    )
                    chocolate = film.locator(".routine-feedback__chocolate")
                    self.assertEqual(
                        await chocolate.get_attribute("data-chocolate-subject"),
                        "muzieknoot",
                    )
                    self.assertEqual(
                        await chocolate.locator("image").get_attribute("href"),
                        self.expected_music_note_url,
                    )
                    self.assertEqual(
                        await chocolate.locator("svg").get_attribute("viewBox"),
                        "247 123 854 1063",
                    )
                    await page.wait_for_timeout(round(3500 * 0.62))
                    await self.capture(page, "solve-hold")
                    await film.wait_for(state="hidden", timeout=4500)
                    await self.capture(page, "solve-settled")

                    await page.evaluate(
                        """() => document.body.dispatchEvent(new CustomEvent(
                          'routineFeedbackConfirmed', {detail: window.__issue107Detail}
                        ))"""
                    )
                    await page.wait_for_timeout(200)
                    self.assertFalse(await film.is_visible())
                    self.assertFalse(
                        await page.locator(".app-shell").evaluate("el => el.inert")
                    )
                    self.assertNotIn("fragment", solved_film_text)
                    self.assertTrue(
                        await page.evaluate(
                            "document.documentElement.scrollWidth <= innerWidth"
                        )
                    )
                finally:
                    await self.close_phone(context, page, "all-four-actions")
                    await browser.close()

        asyncio.run(check())

    def test_attack_interrupts_discards_lock_and_does_not_block_later_feedback(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser, context, page = await self.open_phone(playwright)
                other_browser, other_context, other = await self.open_phone(
                    playwright, self.opponent_cookie
                )
                try:
                    await page.get_by_role("button", name="Winkel", exact=False).click()
                    await page.get_by_role("button", name="Hint kopen (1)").click()
                    film = await self.wait_for_film(page, "hint_purchased", "2.7s")
                    event_id = await film.get_attribute("data-event-id")
                    self.assertIsNotNone(event_id)
                    await other.get_by_role(
                        "button", name="Winkel", exact=False
                    ).click()
                    await other.get_by_role(
                        "button", name="Andere team bevriezen (3)"
                    ).click()
                    await page.locator(
                        "#gameplay-event.gameplay-event--victim"
                    ).wait_for(state="visible", timeout=5000)
                    await film.wait_for(state="hidden", timeout=1000)
                    self.assertFalse(
                        await page.evaluate(
                            "document.body.classList.contains('routine-feedback-active')"
                        )
                    )
                    await asyncio.to_thread(
                        admin_unfreeze,
                        self.admin,
                        AdminTeam(str(uuid4()), self.run_id, "a"),
                    )
                    await page.locator("#answer-input").wait_for(timeout=5000)
                    await page.wait_for_function(
                        "!document.body.classList.contains('gameplay-film-active')",
                        timeout=6000,
                    )
                    self.assertFalse(await film.is_visible())
                    self.assertIsNone(
                        await page.locator("#routine-feedback").get_attribute(
                            "data-event-id"
                        )
                    )
                    self.assertFalse(
                        await page.locator(".app-shell").evaluate("el => el.inert")
                    )

                    # The expired attack node keeps its event id for receipt
                    # deduplication; it must not suppress a later routine film.
                    self.assertIsNotNone(
                        await page.locator("#gameplay-event").get_attribute(
                            "data-event-id"
                        )
                    )
                    await page.get_by_role("button", name="Winkel", exact=False).click()
                    await page.get_by_role("button", name="Hint kopen (1)").click()
                    await self.wait_for_film(page, "hint_purchased", "2.7s")
                finally:
                    await self.close_phone(
                        other_context, other, "attack-interruption-sender"
                    )
                    await other_browser.close()
                    await self.close_phone(context, page, "attack-interruption-victim")
                    await browser.close()

        asyncio.run(check())

    def test_hint_purchase_records_complete_motion_and_contained_letter(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser, context, page = await self.open_phone(playwright)
                try:
                    await page.get_by_role("button", name="Winkel", exact=False).click()
                    # Give the eventual GIF a short calm lead-in before purchase.
                    await page.wait_for_timeout(300)
                    await page.get_by_role("button", name="Hint kopen (1)").click()
                    film = await self.wait_for_film(
                        page, "hint_purchased", "2.7s"
                    )
                    rest_geometry = await film.locator(
                        ".routine-feedback__envelope"
                    ).evaluate(
                        """envelope => {
                            const letter = envelope.querySelector(
                                '.routine-feedback__letter'
                            );
                            const flap = envelope.querySelector(
                                '.routine-feedback__flap'
                            );
                            return {
                                top: letter.offsetTop,
                                bottom: letter.offsetTop + letter.offsetHeight,
                                envelopeHeight: envelope.clientHeight,
                                letterZ: getComputedStyle(letter).zIndex,
                                flapZ: getComputedStyle(flap).zIndex,
                                frontZ: getComputedStyle(envelope, '::after').zIndex,
                            };
                        }"""
                    )
                    self.assertGreaterEqual(rest_geometry["top"], 0)
                    self.assertLessEqual(
                        rest_geometry["bottom"], rest_geometry["envelopeHeight"]
                    )
                    self.assertLess(
                        int(rest_geometry["letterZ"]), int(rest_geometry["frontZ"])
                    )
                    self.assertGreater(
                        int(rest_geometry["flapZ"]), int(rest_geometry["letterZ"])
                    )

                    # At the hold, the paper has risen only after the flap opened
                    # and remains inside the animation object's upper boundary.
                    await page.wait_for_timeout(round(2700 * 0.66))
                    open_geometry = await film.evaluate(
                        """film => {
                            const rect = selector => film.querySelector(selector)
                                .getBoundingClientRect();
                            const object = rect('.routine-feedback__object');
                            const envelope = rect('.routine-feedback__envelope');
                            const letter = rect('.routine-feedback__letter');
                            const flap = film.querySelector(
                                '.routine-feedback__flap'
                            );
                            return {
                                objectTop: object.top,
                                envelopeTop: envelope.top,
                                envelopeBottom: envelope.bottom,
                                letterTop: letter.top,
                                letterBottom: letter.bottom,
                                flapZ: getComputedStyle(flap).zIndex,
                                letterZ: getComputedStyle(
                                    film.querySelector('.routine-feedback__letter')
                                ).zIndex,
                            };
                        }"""
                    )
                    self.assertGreaterEqual(
                        open_geometry["letterTop"], open_geometry["objectTop"]
                    )
                    self.assertLess(
                        open_geometry["letterTop"], open_geometry["envelopeTop"]
                    )
                    self.assertLess(
                        open_geometry["letterBottom"],
                        open_geometry["envelopeBottom"],
                    )
                    self.assertLess(
                        int(open_geometry["flapZ"]),
                        int(open_geometry["letterZ"]),
                    )
                    await film.wait_for(state="hidden", timeout=4000)
                    # Preserve a short settled tail for straightforward GIF trim.
                    await page.wait_for_timeout(300)
                finally:
                    await self.close_phone(
                        context, page, "hint-purchase-gif-source"
                    )
                    await browser.close()

        asyncio.run(check())

    def test_resolved_challenge_allows_all_four_later_routines(self):
        self.resolve_challenge_for_opponent()

        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser, context, page = await self.open_phone(playwright)
                try:
                    surface = page.locator("[data-routine-run-id]")
                    self.assertEqual(
                        await surface.get_attribute("data-routine-challenge-phase"),
                        "resolved",
                    )

                    await page.get_by_role("button", name="Winkel", exact=False).click()
                    await page.get_by_role("button", name="Hint kopen (1)").click()
                    film = await self.wait_for_film(
                        page, "hint_purchased", "2.7s"
                    )
                    await page.evaluate("window.cancelRoutineFeedback('test')")
                    await film.wait_for(state="hidden")

                    await page.get_by_role("button", name="Winkel", exact=False).click()
                    await page.get_by_role(
                        "button", name="Uno Reverse kopen (2)"
                    ).click()
                    film = await self.wait_for_film(
                        page, "reverse_purchased", "3.4s"
                    )
                    await page.evaluate("window.cancelRoutineFeedback('test')")
                    await film.wait_for(state="hidden")

                    await page.locator("[data-skip-action]").click()
                    film = await self.wait_for_film(
                        page, "puzzle_skipped", "2.8s"
                    )
                    await page.evaluate("window.cancelRoutineFeedback('test')")
                    await film.wait_for(state="hidden")

                    await page.locator("#answer-input").fill("3")
                    await page.get_by_role(
                        "button", name="Antwoord insturen"
                    ).click()
                    film = await self.wait_for_film(
                        page, "puzzle_solved", "3.5s"
                    )
                    self.assertEqual(
                        await film.locator("h2").inner_text(), "Goed gevonden!"
                    )
                finally:
                    await self.close_phone(
                        context, page, "resolved-challenge-routines"
                    )
                    await browser.close()

        asyncio.run(check())

    def test_first_finisher_response_preempts_routine_then_allows_later_action(self):
        PuzzleProgress.objects.filter(
            run_id=self.run_id,
            team_id="b",
            number__lt=25,
        ).update(
            completed=True,
            reward_awarded=True,
            completion_route="admin_force",
        )
        TeamRun.objects.filter(run_id=self.run_id, team_id="b").update(
            current_number=25
        )

        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser, context, page = await self.open_phone(playwright)
                request_held = asyncio.Event()
                request_release = asyncio.Event()

                async def hold_hint(route):
                    request_held.set()
                    await request_release.wait()
                    await route.continue_()

                await page.route(
                    f"**{reverse('team_action', args=['purchase-hint'])}",
                    hold_hint,
                )
                try:
                    await page.get_by_role("button", name="Winkel", exact=False).click()
                    await page.get_by_role(
                        "button", name="Uno Reverse kopen (2)"
                    ).click()
                    active_film = await self.wait_for_film(
                        page, "reverse_purchased", "3.4s"
                    )
                    # Submit a second routine action while the first film is
                    # active so the winner transition must cancel one response
                    # and invalidate the other.
                    await page.locator(".shop-item--hint").evaluate(
                        "form => form.requestSubmit()"
                    )
                    await asyncio.wait_for(request_held.wait(), 5)
                    opponent_state = await asyncio.to_thread(
                        get_team_state, self.opponent
                    )
                    await asyncio.to_thread(
                        force_complete_current,
                        self.admin,
                        AdminPuzzle(
                            str(uuid4()),
                            self.run_id,
                            "b",
                            opponent_state.question.id,
                        ),
                    )
                    request_release.set()

                    celebration = page.locator(
                        '#endgame-celebration[data-endgame-result="runner-up"]'
                    )
                    await celebration.wait_for(state="visible", timeout=5000)
                    await page.wait_for_timeout(200)
                    await active_film.wait_for(state="hidden", timeout=1000)
                    self.assertFalse(
                        await page.locator("#routine-feedback").is_visible()
                    )
                    self.assertFalse(
                        await page.evaluate(
                            "document.body.classList.contains("
                            "'routine-feedback-active')"
                        )
                    )
                    self.assertEqual(
                        await page.locator(
                            "[data-routine-run-id]"
                        ).get_attribute("data-routine-first-finisher"),
                        "b",
                    )

                    await celebration.wait_for(state="hidden", timeout=7000)
                    await page.get_by_role("button", name="Winkel", exact=False).click()
                    await page.get_by_role("button", name="Hint kopen (1)").click()
                    await self.wait_for_film(page, "hint_purchased", "2.7s")
                finally:
                    request_release.set()
                    await self.close_phone(
                        context, page, "first-finisher-preemption"
                    )
                    await browser.close()

        asyncio.run(check())
