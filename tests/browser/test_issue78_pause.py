"""Issue #78: real server-backed Pause appearance and safety smoke."""

import asyncio
import os
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from quiz.application import admin_freeze, pause_game, resume_game
from quiz.contracts import AdminTeam, RunCommand
from tests.browser.issue31_support import Issue31BrowserCase


class Issue78PauseVisualTests(Issue31BrowserCase):
    def test_real_tv_and_phone_pause_visual_checkpoint(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                host = urlparse(self.live_server_url).hostname
                phone_context = await browser.new_context(
                    viewport={"width": 390, "height": 844},
                    device_scale_factor=1,
                )
                await phone_context.add_cookies(
                    [
                        {
                            "name": "sessionid",
                            "value": self.a_cookie,
                            "domain": host,
                            "path": "/",
                        }
                    ]
                )
                tv_context = await browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    device_scale_factor=1,
                )
                phone = await phone_context.new_page()
                tv = await tv_context.new_page()
                output_dir = os.environ.get("UI78_SCREENSHOT_DIR")
                if output_dir:
                    Path(output_dir).mkdir(parents=True, exist_ok=True)
                try:
                    await phone.goto(f"{self.live_server_url}/team/")
                    await tv.goto(f"{self.live_server_url}/overview/")
                    await asyncio.to_thread(
                        pause_game,
                        self.admin,
                        RunCommand(str(uuid4()), self.run_id),
                    )
                    await phone.locator(".pause-veil--team").wait_for(
                        timeout=6000
                    )
                    await tv.locator(".pause-veil--tv").wait_for(timeout=6000)
                    self.assertIn(
                        "Spel gepauzeerd",
                        await tv.locator(".pause-veil--tv").inner_text(),
                    )
                    self.assertEqual(
                        await phone.locator(
                            "#answer-input, #team-shop-dialog, "
                            "#question-pane form"
                        ).count(),
                        0,
                    )
                    self.assertEqual(
                        await phone.locator("#question-pane").get_attribute(
                            "inert"
                        ),
                        "",
                    )
                    self.assertEqual(
                        await phone.locator(
                            ".pause-veil--team h2"
                        ).inner_text(),
                        "Spel gepauzeerd",
                    )
                    stopped_time = await tv.locator(
                        ".pause-veil__time"
                    ).inner_text()
                    await tv.wait_for_timeout(1200)
                    self.assertEqual(
                        stopped_time,
                        await tv.locator(".pause-veil__time").inner_text(),
                    )
                    if output_dir:
                        await tv.screenshot(
                            path=str(
                                Path(output_dir)
                                / "issue78-tv-advent-pause-1920x1080.png"
                            ),
                            animations="disabled",
                        )
                        await phone.screenshot(
                            path=str(
                                Path(output_dir)
                                / "issue78-phone-advent-pause-390x844.png"
                            ),
                            animations="disabled",
                        )
                    await asyncio.to_thread(
                        resume_game,
                        self.admin,
                        RunCommand(str(uuid4()), self.run_id),
                    )
                    await phone.locator(".pause-veil--team").wait_for(
                        state="detached", timeout=6000
                    )
                    self.assertEqual(
                        await phone.locator("#answer-input").count(), 1
                    )
                    await asyncio.to_thread(
                        admin_freeze,
                        self.admin,
                        AdminTeam(str(uuid4()), self.run_id, "a"),
                    )
                    await phone.locator(".freeze-message").wait_for(
                        timeout=6000
                    )
                    await asyncio.to_thread(
                        pause_game,
                        self.admin,
                        RunCommand(str(uuid4()), self.run_id),
                    )
                    await phone.locator(".pause-veil--frozen").wait_for(
                        timeout=6000
                    )
                    self.assertEqual(
                        await phone.locator(
                            "#question-pane img, #question-pane audio, "
                            "#question-pane form, #team-actions form"
                        ).count(),
                        0,
                    )
                finally:
                    await phone_context.close()
                    await tv_context.close()
                    await browser.close()

        asyncio.run(check())
