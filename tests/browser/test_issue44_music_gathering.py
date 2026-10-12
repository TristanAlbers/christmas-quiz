"""Browser acceptance for issue #44 Music gathering and TV progress."""

import asyncio
import os
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import Client, LiveServerTestCase, override_settings
from django.utils import timezone

from quiz.application import (
    force_complete_current,
    submit_music_answer,
    pause_game,
    resume_game,
    start_game,
)
from quiz.contracts import Actor, AdminPuzzle, RunCommand, StartGame, SubmitMusicAnswer
from quiz.models import AccountRole, MusicQuiz


class IssueFortyFourMusicGatheringBrowserTests(LiveServerTestCase):
    def setUp(self):
        if not os.environ.get("TEST_DATABASE_PATH"):
            self.skipTest("requires disposable file-backed TEST_DATABASE_PATH")
        self.snapshots = TemporaryDirectory()
        self.addCleanup(self.snapshots.cleanup)
        scope = override_settings(QUIZ_SNAPSHOT_ROOT=Path(self.snapshots.name))
        scope.enable()
        self.addCleanup(scope.disable)

        users = get_user_model()
        admin_user = users.objects.create_user("issue44-browser-admin")
        self.a_user = users.objects.create_user("issue44-browser-a")
        self.b_user = users.objects.create_user("issue44-browser-b")
        AccountRole.objects.create(user=admin_user, role="admin")
        AccountRole.objects.create(user=self.a_user, role="team", team_id="a")
        AccountRole.objects.create(user=self.b_user, role="team", team_id="b")
        self.admin = Actor(admin_user.pk, "admin")
        self.run_id = start_game(
            self.admin, StartGame(str(uuid4()), "christmas-2026-demo")
        ).run_id
        for number in range(1, 14):
            force_complete_current(
                self.admin,
                AdminPuzzle(str(uuid4()), self.run_id, "a", f"a-{number}"),
            )

        self.cookies = {}
        for team_id, user in (("a", self.a_user), ("b", self.b_user)):
            client = Client()
            client.force_login(user)
            self.cookies[team_id] = client.cookies["sessionid"].value

    def _set_music_time(self, elapsed_ms):
        MusicQuiz.objects.filter(run_id=self.run_id).update(
            music_elapsed_ms=elapsed_ms,
            music_clock_anchor=timezone.now(),
        )

    async def _team_page(self, browser, team_id):
        context = await browser.new_context(viewport={"width": 390, "height": 844})
        host = urlparse(self.live_server_url).hostname
        await context.add_cookies(
            [
                {
                    "name": "sessionid",
                    "value": self.cookies[team_id],
                    "domain": host,
                    "path": "/",
                }
            ]
        )
        page = await context.new_page()
        await page.goto(f"{self.live_server_url}/team/")
        return context, page

    def test_gathering_and_cosmetic_player_progress_journey(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                a_context, team_a = await self._team_page(browser, "a")
                b_context, team_b = await self._team_page(browser, "b")
                tv_context = await browser.new_context(
                    viewport={"width": 1920, "height": 1080}
                )
                tv = await tv_context.new_page()
                await tv.goto(f"{self.live_server_url}/overview/")
                try:
                    await tv.get_by_text("Maak je klaar!", exact=True).wait_for()
                    countdown = tv.locator("[data-music-countdown-value]")
                    self.assertRegex(
                        await countdown.inner_text(), re.compile(r"^(01:00|00:5[89])$")
                    )
                    self.assertEqual(await tv.locator(".music-step").count(), 11)
                    self.assertEqual(
                        await tv.locator(".music-step--current").count(), 0
                    )
                    self.assertEqual(
                        await tv.locator(".music-player-progress").count(), 0
                    )
                    self.assertEqual(
                        await tv.locator("#overview-audio-state").get_attribute(
                            "data-question-number"
                        ),
                        "",
                    )
                    for team in (team_a, team_b):
                        await team.get_by_text(
                            "Maak je klaar voor de Muziek Quiz", exact=True
                        ).wait_for()
                        status = team.locator(".music-gathering-status")
                        self.assertEqual(await status.count(), 1)
                        # Catch the exact old pastel/cream contrast regression.
                        bg = await status.evaluate(
                            "el => getComputedStyle(el).backgroundImage"
                        )
                        self.assertIn("rgb(25, 58, 48)", bg)
                        label = await status.locator("strong").evaluate(
                            "el => getComputedStyle(el).color"
                        )
                        self.assertEqual(label, "rgb(246, 223, 173)")
                    if capture_dir := os.environ.get("UI77_SCREENSHOT_DIR"):
                        Path(capture_dir).mkdir(parents=True, exist_ok=True)
                        await team_a.screenshot(
                            path=str(Path(capture_dir) / "phone-gathering-390x844.png")
                        )
                        await tv.screenshot(
                            path=str(Path(capture_dir) / "tv-gathering-1920x1080.png")
                        )
                        self.assertEqual(
                            await team.locator("#music-answer-input").count(), 0
                        )
                        self.assertEqual(await team.locator("#answer-input").count(), 0)
                        self.assertEqual(
                            await team.locator(".music-player-progress").count(), 0
                        )

                    await asyncio.to_thread(
                        pause_game,
                        self.admin,
                        RunCommand(str(uuid4()), self.run_id),
                    )
                    await tv.get_by_text(
                        "Gepauzeerd · de tijd staat stil", exact=True
                    ).wait_for(timeout=5000)
                    paused_gathering = await countdown.inner_text()
                    await tv.wait_for_timeout(1_100)
                    self.assertEqual(await countdown.inner_text(), paused_gathering)
                    self.assertEqual(
                        await team_a.locator("#music-answer-input").count(), 0
                    )
                    await asyncio.to_thread(
                        resume_game,
                        self.admin,
                        RunCommand(str(uuid4()), self.run_id),
                    )

                    await asyncio.to_thread(self._set_music_time, 60_000)
                    await tv.get_by_text("Vraag 1 van 11", exact=False).wait_for(
                        timeout=5000
                    )
                    for team in (team_a, team_b):
                        await team.locator("#music-answer-input").wait_for(timeout=5000)
                        self.assertEqual(
                            await team.locator(".music-step--current").inner_text(), "1"
                        )
                        # Phone progress is communicated only by the tracker;
                        # the TV owns the separate question-number label.
                        self.assertEqual(
                            await team.locator(
                                ".music-quiz--phone__kicker"
                            ).inner_text(),
                            "Muziek Quiz",
                        )
                    # The V4 player bar is illustration only: the 180s graphic
                    # stays fixed, even as the authoritative question clock changes.
                    bar = tv.locator(".music-player-progress")
                    self.assertEqual(await bar.count(), 1)
                    self.assertEqual(
                        await bar.get_attribute("role"), "img"
                    )
                    self.assertEqual(
                        await bar.locator("progress").count(), 0
                    )
                    self.assertEqual(
                        await bar.locator(".music-player-progress__fill").count(), 1
                    )
                    self.assertEqual(
                        await tv.locator(".music-step").count(), 11
                    )
                    if capture_dir := os.environ.get("UI77_SCREENSHOT_DIR"):
                        Path(capture_dir).mkdir(parents=True, exist_ok=True)
                        output = Path(capture_dir)
                        await tv.screenshot(path=str(output / "tv-1920x1080.png"))
                        await team_a.screenshot(path=str(output / "phone-390x844.png"))

                    await asyncio.to_thread(self._set_music_time, 150_000)
                    await tv.wait_for_timeout(800)
                    self.assertAlmostEqual(
                        await bar.locator(".music-player-progress__fill").evaluate(
                            "n => n.offsetWidth / n.parentElement.clientWidth"
                        ),
                        0.4,
                        places=2,
                    )
                    self.assertEqual(
                        await team_a.locator(".music-player-progress").count(), 0
                    )

                    await asyncio.to_thread(
                        pause_game, self.admin, RunCommand(str(uuid4()), self.run_id)
                    )
                    await tv.wait_for_function(
                        "document.querySelector('#overview-audio-state')"
                        ".dataset.globalState === 'PAUSED'"
                    )
                    # Team and TV have independent 500 ms pollers.
                    await team_a.locator("#music-answer-input").wait_for(
                        state="detached", timeout=5000
                    )
                    self.assertEqual(
                        await team_a.locator("#music-answer-input").count(), 0
                    )
                    await asyncio.to_thread(
                        resume_game, self.admin, RunCommand(str(uuid4()), self.run_id)
                    )
                    await asyncio.to_thread(self._set_music_time, 300_000)
                    await tv.wait_for_timeout(800)
                    self.assertEqual(await bar.locator("progress").count(), 0)
                    self.assertAlmostEqual(
                        await bar.locator(".music-player-progress__fill").evaluate(
                            "n => n.offsetWidth / n.parentElement.clientWidth"
                        ),
                        0.4,
                        places=2,
                    )
                    self.assertEqual(
                        await team_a.locator("#music-answer-input").count(), 1
                    )
                    await tv.reload()
                    bar = tv.locator(".music-player-progress")
                    self.assertEqual(await bar.locator("progress").count(), 0)
                    self.assertAlmostEqual(
                        await bar.locator(".music-player-progress__fill").evaluate(
                            "n => n.offsetWidth / n.parentElement.clientWidth"
                        ),
                        0.4,
                        places=2,
                    )

                    await team_a.locator("#music-answer-input").fill("jingle bells")
                    await team_a.get_by_role("button", name="Antwoord insturen").click()
                    await tv.get_by_text("Vraag 2 van 11", exact=False).wait_for(
                        timeout=5000
                    )
                    self.assertEqual(
                        await tv.locator(".music-step--current").inner_text(), "2"
                    )
                    self.assertEqual(
                        await tv.locator(".music-player-progress progress").count(), 0
                    )
                    self.assertEqual(
                        await team_a.locator("#music-answer-input").count(), 1
                    )
                    # A compact phone and reduced-motion settings must keep
                    # the live answer input usable through multiple polls.
                    await team_a.set_viewport_size({"width": 320, "height": 720})
                    await team_a.emulate_media(reduced_motion="reduce")
                    await tv.emulate_media(reduced_motion="reduce")
                    field = team_a.locator("#music-answer-input")
                    await field.fill("nog bezig")
                    await field.focus()
                    await field.evaluate("el => el.setSelectionRange(3, 6)")
                    await team_a.evaluate(
                        "window.musicInputBeforePoll = "
                        "document.querySelector('#music-answer-input')"
                    )
                    await team_a.wait_for_timeout(1200)
                    self.assertTrue(
                        await team_a.evaluate(
                            "document.querySelector('#music-answer-input') "
                            "=== window.musicInputBeforePoll"
                        )
                    )
                    self.assertEqual(await field.input_value(), "nog bezig")
                    self.assertEqual(
                        await field.evaluate("el => el.selectionStart"), 3
                    )
                    self.assertEqual(
                        await field.evaluate("el => el.selectionEnd"), 6
                    )
                    self.assertLessEqual(
                        await team_a.evaluate(
                            "document.documentElement.scrollWidth"
                        ),
                        321,
                    )
                    self.assertTrue(
                        await tv.evaluate(
                            "matchMedia('(prefers-reduced-motion: reduce)').matches"
                        )
                    )
                    scores = {}
                    for article in await tv.locator(
                        ".public-music-scores article"
                    ).all():
                        name = await article.locator("span").inner_text()
                        points = await article.locator("strong").inner_text()
                        scores[name] = points
                    self.assertEqual(scores, {"Team A": "1", "Team B": "0"})
                finally:
                    await tv_context.close()
                    await b_context.close()
                    await a_context.close()
                    await browser.close()

        asyncio.run(check())

    def _finish_music_with_winner(self, final_winner):
        """Advance real server commands to final results, with one score leader."""
        self._set_music_time(60_000)
        answers = (
            "jingle bells",
            "silent night",
            "white christmas",
            "feliz navidad",
            "last christmas",
            "santa baby",
            "winter wonderland",
            "let it snow",
            "the christmas song",
            "rudolph",
            "deck the halls",
        )
        # The overall champion earns six of eleven song wins.
        for number, answer in enumerate(answers, start=1):
            team_id = final_winner if number % 2 else (
                "b" if final_winner == "a" else "a"
            )
            user = self.a_user if team_id == "a" else self.b_user
            result = submit_music_answer(
                Actor(user.pk, "team", team_id),
                SubmitMusicAnswer(
                    str(uuid4()), self.run_id, f"music-{number}", answer
                ),
            )
            self.assertEqual(result.outcome, "won")
        music = MusicQuiz.objects.get(run_id=self.run_id)
        self.assertEqual(music.phase, "final_results")
        return music.final_results_started_ms

    def _put_finale_near_expiry(self, final_started_ms):
        MusicQuiz.objects.filter(run_id=self.run_id).update(
            music_elapsed_ms=final_started_ms + 58_700,
            music_clock_anchor=timezone.now(),
        )

    def test_finale_tv_phones_countdown_celebration_and_advent_resume(self):
        start_ms = self._finish_music_with_winner("a")

        async def check():
            from playwright.async_api import async_playwright

            errors = []
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                a_ctx, a = await self._team_page(browser, "a")
                b_ctx, b = await self._team_page(browser, "b")
                tv_ctx = await browser.new_context(
                    viewport={"width": 1920, "height": 1080}
                )
                tv = await tv_ctx.new_page()
                for page in (a, b, tv):
                    page.on("pageerror", lambda exc: errors.append(str(exc)))
                try:
                    await tv.goto(f"{self.live_server_url}/overview/")
                    await tv.get_by_text("Team A wint!", exact=True).wait_for()
                    await a.get_by_text(
                        "Jullie winnen de Muziek Quiz!", exact=True
                    ).wait_for()
                    await b.get_by_text(
                        "Team A wint de Muziek Quiz!", exact=True
                    ).wait_for()
                    self.assertEqual(
                        await tv.locator(".music-stage--final_results").count(), 1
                    )
                    self.assertEqual(
                        await tv.locator(".public-music-scores article").count(), 2
                    )
                    for page in (a, b, tv):
                        clock = page.locator(
                            ".music-finale__return [data-music-countdown-value]"
                        )
                        await clock.wait_for()
                        self.assertRegex(
                            await clock.inner_text(),
                            re.compile(r"^00:(5[0-9]|4[0-9])$"),
                        )
                        self.assertEqual(
                            await page.locator("#music-answer-input").count(), 0
                        )
                    self.assertEqual(
                        await tv.locator(".music-finale-confetti i").count(), 46
                    )
                    self.assertEqual(
                        await a.locator(".music-finale-confetti i").count(), 46
                    )
                    self.assertEqual(
                        await b.locator(".music-finale-confetti i").count(), 0
                    )
                    self.assertIn(
                        "tijdelijk stil",
                        await tv.locator(".public-music-header .game-clock").inner_text(),
                    )
                    if capture_dir := os.environ.get("UI77_SCREENSHOT_DIR"):
                        output = Path(capture_dir)
                        output.mkdir(parents=True, exist_ok=True)
                        await tv.screenshot(path=str(output / "tv-finale-1920x1080.png"))
                        await a.screenshot(path=str(output / "phone-finale-winner-390x844.png"))
                        await b.screenshot(path=str(output / "phone-finale-runner-390x844.png"))

                    await asyncio.to_thread(
                        pause_game, self.admin, RunCommand(str(uuid4()), self.run_id)
                    )
                    await tv.wait_for_function(
                        "document.querySelector('#overview-audio-state')"
                        ".dataset.globalState === 'PAUSED'"
                    )
                    paused = await tv.locator(
                        ".music-finale__return [data-music-countdown-value]"
                    ).inner_text()
                    await tv.wait_for_timeout(1300)
                    self.assertEqual(
                        await tv.locator(
                            ".music-finale__return [data-music-countdown-value]"
                        ).inner_text(), paused
                    )
                    await asyncio.to_thread(
                        resume_game, self.admin, RunCommand(str(uuid4()), self.run_id)
                    )
                    await tv.wait_for_function(
                        "document.querySelector('#overview-audio-state')"
                        ".dataset.globalState === 'MUSIC_QUIZ'"
                    )
                    # Countdown is based on the existing authoritative Music
                    # clock; expiry switches every display back to Advent.
                    await asyncio.to_thread(self._put_finale_near_expiry, start_ms)
                    await tv.wait_for_function(
                        "document.querySelector('.music-finale__return"
                        " [data-music-countdown-value]')?.textContent"
                        " === '00:02'", timeout=5000
                    )
                    await tv.get_by_text(
                        "De adventrace is begonnen", exact=False
                    ).wait_for(timeout=6000)
                    for page in (a, b):
                        await page.locator(".music-quiz--phone").wait_for(
                            state="detached", timeout=6000
                        )
                    self.assertEqual(errors, [])
                finally:
                    await tv_ctx.close()
                    await b_ctx.close()
                    await a_ctx.close()
                    await browser.close()

        asyncio.run(check())

    def test_finale_other_team_is_declared_music_champion(self):
        self._finish_music_with_winner("b")

        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                a_ctx, a = await self._team_page(browser, "a")
                b_ctx, b = await self._team_page(browser, "b")
                tv_ctx = await browser.new_context(
                    viewport={"width": 1920, "height": 1080}
                )
                tv = await tv_ctx.new_page()
                try:
                    await tv.goto(f"{self.live_server_url}/overview/")
                    await tv.get_by_text("Team B wint!", exact=True).wait_for()
                    await b.get_by_text(
                        "Jullie winnen de Muziek Quiz!", exact=True
                    ).wait_for()
                    await a.get_by_text(
                        "Team B wint de Muziek Quiz!", exact=True
                    ).wait_for()
                    self.assertEqual(
                        await a.locator(".music-finale-confetti i").count(), 0
                    )
                    self.assertEqual(
                        await b.locator(".music-finale-confetti i").count(), 46
                    )
                    self.assertEqual(
                        await tv.locator(".public-music-scores strong").all_inner_texts(),
                        ["5", "6"],
                    )
                finally:
                    await tv_ctx.close()
                    await b_ctx.close()
                    await a_ctx.close()
                    await browser.close()

        asyncio.run(check())
