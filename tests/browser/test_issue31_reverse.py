import asyncio
import os
from pathlib import Path

from tests.browser.issue31_support import Issue31BrowserCase


class Issue31ReverseBrowserTests(Issue31BrowserCase):
    def test_reverse_purchase_closes_shop_and_reflection_animates_both_teams(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                ba, ca, a = await self.page_for(playwright, self.a_cookie)
                bb, cb, b = await self.page_for(playwright, self.b_cookie)
                try:
                    await a.locator("[aria-controls='team-shop-dialog']").click()
                    await a.get_by_role(
                        "button", name="Uno Reverse kopen (2)"
                    ).click()
                    await a.locator("#team-shop-dialog").wait_for(
                        state="hidden", timeout=5000
                    )
                    purchase = a.locator(
                        '#routine-feedback[data-kind="reverse_purchased"]'
                    )
                    await purchase.wait_for(state="visible", timeout=5000)
                    purchase_text = (await purchase.inner_text()).lower()
                    self.assertIn("reverse staat klaar", purchase_text)
                    self.assertIn("volgende freeze", purchase_text)
                    self.assertEqual(
                        await purchase.evaluate(
                            "el => getComputedStyle(el).animationDuration"
                        ),
                        "3.4s",
                    )
                    self.assertFalse(await a.locator("#gameplay-event").is_visible())

                    # The animation must use the same vector arrows as the shop,
                    # never an OS-dependent Unicode glyph on iOS/Android.
                    symbol = purchase.locator(
                        ".routine-feedback__reverse-card span"
                    )
                    self.assertEqual((await symbol.inner_text()).strip(), "")
                    purchase_paths = await symbol.locator("svg path").evaluate_all(
                        "(paths) => paths.map(p => p.getAttribute('d'))"
                    )
                    shop_paths = await a.locator(
                        ".shop-item--reverse .resource-reverse-card__symbol svg path"
                    ).evaluate_all(
                        "(paths) => paths.map(p => p.getAttribute('d'))"
                    )
                    self.assertEqual(len(purchase_paths), 2)
                    self.assertEqual(purchase_paths, shop_paths)
                    self.assertTrue(await symbol.locator("svg").is_visible())
                    self.assertEqual(
                        await purchase.locator(
                            ".routine-feedback__reverse-card"
                        ).evaluate("el => getComputedStyle(el).animationName"),
                        "routine-feedback-card",
                    )
                    screenshot_dir = os.environ.get("REVERSE_ANIMATION_SCREENSHOT_DIR")
                    if screenshot_dir:
                        Path(screenshot_dir).mkdir(parents=True, exist_ok=True)
                        await a.wait_for_timeout(1250)
                        engine = os.environ.get("ISSUE31_BROWSER_ENGINE", "chromium")
                        await a.screenshot(
                            path=str(
                                Path(screenshot_dir)
                                / f"reverse-purchase-{engine}-390x844.png"
                            )
                        )

                    await b.locator("[aria-controls='team-shop-dialog']").click()
                    await b.get_by_role(
                        "button", name="Andere team bevriezen (3)"
                    ).click()
                    reflected = b.locator(
                        "#gameplay-event.gameplay-event--attacker-reversed"
                    )
                    saved = a.locator("#gameplay-event.gameplay-event--saved")
                    await reflected.wait_for(state="visible", timeout=5000)
                    await saved.wait_for(state="visible", timeout=5000)
                    reflected_text = (await reflected.inner_text()).lower()
                    self.assertIn("freeze verstuurd", reflected_text)
                    self.assertIn("teruggekaatst!", reflected_text)
                    self.assertIn(
                        "Jullie Reverse heeft jullie gered!", await saved.inner_text()
                    )
                    self.assertEqual(
                        await reflected.evaluate(
                            "el => getComputedStyle(el).animationDuration"
                        ),
                        "4.6s",
                    )
                    await b.locator(".state-panel-freeze").wait_for(timeout=5000)
                    self.assertEqual(await b.locator("#answer-input").count(), 0)
                    self.assertEqual(await a.locator("#answer-input").count(), 1)
                    await a.reload()
                    self.assertFalse(await a.locator("#gameplay-event").is_visible())
                    self.assertFalse(await a.locator("#routine-feedback").is_visible())
                finally:
                    await ca.close()
                    await ba.close()
                    await cb.close()
                    await bb.close()

        asyncio.run(check())

    def test_rejected_shop_purchase_stays_open_without_animation(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser, context, page = await self.page_for(
                    playwright, self.a_cookie
                )
                try:
                    await page.locator("[aria-controls='team-shop-dialog']").click()
                    await page.get_by_role(
                        "button", name="Uno Reverse kopen (2)"
                    ).click()
                    await page.locator("#team-shop-dialog").wait_for(
                        state="hidden", timeout=5000
                    )
                    await page.locator("[aria-controls='team-shop-dialog']").click()
                    shop = page.locator("#team-shop-dialog")
                    await page.get_by_role(
                        "button", name="Andere team bevriezen (3)"
                    ).click()
                    await page.locator("#shop-feedback").get_by_text(
                        "Actie geweigerd", exact=False
                    ).wait_for(timeout=5000)
                    self.assertTrue(await shop.evaluate("el => el.open"))
                    self.assertFalse(
                        await page.locator("#gameplay-event").is_visible()
                    )
                finally:
                    await context.close()
                    await browser.close()

        asyncio.run(check())
