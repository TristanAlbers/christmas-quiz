"""Issue #76: authentic frozen phone surface, privacy and recovery smoke checks."""

import asyncio
import os
import re
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from quiz.application import admin_freeze, admin_unfreeze
from quiz.contracts import AdminTeam
from tests.browser.issue31_support import Issue31BrowserCase


class Issue76FrozenPhoneBrowserTests(Issue31BrowserCase):
    def test_frozen_phone_is_inert_private_safe_and_recovers(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                context = await browser.new_context(
                    viewport={"width": 390, "height": 844},
                    device_scale_factor=1,
                )
                host = urlparse(self.live_server_url).hostname
                await context.add_cookies(
                    [{
                        "name": "sessionid",
                        "value": self.a_cookie,
                        "domain": host,
                        "path": "/",
                    }]
                )
                page = await context.new_page()
                output_dir = os.environ.get("UI76_SCREENSHOT_DIR")
                if output_dir:
                    Path(output_dir).mkdir(parents=True, exist_ok=True)
                try:
                    await page.goto(f"{self.live_server_url}/team/")
                    self.assertEqual(await page.locator("#answer-input").count(), 1)
                    await asyncio.to_thread(
                        admin_freeze,
                        self.admin,
                        AdminTeam(str(uuid4()), self.run_id, "a"),
                    )
                    await page.locator(".state-panel-freeze").wait_for(timeout=5000)
                    ice = page.locator("#freeze-backdrop")
                    await ice.wait_for(state="visible", timeout=5000)
                    self.assertTrue(await page.locator(".freeze-message").is_visible())
                    self.assertTrue(await ice.locator(".freeze-ghost").is_visible())
                    self.assertTrue(await ice.locator(".freeze-ice").is_visible())
                    for selector, minimum in (
                        (".freeze-message h2", 44),
                        (".freeze-message__description strong", 20),
                        (".freeze-timer", 56),
                    ):
                        size = await page.locator(selector).evaluate(
                            "el => parseFloat(getComputedStyle(el).fontSize)"
                        )
                        self.assertGreaterEqual(size, minimum, selector)
                    self.assertEqual(
                        await page.locator(
                            "#question-pane img, #question-pane audio, "
                            "#question-pane video, #question-pane .hint-card, "
                            "#question-pane .answer-form, #team-actions form, "
                            "#team-actions button, #question-pane button"
                        ).count(),
                        0,
                    )
                    self.assertEqual(await page.locator("#team-shop-dialog").count(), 0)
                    self.assertNotIn("answer-input", await page.content())
                    time_text = await page.locator(".freeze-timer").inner_text()
                    self.assertRegex(time_text, re.compile(r"^\d{2}:\d{2}$"))
                    await page.evaluate(
                        "window.__freezeBackdrop = "
                        "document.getElementById('freeze-backdrop')"
                    )
                    if output_dir:
                        await page.wait_for_timeout(180)
                        await page.screenshot(
                            path=str(Path(output_dir) / "issue76-keyframe-390x844.png"),
                            animations="allow",
                        )
                    await page.wait_for_timeout(2900)
                    self.assertTrue(
                        await page.evaluate(
                            "window.__freezeBackdrop === "
                            "document.getElementById('freeze-backdrop')"
                        ),
                        "Freeze layer must not be remounted by 500ms polls.",
                    )
                    self.assertLessEqual(
                        int(
                            await page.locator(".freeze-timer").get_attribute(
                                "data-remaining-ms"
                            )
                        ),
                        300000,
                    )
                    if output_dir:
                        await page.screenshot(
                            path=str(Path(output_dir) / "issue76-settled-390x844.png"),
                            animations="disabled",
                        )
                    await page.emulate_media(reduced_motion="reduce")
                    self.assertEqual(
                        await page.locator(".freeze-ice").evaluate(
                            "el => getComputedStyle(el, '::before').animationDuration"
                        ),
                        "0s",
                    )
                    await page.reload()
                    await page.locator(".state-panel-freeze").wait_for(timeout=5000)
                    self.assertTrue(await page.locator("#freeze-backdrop").is_visible())
                    self.assertEqual(await page.locator("#answer-input").count(), 0)
                    await asyncio.to_thread(
                        admin_unfreeze,
                        self.admin,
                        AdminTeam(str(uuid4()), self.run_id, "a"),
                    )
                    await page.locator("#answer-input").wait_for(timeout=5000)
                    self.assertFalse(
                        await page.locator("#freeze-backdrop").is_visible()
                    )
                finally:
                    await context.close()
                    await browser.close()

        asyncio.run(check())
