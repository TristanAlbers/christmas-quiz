"""Real Django/HTMX visual and lifecycle checks for issue #107."""

import asyncio
import os
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.templatetags.static import static
from django.test import Client, LiveServerTestCase

from quiz.application import admin_unfreeze, start_game
from quiz.contracts import Actor, AdminTeam, StartGame
from quiz.models import AccountRole, TeamRun


class MidnightImpactBrowserTests(LiveServerTestCase):
    def setUp(self):
        if not os.environ.get("TEST_DATABASE_PATH"):
            self.skipTest("requires disposable file-backed TEST_DATABASE_PATH")
        users = get_user_model()
        admin_user = users.objects.create_user("issue107-browser-admin")
        team_user = users.objects.create_user("issue107-browser-team")
        opponent_user = users.objects.create_user("issue107-browser-opponent")
        AccountRole.objects.create(user=admin_user, role="admin")
        AccountRole.objects.create(user=team_user, role="team", team_id="a")
        AccountRole.objects.create(user=opponent_user, role="team", team_id="b")
        self.admin = Actor(admin_user.pk, "admin")
        self.run_id = start_game(
            self.admin,
            StartGame(str(uuid4()), "christmas-2026-demo"),
        ).run_id
        TeamRun.objects.filter(run_id=self.run_id).update(points=50)
        client = Client()
        client.force_login(team_user)
        self.session_cookie = client.cookies["sessionid"].value
        self.expected_music_note_url = static("quiz/chocolates/muzieknoot.png")
        opponent_client = Client()
        opponent_client.force_login(opponent_user)
        self.opponent_cookie = opponent_client.cookies["sessionid"].value
        output = os.environ.get("UI107_SCREENSHOT_DIR")
        self.output_dir = Path(output) if output else None
        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)

    async def open_phone(self, playwright, session_cookie=None):
        engine = os.environ.get("ISSUE107_BROWSER_ENGINE", "chromium")
        if engine not in {"chromium", "webkit"}:
            raise ValueError("ISSUE107_BROWSER_ENGINE must be chromium or webkit")
        browser = await getattr(playwright, engine).launch()
        context = await browser.new_context(
            viewport={"width": 390, "height": 844},
            device_scale_factor=1,
            reduced_motion="reduce",
        )
        host = urlparse(self.live_server_url).hostname
        await context.add_cookies(
            [
                {
                    "name": "sessionid",
                "value": session_cookie or self.session_cookie,
                    "domain": host,
                    "path": "/",
                }
            ]
        )
        page = await context.new_page()
        response = await page.goto(f"{self.live_server_url}/team/")
        self.assertIsNotNone(response)
        self.assertEqual(response.status, 200)
        await page.locator(".team-advent-panel").wait_for(timeout=5000)
        return browser, context, page

    async def capture(self, page, name):
        if self.output_dir:
            engine = os.environ.get("ISSUE107_BROWSER_ENGINE", "chromium")
            await page.screenshot(
                path=str(self.output_dir / f"actual-{name}-{engine}-390x844.png"),
                full_page=False,
            )

    async def capture_reference(self, browser):
        reference = os.environ.get("UI107_REFERENCE_HTML")
        if not reference or not self.output_dir:
            return
        reference_path = Path(reference).resolve()
        self.assertTrue(reference_path.is_file())
        labels = {
            "solve": "Puzzel opgelost",
            "reverse": "Reverse kopen",
            "skip": "Overslaan",
            "hint": "Hint kopen",
        }
        for key, label in labels.items():
            context = await browser.new_context(
                viewport={"width": 390, "height": 844},
                device_scale_factor=1,
                reduced_motion="reduce",
            )
            page = await context.new_page()
            try:
                await page.goto(reference_path.as_uri())
                await page.get_by_role("button", name=label).click()
                await page.add_style_tag(
                    content="""
                    html,body,main,#qm-motion-next,.qm-stage{margin:0!important;padding:0!important;
                      width:390px!important;height:844px!important;max-width:none!important;
                      min-height:0!important;overflow:hidden!important}
                    body>main>header,.demo-note,.qm-controls{display:none!important}
                    #qm-motion-next .qm-phone{width:390px!important;
                      height:844px!important;
                      border:0!important;border-radius:0!important;box-shadow:none!important}
                    """
                )
                await page.wait_for_timeout(950)
                await page.locator(".qm-phone").screenshot(
                    path=str(self.output_dir / f"reference-{key}-390x844.png")
                )
            finally:
                await context.close()

    async def wait_for_film(self, page, kind, expected_duration):
        film = page.locator(f'#routine-feedback[data-kind="{kind}"]')
        await film.wait_for(state="visible", timeout=5000)
        self.assertEqual(
            await film.evaluate("el => getComputedStyle(el).animationDuration"),
            expected_duration,
        )
        self.assertTrue(await page.locator(".app-shell").evaluate("el => el.inert"))
        return film

    def test_all_four_confirmed_actions_use_one_full_motion_surface(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser, context, page = await self.open_phone(playwright)
                try:
                    await self.capture_reference(browser)

                    await page.get_by_role("button", name="Winkel", exact=False).click()
                    await page.get_by_role("button", name="Hint kopen (1)").click()
                    film = await self.wait_for_film(page, "hint_purchased", "2.7s")
                    self.assertEqual(
                        await film.locator("h2").inner_text(), "Een lichtpuntje"
                    )
                    self.assertEqual(
                        await film.locator(".routine-feedback__letter").inner_text(),
                        "?",
                    )
                    await page.wait_for_timeout(950)
                    await self.capture(page, "hint-hold")
                    await film.wait_for(state="hidden", timeout=4000)
                    await self.capture(page, "hint-settled")

                    await page.get_by_role("button", name="Winkel", exact=False).click()
                    await page.get_by_role(
                        "button", name="Uno Reverse kopen (2)"
                    ).click()
                    film = await self.wait_for_film(page, "reverse_purchased", "3.4s")
                    self.assertEqual(
                        await film.locator("h2").inner_text(), "Reverse staat klaar"
                    )
                    purchase_paths = await film.locator("svg path").evaluate_all(
                        "paths => paths.map(path => path.getAttribute('d'))"
                    )
                    shop_paths = await page.locator(
                        ".shop-item--reverse .resource-reverse-card__symbol svg path"
                    ).evaluate_all("paths => paths.map(path => path.getAttribute('d'))")
                    self.assertEqual(purchase_paths, shop_paths)
                    await page.wait_for_timeout(950)
                    await self.capture(page, "reverse-hold")
                    await film.wait_for(state="hidden", timeout=4500)
                    self.assertIn(
                        "Actief",
                        await page.locator(".resource-card--reverse").inner_text(),
                    )
                    await self.capture(page, "reverse-settled")

                    await page.locator("[data-skip-action]").click()
                    film = await self.wait_for_film(page, "puzzle_skipped", "2.8s")
                    self.assertEqual(
                        await film.locator("h2").inner_text(), "Een deur verder"
                    )
                    self.assertEqual(
                        await film.locator(
                            ".routine-feedback__page--current strong"
                        ).inner_text(),
                        "1",
                    )
                    self.assertEqual(
                        await film.locator(
                            ".routine-feedback__page--next strong"
                        ).inner_text(),
                        "2",
                    )
                    await page.wait_for_timeout(950)
                    await self.capture(page, "skip-hold")
                    await film.wait_for(state="hidden", timeout=4000)
                    await self.capture(page, "skip-settled")

                    await page.locator("#answer-input").fill("3")
                    await page.evaluate(
                        """() => document.body.addEventListener(
                          'routineFeedbackConfirmed',
                          event => { window.__issue107Detail = event.detail; },
                          {once:true}
                        )"""
                    )
                    await page.get_by_role("button", name="Antwoord insturen").click()
                    film = await self.wait_for_film(page, "puzzle_solved", "3.5s")
                    self.assertEqual(
                        await film.locator("h2").inner_text(), "Goed gevonden!"
                    )
                    chocolate = film.locator(".routine-feedback__chocolate")
                    self.assertEqual(
                        await chocolate.get_attribute("data-chocolate-subject"),
                        "muzieknoot",
                    )
                    self.assertEqual(
                        await chocolate.locator("image").get_attribute("href"),
                        self.expected_music_note_url,
                    )
                    self.assertEqual(
                        await chocolate.locator("svg").get_attribute("viewBox"),
                        "247 123 854 1063",
                    )
                    await page.wait_for_timeout(950)
                    await self.capture(page, "solve-hold")
                    await film.wait_for(state="hidden", timeout=4500)
                    await self.capture(page, "solve-settled")

                    await page.evaluate(
                        """() => document.body.dispatchEvent(new CustomEvent(
                          'routineFeedbackConfirmed', {detail: window.__issue107Detail}
                        ))"""
                    )
                    await page.wait_for_timeout(200)
                    self.assertFalse(await film.is_visible())
                    self.assertFalse(
                        await page.locator(".app-shell").evaluate("el => el.inert")
                    )
                    self.assertNotIn("fragment", (await film.inner_text()).lower())
                    self.assertTrue(
                        await page.evaluate(
                            "document.documentElement.scrollWidth <= innerWidth"
                        )
                    )
                finally:
                    await context.close()
                    await browser.close()

        asyncio.run(check())

    def test_attack_interrupts_discards_lock_and_does_not_block_later_feedback(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser, context, page = await self.open_phone(playwright)
                other_browser, other_context, other = await self.open_phone(
                    playwright, self.opponent_cookie
                )
                try:
                    await page.get_by_role("button", name="Winkel", exact=False).click()
                    await page.get_by_role("button", name="Hint kopen (1)").click()
                    film = await self.wait_for_film(page, "hint_purchased", "2.7s")
                    event_id = await film.get_attribute("data-event-id")
                    await other.get_by_role(
                        "button", name="Winkel", exact=False
                    ).click()
                    await other.get_by_role(
                        "button", name="Andere team bevriezen (3)"
                    ).click()
                    await page.locator(
                        "#gameplay-event.gameplay-event--target"
                    ).wait_for(state="visible", timeout=5000)
                    await film.wait_for(state="hidden", timeout=1000)
                    self.assertFalse(
                        await page.evaluate(
                            "document.body.classList.contains('routine-feedback-active')"
                        )
                    )
                    await asyncio.to_thread(
                        admin_unfreeze,
                        self.admin,
                        AdminTeam(str(uuid4()), self.run_id, "a"),
                    )
                    await page.locator("#answer-input").wait_for(timeout=5000)
                    await page.wait_for_function(
                        "!document.body.classList.contains('gameplay-film-active')",
                        timeout=6000,
                    )
                    self.assertFalse(await film.is_visible())
                    self.assertNotEqual(
                        await film.get_attribute("data-event-id"),
                        event_id,
                    )
                    self.assertFalse(
                        await page.locator(".app-shell").evaluate("el => el.inert")
                    )

                    # The expired attack node keeps its event id for receipt
                    # deduplication; it must not suppress a later routine film.
                    self.assertIsNotNone(
                        await page.locator("#gameplay-event").get_attribute(
                            "data-event-id"
                        )
                    )
                    await page.get_by_role(
                        "button", name="Winkel", exact=False
                    ).click()
                    await page.get_by_role("button", name="Hint kopen (1)").click()
                    await self.wait_for_film(page, "hint_purchased", "2.7s")
                finally:
                    await other_context.close()
                    await other_browser.close()
                    await context.close()
                    await browser.close()

        asyncio.run(check())
