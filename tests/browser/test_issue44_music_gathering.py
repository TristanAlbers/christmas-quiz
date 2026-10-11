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
    pause_game,
    resume_game,
    start_game,
)
from quiz.contracts import Actor, AdminPuzzle, RunCommand, StartGame
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
                finally:
                    await tv_context.close()
                    await b_context.close()
                    await a_context.close()
                    await browser.close()

        asyncio.run(check())
