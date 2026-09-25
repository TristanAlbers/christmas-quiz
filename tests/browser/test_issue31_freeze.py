import asyncio
from uuid import uuid4

from quiz.application import admin_freeze, admin_unfreeze
from quiz.contracts import AdminTeam
from tests.browser.issue31_support import Issue31BrowserCase


class Issue31FreezeBrowserTests(Issue31BrowserCase):
    def test_normal_freeze_animates_attacker_and_victim_with_reduced_motion(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                ba, ca, a = await self.page_for(playwright, self.a_cookie)
                bb, cb, b = await self.page_for(playwright, self.b_cookie)
                try:
                    await a.emulate_media(reduced_motion="reduce")
                    await b.emulate_media(reduced_motion="reduce")
                    await a.get_by_role("button", name="Shop Power-ups").click()
                    await a.get_by_role("button", name="Freeze opponent (3)").click()
                    attacker = a.locator(
                        "#gameplay-event.gameplay-event--attacker"
                    )
                    victim = b.locator("#gameplay-event.gameplay-event--victim")
                    await attacker.wait_for(state="visible", timeout=5000)
                    await victim.wait_for(state="visible", timeout=5000)
                    self.assertIn("direct hit!", (await attacker.inner_text()).lower())
                    self.assertIn(
                        "you have been frozen!", (await victim.inner_text()).lower()
                    )
                    animation = await attacker.locator(
                        ".gameplay-event__stage--attack"
                    ).evaluate("el => getComputedStyle(el).animationName")
                    self.assertEqual(animation, "gameplay-static-first")
                    await b.locator(".state-panel-freeze").wait_for(timeout=5000)
                    self.assertEqual(await b.locator("#answer-input").count(), 0)
                    await b.reload()
                    self.assertFalse(await b.locator("#gameplay-event").is_visible())
                finally:
                    await ca.close()
                    await ba.close()
                    await cb.close()
                    await bb.close()

        asyncio.run(check())

    def test_open_shop_updates_freeze_eligibility_without_closing(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser, context, page = await self.page_for(
                    playwright, self.a_cookie
                )
                try:
                    await page.get_by_role("button", name="Shop Power-ups").click()
                    shop = page.locator("#team-shop-dialog")
                    await asyncio.to_thread(
                        admin_freeze,
                        self.admin,
                        AdminTeam(str(uuid4()), self.run_id, "b"),
                    )
                    unavailable = page.get_by_role(
                        "button", name="Freeze unavailable"
                    )
                    await unavailable.wait_for(timeout=5000)
                    self.assertTrue(await shop.evaluate("el => el.open"))
                    self.assertTrue(await unavailable.is_disabled())
                    await asyncio.to_thread(
                        admin_unfreeze,
                        self.admin,
                        AdminTeam(str(uuid4()), self.run_id, "b"),
                    )
                    await page.get_by_role(
                        "button", name="Freeze opponent (3)"
                    ).wait_for(timeout=5000)
                    self.assertTrue(await shop.evaluate("el => el.open"))
                finally:
                    await context.close()
                    await browser.close()

        asyncio.run(check())
