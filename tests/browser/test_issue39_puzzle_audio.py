"""Browser coverage for issue #39 manual, polling-stable puzzle audio."""

import asyncio
import json
import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, LiveServerTestCase, override_settings

from quiz.application import start_game
from quiz.contracts import Actor, StartGame
from quiz.models import AccountRole


class TypedPuzzleAudioBrowserTests(LiveServerTestCase):
    def setUp(self):
        if not os.environ.get("TEST_DATABASE_PATH"):
            self.skipTest("requires disposable file-backed TEST_DATABASE_PATH")

        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        games = root / "games"
        package = games / "christmas-2026-demo"
        shutil.copytree(settings.BASE_DIR / "games" / "christmas-2026-demo", package)
        (package / "a" / "clue.mp3").write_bytes(b"ID3-browser-private-audio")
        config_file = package / "game.json"
        config = json.loads(config_file.read_text())
        config["teams"]["a"]["puzzles"][0]["media"] = [
            {"type": "image", "path": "a/star.png", "alt": "Rode ster voor team A"},
            {"type": "audio", "path": "a/clue.mp3"},
        ]
        config_file.write_text(json.dumps(config))

        scope = override_settings(
            QUIZ_GAMES_ROOT=games,
            QUIZ_SNAPSHOT_ROOT=root / "snapshots",
        )
        scope.enable()
        self.addCleanup(scope.disable)

        users = get_user_model()
        admin_user = users.objects.create_user("issue39-browser-admin")
        self.team_user = users.objects.create_user("issue39-browser-team")
        AccountRole.objects.create(user=admin_user, role="admin")
        AccountRole.objects.create(user=self.team_user, role="team", team_id="a")
        start_game(
            Actor(admin_user.pk, "admin"),
            StartGame(str(uuid4()), "christmas-2026-demo"),
        )

        client = Client()
        client.force_login(self.team_user)
        self.session_cookie = client.cookies["sessionid"].value

    def test_mixed_media_is_manual_and_audio_node_survives_normal_polls(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
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
                await context.add_init_script(
                    """
                    window.__issue39PlayCalls = 0;
                    HTMLMediaElement.prototype.play = function () {
                      window.__issue39PlayCalls += 1;
                      return Promise.resolve();
                    };
                    """
                )
                page = await context.new_page()
                try:
                    await page.goto(f"{self.live_server_url}/team/")
                    audio = page.locator("#question-pane audio.puzzle-audio")
                    await audio.wait_for()
                    image = page.locator(
                        '#question-pane img[alt="Rode ster voor team A"]'
                    )
                    await image.wait_for()

                    self.assertTrue(await audio.evaluate("el => el.controls"))
                    self.assertEqual(await audio.get_attribute("preload"), "metadata")
                    self.assertIsNone(await audio.get_attribute("autoplay"))
                    self.assertEqual(await page.evaluate("window.__issue39PlayCalls"), 0)

                    await audio.evaluate(
                        """el => {
                          window.__issue39AudioNode = el;
                          el.__issue39Marker = 'preserved';
                        }"""
                    )
                    await page.evaluate(
                        """() => {
                          window.__issue39PollSwaps = 0;
                          const target = document.getElementById('game-status');
                          const observer = new MutationObserver(records => {
                            if (records.some(record => record.type === 'childList')) {
                              window.__issue39PollSwaps += 1;
                            }
                          });
                          observer.observe(target, {childList: true});
                        }"""
                    )
                    await page.wait_for_function(
                        "() => window.__issue39PollSwaps >= 2",
                        timeout=5000,
                    )

                    self.assertTrue(
                        await page.evaluate(
                            """() => window.__issue39AudioNode ===
                              document.querySelector('#question-pane audio.puzzle-audio')"""
                        )
                    )
                    self.assertEqual(
                        await audio.evaluate("el => el.__issue39Marker"),
                        "preserved",
                    )
                    self.assertEqual(await page.evaluate("window.__issue39PlayCalls"), 0)
                finally:
                    await context.close()
                    await browser.close()

        asyncio.run(check())
