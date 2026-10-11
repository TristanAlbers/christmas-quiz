import asyncio
import json

from ui74_capture_temp import CaptureIssue74ReferenceScenario


class CaptureIssue74ImpeccableOverlay(CaptureIssue74ReferenceScenario):
    def test_overlay(self):
        async def capture():
            from playwright.async_api import async_playwright
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                context, page = await self._page(browser, 390, 844)
                logs = []
                page.on("console", lambda message: logs.append({"type": message.type, "text": message.text}))
                try:
                    await page.add_script_tag(path="/overlay/detect.js")
                    await page.wait_for_timeout(3000)
                    await page.screenshot(path=self.output / "impeccable-overlay-390x844.png", full_page=False)
                    (self.output / "impeccable-console.json").write_text(json.dumps(logs, indent=2))
                finally:
                    await context.close()
                    await browser.close()
        asyncio.run(capture())
