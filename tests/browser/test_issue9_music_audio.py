"""Browser acceptance for issue #9 persistent central Music Quiz playback."""

import asyncio
import json
import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import LiveServerTestCase, override_settings
from django.utils import timezone

from quiz.application import (
    force_complete_current,
    pause_game,
    resume_game,
    start_game,
    submit_music_answer,
)
from quiz.contracts import Actor, AdminPuzzle, RunCommand, StartGame, SubmitMusicAnswer
from quiz.models import AccountRole, MusicQuiz

MEDIA_STUB = r"""
window.__mediaCalls = [];
window.__rejectMediaPlay = false;

Object.defineProperty(HTMLMediaElement.prototype, "currentTime", {
  configurable: true,
  get() { return this.__issue9CurrentTime || 0; },
  set(value) { this.__issue9CurrentTime = Number(value) || 0; },
});

HTMLMediaElement.prototype.load = function () {
  window.__mediaCalls.push({kind: "load", src: this.getAttribute("src") || ""});
};

HTMLMediaElement.prototype.pause = function () {
  window.__mediaCalls.push({
    kind: "pause",
    src: this.getAttribute("src") || "",
    time: this.currentTime,
  });
};

HTMLMediaElement.prototype.play = function () {
  window.__mediaCalls.push({
    kind: "play",
    src: this.getAttribute("src") || "",
    time: this.currentTime,
  });
  if (window.__rejectMediaPlay) {
    return Promise.reject(new DOMException("autoplay blocked", "NotAllowedError"));
  }
  return Promise.resolve();
};
"""


