import asyncio

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
                    self.assertIn(
                        "gekocht en geactiveerd",
                        (await a.locator("#action-feedback").inner_text()).lower(),
                    )
                    purchase = a.locator("#reverse-purchase.reverse-purchase")
                    await purchase.wait_for(state="visible", timeout=5000)
                    purchase_text = (await purchase.inner_text()).lower()
                    self.assertIn("aankoop gelukt", purchase_text)
                    self.assertIn("uno reverse geactiveerd!", purchase_text)
                    self.assertEqual(
                        await purchase.evaluate(
                            "el => getComputedStyle(el).animationDuration"
                        ),
                        "3s",
                    )
                    self.assertFalse(await a.locator("#gameplay-event").is_visible())

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
                    self.assertIn("freeze gelanceerd", reflected_text)
                    self.assertIn("teruggekaatst!", reflected_text)
                    self.assertIn("Jullie Reverse heeft jullie gered!", await saved.inner_text())
                    self.assertEqual(
                        await reflected.evaluate(
                            "el => getComputedStyle(el).animationDuration"
                        ),
                        "4s",
                    )
                    await b.locator(".state-panel-freeze").wait_for(timeout=5000)
                    self.assertEqual(await b.locator("#answer-input").count(), 0)
                    self.assertEqual(await a.locator("#answer-input").count(), 1)
                    await a.reload()
                    self.assertFalse(await a.locator("#gameplay-event").is_visible())
                    self.assertFalse(await a.locator("#reverse-purchase").is_visible())
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
