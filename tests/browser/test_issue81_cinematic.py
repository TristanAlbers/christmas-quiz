"""Issue #81: actual two-authenticated-phone Freeze films and draft semantics."""

import asyncio
import os
from pathlib import Path
from uuid import uuid4

from quiz.application import admin_unfreeze
from quiz.contracts import AdminTeam
from tests.browser.issue31_support import Issue31BrowserCase


class Issue81CinematicBrowserTests(Issue31BrowserCase):
    async def capture_pair(self, a, b, name):
        folder = os.environ.get("UI81_SCREENSHOT_DIR")
        if not folder:
            return
        output = Path(folder)
        output.mkdir(parents=True, exist_ok=True)
        engine = os.environ.get("ISSUE31_BROWSER_ENGINE", "chromium")
        for team, page in (("a", a), ("b", b)):
            await page.screenshot(
                path=str(output / f"issue81-{name}-{team}-{engine}-390x844.png"),
                animations="allow",
            )

    async def open_phones(self, playwright):
        ba, ca, a = await self.page_for(playwright, self.a_cookie)
        bb, cb, b = await self.page_for(playwright, self.b_cookie)
        await a.set_viewport_size({"width": 390, "height": 844})
        await b.set_viewport_size({"width": 390, "height": 844})
        return (ba, ca, a), (bb, cb, b)

    def test_normal_attack_has_ordered_phone_films_and_clears_only_victim(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                (ba, ca, a), (bb, cb, b) = await self.open_phones(playwright)
                try:
                    await a.locator("#answer-input").fill("aanvaller houdt dit")
                    await b.locator("#answer-input").fill("slachtoffer verliest dit")
                    await a.evaluate(
                        "window.__originalAnswer = "
                        "document.getElementById('answer-input')"
                    )
                    await a.get_by_role("button", name="Winkel").click()
                    await a.get_by_role(
                        "button", name="Andere team bevriezen (3)"
                    ).click()
                    attack = a.locator("#gameplay-event.gameplay-event--attacker")
                    victim = b.locator("#gameplay-event.gameplay-event--victim")
                    await attack.wait_for(state="visible", timeout=6000)
                    await victim.wait_for(state="visible", timeout=6000)
                    self.assertEqual(
                        await attack.get_attribute("data-event-id"),
                        await victim.get_attribute("data-event-id"),
                    )
                    self.assertEqual(
                        await attack.evaluate(
                            "el => getComputedStyle(el).animationDuration"
                        ),
                        "4.6s",
                    )
                    await a.wait_for_timeout(900)
                    self.assertGreater(
                        float(await attack.locator(
                            ".gameplay-event__stage--attack"
                        ).evaluate("el => getComputedStyle(el).opacity")),
                        0.5,
                    )
                    await self.capture_pair(a, b, "normal-launch")

                    await a.wait_for_timeout(2000)
                    self.assertGreater(
                        float(await victim.locator(
                            ".gameplay-event__stage--impact"
                        ).evaluate("el => getComputedStyle(el).opacity")),
                        0.5,
                    )
                    await self.capture_pair(a, b, "normal-impact")

                    await a.wait_for_timeout(2400)
                    self.assertEqual(
                        await victim.evaluate(
                            "el => getComputedStyle(el).visibility"
                        ), "hidden",
                    )
                    await b.locator(".state-panel-freeze").wait_for(timeout=5000)
                    self.assertEqual(await b.locator("#answer-input").count(), 0)
                    self.assertEqual(
                        await a.locator("#answer-input").input_value(),
                        "aanvaller houdt dit",
                    )
                    self.assertTrue(await a.evaluate(
                        "window.__originalAnswer === "
                        "document.getElementById('answer-input')"
                    ))
                    await self.capture_pair(a, b, "normal-settled")

                    await asyncio.to_thread(
                        admin_unfreeze,
                        self.admin,
                        AdminTeam(str(uuid4()), self.run_id, "b"),
                    )
                    await b.locator("#answer-input").wait_for(timeout=5000)
                    self.assertEqual(await b.locator("#answer-input").input_value(), "")
                    await a.reload()
                    await b.reload()
                    self.assertFalse(await a.locator("#gameplay-event").is_visible())
                    self.assertFalse(await b.locator("#gameplay-event").is_visible())
                finally:
                    await ca.close()
                    await ba.close()
                    await cb.close()
                    await bb.close()

        asyncio.run(check())

    def test_reverse_plays_after_launch_and_preserves_protected_draft(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                (ba, ca, a), (bb, cb, b) = await self.open_phones(playwright)
                try:
                    await a.get_by_role("button", name="Winkel").click()
                    await a.get_by_role(
                        "button", name="Uno Reverse kopen (2)"
                    ).click()
                    await a.locator("#team-shop-dialog").wait_for(
                        state="hidden", timeout=5000
                    )
                    self.assertFalse(
                        await a.locator("#gameplay-event").is_visible()
                    )
                    await a.locator("#answer-input").fill("blijft behouden")
                    await a.locator("#answer-input").focus()
                    await a.locator("#answer-input").evaluate(
                        "el => el.setSelectionRange(2, 6)"
                    )
                    await a.evaluate(
                        "window.__protectedInput = "
                        "document.getElementById('answer-input')"
                    )
                    await b.locator("#answer-input").fill("verliest door Reverse")
                    await b.get_by_role("button", name="Winkel").click()
                    await b.get_by_role(
                        "button", name="Andere team bevriezen (3)"
                    ).click()
                    reflected = b.locator(
                        "#gameplay-event.gameplay-event--attacker-reversed"
                    )
                    saved = a.locator("#gameplay-event.gameplay-event--saved")
                    await reflected.wait_for(state="visible", timeout=6000)
                    await saved.wait_for(state="visible", timeout=6000)
                    self.assertEqual(
                        await reflected.get_attribute("data-event-id"),
                        await saved.get_attribute("data-event-id"),
                    )
                    await a.wait_for_timeout(500)
                    self.assertGreater(
                        float(await saved.locator(
                            ".gameplay-event__stage--attack"
                        ).evaluate("el => getComputedStyle(el).opacity")),
                        0.5,
                    )
                    await self.capture_pair(a, b, "reverse-launch")

                    await a.wait_for_timeout(1850)
                    for page in (a, b):
                        card = page.locator(
                            ".gameplay-event__stage--reverse-good "
                            ".gameplay-event__reverse-card"
                            if page == a else
                            ".gameplay-event__stage--reverse-bad "
                            ".gameplay-event__reverse-card"
                        )
                        self.assertTrue(await card.is_visible())
                        self.assertEqual(await card.locator("svg path").count(), 2)
                        self.assertEqual(
                            "REVERSE" in await card.inner_text(),
                            True,
                        )
                    await self.capture_pair(a, b, "reverse-card")

                    await a.wait_for_timeout(2550)
                    await b.locator(".state-panel-freeze").wait_for(timeout=5000)
                    self.assertEqual(await b.locator("#answer-input").count(), 0)
                    self.assertEqual(
                        await a.locator("#answer-input").input_value(),
                        "blijft behouden",
                    )
                    self.assertTrue(await a.evaluate(
                        "window.__protectedInput === "
                        "document.getElementById('answer-input')"
                    ))
                    self.assertEqual(
                        await a.locator("#answer-input").evaluate(
                            "el => [document.activeElement === el, "
                            "el.selectionStart, el.selectionEnd]"
                        ),
                        [True, 2, 6],
                    )
                    await self.capture_pair(a, b, "reverse-settled")
                    await asyncio.to_thread(
                        admin_unfreeze,
                        self.admin,
                        AdminTeam(str(uuid4()), self.run_id, "b"),
                    )
                    await b.locator("#answer-input").wait_for(timeout=5000)
                    self.assertEqual(await b.locator("#answer-input").input_value(), "")
                    await a.reload()
                    await b.reload()
                    self.assertFalse(await a.locator("#gameplay-event").is_visible())
                    self.assertFalse(await b.locator("#gameplay-event").is_visible())
                finally:
                    await ca.close()
                    await ba.close()
                    await cb.close()
                    await bb.close()

        asyncio.run(check())