class IssueNineMusicAudioBrowserTests(LiveServerTestCase):
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

    def setUp(self):
        if not os.environ.get("TEST_DATABASE_PATH"):
            self.skipTest("requires disposable file-backed TEST_DATABASE_PATH")

        self.games = TemporaryDirectory()
        self.snapshots = TemporaryDirectory()
        self.addCleanup(self.games.cleanup)
        self.addCleanup(self.snapshots.cleanup)

        source = Path(settings.BASE_DIR) / "games" / "christmas-2026-demo"
        package = Path(self.games.name) / "christmas-2026-demo"
        shutil.copytree(source, package)
        config_path = package / "game.json"
        config = json.loads(config_path.read_text())
        audio_root = package / "music"
        audio_root.mkdir()
        audio_bytes = (
            Path(settings.BASE_DIR) / "quiz" / "static" / "quiz" / "sound-check.wav"
        ).read_bytes()
        for number, question in enumerate(config["music_questions"], 1):
            question["audio"] = f"music/question-{number}.wav"
            (audio_root / f"question-{number}.wav").write_bytes(audio_bytes)
        config_path.write_text(json.dumps(config, indent=2))

        scope = override_settings(
            QUIZ_GAMES_ROOT=Path(self.games.name),
            QUIZ_SNAPSHOT_ROOT=Path(self.snapshots.name),
        )
        scope.enable()
        self.addCleanup(scope.disable)

        users = get_user_model()
        admin_user = users.objects.create_user("issue9-browser-admin")
        team_user = users.objects.create_user("issue9-browser-a")
        AccountRole.objects.create(user=admin_user, role="admin")
        AccountRole.objects.create(user=team_user, role="team", team_id="a")

        self.admin = Actor(admin_user.pk, "admin")
        self.team = Actor(team_user.pk, "team", "a")
        self.run_id = start_game(
            self.admin, StartGame(str(uuid4()), "christmas-2026-demo")
        ).run_id

    def _start_music(self):
        for number in range(1, 14):
            force_complete_current(
                self.admin,
                AdminPuzzle(str(uuid4()), self.run_id, "a", f"a-{number}"),
            )

    def _answer_music(self, number):
        submit_music_answer(
            self.team,
            SubmitMusicAnswer(
                str(uuid4()),
                self.run_id,
                f"music-{number}",
                self.answers[number - 1],
            ),
        )

    def _finish_gathering(self):
        MusicQuiz.objects.filter(run_id=self.run_id).update(
            music_elapsed_ms=60_000,
            music_clock_anchor=timezone.now(),
        )

    async def _overview_page(self, browser):
        context = await browser.new_context()
        await context.add_init_script(MEDIA_STUB)
        page = await context.new_page()
        await page.goto(f"{self.live_server_url}/overview/")
        return context, page

    def test_persistent_player_survives_polls_question_changes_and_pause(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                context, page = await self._overview_page(browser)
                try:
                    self.assertEqual(await page.locator("#music-player").count(), 1)
                    await page.evaluate(
                        "window.__issue9Player = "
                        "document.querySelector('#music-player')"
                    )

                    await page.get_by_role(
                        "button", name="Geluid inschakelen"
                    ).click()
                    await page.get_by_role("heading", name="Geluid klaar").wait_for()
                    await page.wait_for_timeout(750)

                    await asyncio.to_thread(self._start_music)
                    await page.get_by_text("Maak je klaar!", exact=True).wait_for(
                        timeout=5000
                    )
                    self.assertIsNone(
                        await page.locator("#music-player").get_attribute("src")
                    )
                    self.assertEqual(
                        await page.get_by_role("heading", name="Speelt af").count(), 0
                    )

                    await asyncio.to_thread(self._finish_gathering)
                    await page.get_by_text("Vraag 1 van 11", exact=False).wait_for(
                        timeout=5000
                    )
                    await page.get_by_role("heading", name="Speelt af").wait_for(
                        timeout=5000
                    )
                    self.assertTrue(
                        await page.evaluate(
                            "window.__issue9Player === "
                            "document.querySelector('#music-player')"
                        )
                    )
                    player = page.locator("#music-player")
                    self.assertIn("q=1", await player.get_attribute("src"))

                    await player.dispatch_event("loadedmetadata")
                    await player.evaluate("(el) => { el.currentTime = 12.5; }")
                    play_count = await page.evaluate(
                        "window.__mediaCalls"
                        ".filter(call => call.kind === 'play').length"
                    )
                    await page.wait_for_timeout(1200)
                    self.assertEqual(
                        await page.evaluate(
                            "window.__mediaCalls"
                            ".filter(call => call.kind === 'play').length"
                        ),
                        play_count,
                    )
                    self.assertEqual(
                        await player.evaluate("(el) => el.currentTime"), 12.5
                    )
                    self.assertTrue(
                        await page.evaluate(
                            "window.__issue9Player === "
                            "document.querySelector('#music-player')"
                        )
                    )

                    await asyncio.to_thread(
                        pause_game,
                        self.admin,
                        RunCommand(str(uuid4()), self.run_id),
                    )
                    await page.get_by_role("heading", name="Gepauzeerd").wait_for(
                        timeout=5000
                    )
                    paused_src = await player.get_attribute("src")
                    self.assertEqual(
                        await player.evaluate("(el) => el.currentTime"), 12.5
                    )

                    await asyncio.to_thread(
                        resume_game,
                        self.admin,
                        RunCommand(str(uuid4()), self.run_id),
                    )
                    await page.get_by_role("heading", name="Speelt af").wait_for(
                        timeout=5000
                    )
                    self.assertEqual(await player.get_attribute("src"), paused_src)
                    self.assertEqual(
                        await player.evaluate("(el) => el.currentTime"), 12.5
                    )

                    await asyncio.to_thread(self._answer_music, 1)
                    await page.get_by_text("Vraag 2 van 11", exact=False).wait_for(
                        timeout=5000
                    )
                    await page.get_by_role("heading", name="Speelt af").wait_for(
                        timeout=5000
                    )
                    self.assertTrue(
                        await page.evaluate(
                            "window.__issue9Player === "
                            "document.querySelector('#music-player')"
                        )
                    )
                    self.assertIn("q=2", await player.get_attribute("src"))
                    self.assertEqual(await player.evaluate("(el) => el.currentTime"), 0)

                    for number in range(2, 12):
                        await asyncio.to_thread(self._answer_music, number)
                    await page.get_by_text(
                        "Winnaar Muziek Quiz", exact=True
                    ).wait_for(timeout=5000)
                    self.assertEqual(
                        await page.locator(".music-stage--final_results").count(), 1
                    )
                    await page.get_by_role("heading", name="Geluid klaar").wait_for(
                        timeout=5000
                    )
                    self.assertIsNone(await player.get_attribute("src"))
                    self.assertEqual(await player.evaluate("(el) => el.currentTime"), 0)
                    self.assertEqual(await page.locator("#music-player").count(), 1)
                finally:
                    await context.close()
                    await browser.close()

        asyncio.run(check())

    def test_blocked_and_failed_playback_stays_actionable(self):
        self._start_music()
        self._finish_gathering()

        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                context, page = await self._overview_page(browser)
                try:
                    await page.get_by_text("Vraag 1 van 11", exact=False).wait_for()
                    self.assertEqual(await page.locator("#music-player").count(), 1)
                    await page.evaluate("window.__rejectMediaPlay = true")
                    await page.get_by_role(
                        "button", name="Geluid inschakelen"
                    ).click()
                    await page.get_by_role(
                        "heading", name="Geluid geblokkeerd"
                    ).wait_for()
                    retry = page.get_by_role("button", name="Opnieuw proberen")
                    self.assertTrue(await retry.is_visible())

                    await page.evaluate("window.__rejectMediaPlay = false")
                    await retry.click()
                    await page.get_by_role("heading", name="Speelt af").wait_for()

                    await page.locator("#music-player").dispatch_event("error")
                    await page.get_by_role("heading", name="Afspeelfout").wait_for()
                    self.assertTrue(await retry.is_visible())

                    load_count = await page.evaluate(
                        "window.__mediaCalls"
                        ".filter(call => call.kind === 'load').length"
                    )
                    await retry.click()
                    await page.get_by_role("heading", name="Speelt af").wait_for()
                    self.assertGreater(
                        await page.evaluate(
                            "window.__mediaCalls"
                            ".filter(call => call.kind === 'load').length"
                        ),
                        load_count,
                    )

                    await asyncio.to_thread(
                        pause_game,
                        self.admin,
                        RunCommand(str(uuid4()), self.run_id),
                    )
                    await page.get_by_role("heading", name="Gepauzeerd").wait_for()
                    await page.get_by_role("button", name="Geluid testen").click()
                    await page.wait_for_timeout(750)

                    await page.locator("#music-player").dispatch_event("error")
                    await page.get_by_role("heading", name="Afspeelfout").wait_for()
                    load_count = await page.evaluate(
                        "window.__mediaCalls"
                        ".filter(call => call.kind === 'load').length"
                    )

                    await asyncio.to_thread(
                        resume_game,
                        self.admin,
                        RunCommand(str(uuid4()), self.run_id),
                    )
                    await page.get_by_role("heading", name="Speelt af").wait_for(
                        timeout=5000
                    )
                    self.assertGreater(
                        await page.evaluate(
                            "window.__mediaCalls"
                            ".filter(call => call.kind === 'load').length"
                        ),
                        load_count,
                    )
                finally:
                    await context.close()
                    await browser.close()

        asyncio.run(check())
