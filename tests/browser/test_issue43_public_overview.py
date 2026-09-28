import asyncio
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import LiveServerTestCase, override_settings

from quiz.application import admin_freeze, admin_unfreeze, start_game
from quiz.contracts import Actor, AdminTeam, StartGame
from quiz.models import AccountRole, FragmentAward, Run, TeamRun


class Issue43PublicOverviewBrowserTests(LiveServerTestCase):
    def setUp(self):
        if not os.environ.get("TEST_DATABASE_PATH"):
            self.skipTest("requires disposable file-backed TEST_DATABASE_PATH")
        self.snapshots = TemporaryDirectory()
        self.addCleanup(self.snapshots.cleanup)
        scope = override_settings(QUIZ_SNAPSHOT_ROOT=Path(self.snapshots.name))
        scope.enable()
        self.addCleanup(scope.disable)

        users = get_user_model()
        admin_user = users.objects.create_user("issue43-browser-admin")
        AccountRole.objects.create(user=admin_user, role="admin")
        self.admin = Actor(admin_user.pk, "admin")
        self.run_id = start_game(
            self.admin, StartGame(str(uuid4()), "christmas-2026-demo")
        ).run_id

    async def _overview_page(self, playwright):
        browser = await playwright.chromium.launch()
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()
        await page.goto(f"{self.live_server_url}/overview/")
        return browser, context, page

    def _seed_private_state(self):
        TeamRun.objects.filter(run_id=self.run_id, team_id="a").update(
            points=98765,
            hint_tokens=9,
            reverse_active=True,
        )
        FragmentAward.objects.create(
            run_id=self.run_id,
            team_id="a",
            puzzle_id="private-43",
            fragment="PRIVATE-FRAGMENT-43",
        )

    def test_quizzmass_branding_and_authoritative_hhmmss_hide_private_state(self):
        self._seed_private_state()
        Run.objects.filter(pk=self.run_id).update(
            global_state="PAUSED",
            pause_resume_target="ADVENT_QUIZ",
            gameplay_elapsed_ms=5_049_000,
            advent_clock_anchor=None,
        )

        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser, context, page = await self._overview_page(playwright)
                try:
                    await page.get_by_role("heading", name="Quizzmass").wait_for()
                    self.assertEqual(
                        await page.locator(".game-clock strong").inner_text(),
                        "01:24:09",
                    )
                    self.assertEqual(await page.locator(".state-badge").count(), 0)
                    public_text = (
                        await page.locator("#overview-state").inner_text()
                    ).lower()
                    self.assertNotIn("advent_quiz", public_text)
                    self.assertNotIn("advent quiz in progress", public_text)
                    self.assertNotIn("98765", public_text)
                    self.assertNotIn("private-fragment-43", public_text)
                    for private_word in ("hint", "reverse", "fragment"):
                        self.assertNotIn(private_word, public_text)
                finally:
                    await context.close()
                    await browser.close()

        asyncio.run(check())

    def test_freeze_enters_and_leaves_via_polling_without_hiding_progress(self):
        self._seed_private_state()

        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser, context, page = await self._overview_page(playwright)
                try:
                    team_a = page.locator('.advent-progress[data-team-id="a"]')
                    self.assertEqual(await team_a.get_attribute("data-frozen"), "false")
                    self.assertEqual(
                        await team_a.locator(".advent-freeze-badge").count(),
                        0,
                    )

                    await asyncio.to_thread(
                        admin_freeze,
                        self.admin,
                        AdminTeam(str(uuid4()), self.run_id, "a"),
                    )
                    frozen = page.locator(
                        '.advent-progress[data-team-id="a"][data-frozen="true"]'
                    )
                    await frozen.wait_for(state="visible", timeout=5000)
                    badge = frozen.locator(".advent-freeze-badge")
                    self.assertIn("Bevroren", await badge.inner_text())
                    self.assertEqual(await frozen.locator(".advent-door").count(), 25)
                    self.assertEqual(await frozen.locator(".progress-count").count(), 1)
                    animation_name = await frozen.evaluate(
                        "el => getComputedStyle(el).animationName"
                    )
                    self.assertEqual(animation_name, "none")

                    public_text = (
                        await page.locator("#overview-state").inner_text()
                    ).lower()
                    self.assertNotIn("98765", public_text)
                    self.assertNotIn("private-fragment-43", public_text)
                    for private_word in ("hint", "reverse", "fragment"):
                        self.assertNotIn(private_word, public_text)

                    await asyncio.to_thread(
                        admin_unfreeze,
                        self.admin,
                        AdminTeam(str(uuid4()), self.run_id, "a"),
                    )
                    await frozen.wait_for(state="detached", timeout=5000)
                    team_a = page.locator('.advent-progress[data-team-id="a"]')
                    await team_a.wait_for(state="visible", timeout=5000)
                    self.assertEqual(await team_a.get_attribute("data-frozen"), "false")
                    self.assertEqual(
                        await team_a.locator(".advent-freeze-badge").count(),
                        0,
                    )
                finally:
                    await context.close()
                    await browser.close()

        asyncio.run(check())
