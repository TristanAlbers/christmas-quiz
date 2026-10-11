"""Issue #73: real Django/HTMX TV Advent V4, one-shot doors and public privacy."""

import asyncio
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import LiveServerTestCase, override_settings
from django.utils import timezone

from quiz.application import (
    admin_freeze,
    admin_unfreeze,
    force_complete_current,
    start_game,
)
from quiz.contracts import Actor, AdminPuzzle, AdminTeam, StartGame
from quiz.models import AccountRole, FragmentAward, PuzzleProgress, Run, TeamRun


class MidnightAdventTVBrowserTests(LiveServerTestCase):
    def setUp(self):
        if not os.environ.get("TEST_DATABASE_PATH"):
            self.skipTest("requires disposable file-backed TEST_DATABASE_PATH")
        self.snapshots = TemporaryDirectory()
        self.addCleanup(self.snapshots.cleanup)
        scope = override_settings(QUIZ_SNAPSHOT_ROOT=Path(self.snapshots.name))
        scope.enable()
        self.addCleanup(scope.disable)

        user = get_user_model().objects.create_user("issue73-tv-admin")
        AccountRole.objects.create(user=user, role="admin")
        self.admin = Actor(user.pk, "admin")
        self.run_id = start_game(
            self.admin, StartGame(str(uuid4()), "christmas-2026-demo")
        ).run_id

    def _representative_progress(self):
        # Keep both teams' real projected state consistent with the approved
        # illustration: 13 completed for A, 10 for B, current 14 and 11.
        for team_id, completed in (("a", 13), ("b", 10)):
            PuzzleProgress.objects.filter(
                run_id=self.run_id, team_id=team_id, number__lte=completed
            ).update(
                completed=True, reward_awarded=True,
                completion_route="admin_force",
            )
            TeamRun.objects.filter(
                run_id=self.run_id, team_id=team_id
            ).update(current_number=completed + 1)

        Run.objects.filter(pk=self.run_id).update(
            gameplay_elapsed_ms=5_049_000, advent_clock_anchor=timezone.now()
        )

    async def _screenshot(self, page, name):
        directory = os.environ.get("UI73_SCREENSHOT_DIR")
        if directory:
            root = Path(directory)
            root.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(root / f"{name}.png"), full_page=True)

    def test_reference_state_progress_one_shot_poll_and_reconnect(self):
        self._representative_progress()

        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                context = await browser.new_context(
                    viewport={"width": 1920, "height": 1080}
                )
                page = await context.new_page()
                try:
                    await page.goto(f"{self.live_server_url}/overview/")
                    await page.locator(".public-status--advent").wait_for()
                    self.assertEqual(await page.locator(".advent-progress").count(), 2)
                    for team_id, completed in (("a", 13), ("b", 10)):
                        cabinet = page.locator(
                            f'.advent-progress[data-team-id="{team_id}"]'
                        )
                        self.assertEqual(
                            await cabinet.locator(".advent-door").count(), 25
                        )
                        self.assertEqual(
                            await cabinet.locator(".advent-door--completed").count(),
                            completed,
                        )
                        self.assertEqual(
                            await cabinet.locator(".advent-door--current").count(), 1
                        )
                        self.assertEqual(
                            await cabinet.locator(".advent-door__motif").count(), 25
                        )
                        self.assertEqual(
                            await cabinet.locator(
                                ".advent-door__chocolate[data-motif]"
                            ).count(), 25
                        )
                        self.assertEqual(
                            len(await cabinet.locator(
                                ".advent-door__chocolate"
                            ).evaluate_all(
                                "els => [...new Set(els.slice(0,11)"
                                ".map(e => e.dataset.motif))]"
                            )),
                            11,
                        )
                    self.assertEqual(
                        (await page.locator(".game-clock strong").inner_text())[:5],
                        "01:24",
                    )
                    self.assertEqual(
                        await page.locator("#overview-poller").get_attribute(
                            "hx-trigger"
                        ),
                        "every 500ms [!document.hidden], "
                        "visibilitychange[!document.hidden] from:document",
                    )
                    self.assertLessEqual(
                        await page.evaluate("document.documentElement.scrollWidth"),
                        1921,
                    )
                    self.assertLessEqual(
                        await page.evaluate("document.documentElement.scrollHeight"),
                        1081,
                    )
                    self.assertEqual(
                        await page.locator(
                            '.advent-progress[data-team-id="b"] '
                            '.advent-door--current .advent-door__number'
                        ).evaluate("el => getComputedStyle(el).color"),
                        "rgb(64, 44, 22)",
                    )
                    await page.wait_for_timeout(1100)
                    self.assertEqual(
                        await page.locator(".advent-door-opening-echo").count(), 0
                    )
                    await self._screenshot(page, "tv-v4-advent-a13-b10-1920x1080")
                    await page.set_viewport_size({"width": 1024, "height": 768})
                    self.assertLessEqual(
                        await page.evaluate("document.documentElement.scrollWidth"),
                        1025,
                    )
                    await self._screenshot(page, "tv-v4-advent-a13-b10-1024x768")
                    await page.set_viewport_size({"width": 1920, "height": 1080})
                    await page.evaluate("""() => {
                        window.__issue73Echoes = 0;
                        new MutationObserver(records => {
                            records.forEach(record => {
                                record.addedNodes.forEach(node => {
                                if (node.nodeType === 1 &&
                                    node.classList.contains(
                                        'advent-door-opening-echo')) {
                                    window.__issue73Echoes += 1;
                                }
                                });
                            });
                        }).observe(document.body, {childList: true});
                    }""")
                    await asyncio.to_thread(
                        force_complete_current,
                        self.admin,
                        AdminPuzzle(str(uuid4()), self.run_id, "a", "a-14"),
                    )
                    await page.locator(
                        '.advent-progress[data-team-id="a"][data-completed-count="14"]'
                    ).wait_for(timeout=5000)
                    await page.wait_for_function("() => window.__issue73Echoes === 1")
                    await self._screenshot(page, "tv-v4-opening-a14-b10-1920x1080")
                    await page.wait_for_timeout(1200)
                    self.assertEqual(
                        await page.evaluate("window.__issue73Echoes"), 1
                    )
                    await self._screenshot(page, "tv-v4-advent-a14-b10-1920x1080")
                    await page.reload()
                    await page.wait_for_timeout(1100)
                    self.assertEqual(
                        await page.locator(".advent-door-opening-echo").count(), 0
                    )
                    self.assertEqual(
                        await page.locator(
                            '.advent-progress[data-team-id="a"] '
                            '.advent-door--completed'
                        ).count(), 14
                    )
                    await self._screenshot(page, "tv-v4-reconnect-a14-b10-1920x1080")
                finally:
                    await context.close()
                    await browser.close()

        asyncio.run(check())

    def test_reduced_motion_and_frost_reveal_only_public_boolean(self):
        self._representative_progress()
        TeamRun.objects.filter(run_id=self.run_id, team_id="a").update(
            points=98765, hint_tokens=9, reverse_active=True
        )
        FragmentAward.objects.create(
            run_id=self.run_id, team_id="a",
            puzzle_id="private-73", fragment="PRIVATE-FRAGMENT-73"
        )

        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                context = await browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    reduced_motion="reduce",
                )
                page = await context.new_page()
                try:
                    await page.goto(f"{self.live_server_url}/overview/")
                    a = page.locator('.advent-progress[data-team-id="a"]')
                    self.assertEqual(await a.get_attribute("data-frozen"), "false")
                    await asyncio.to_thread(
                        admin_freeze,
                        self.admin,
                        AdminTeam(str(uuid4()), self.run_id, "a"),
                    )
                    frozen = page.locator(
                        '.advent-progress[data-team-id="a"][data-frozen="true"]'
                    )
                    await frozen.wait_for(timeout=5000)
                    self.assertIn(
                        "Bevroren",
                        await frozen.locator(".advent-freeze-badge").inner_text()
                    )
                    self.assertEqual(
                        await frozen.locator(".advent-door").count(), 25
                    )
                    self.assertEqual(
                        await frozen.locator(".advent-door--completed").count(), 13
                    )
                    html = (await page.locator("#overview-state").inner_html()).lower()
                    for forbidden in (
                        "98765", "private-fragment-73", "reverse_active",
                        "hint_tokens", "freeze_remaining", "freeze_cause",
                    ):
                        self.assertNotIn(forbidden, html)
                    await self._screenshot(page, "tv-v4-frozen-a13-b10-1920x1080")
                    await asyncio.to_thread(
                        admin_unfreeze,
                        self.admin,
                        AdminTeam(str(uuid4()), self.run_id, "a"),
                    )
                    await frozen.wait_for(state="detached", timeout=5000)
                    await asyncio.to_thread(
                        force_complete_current,
                        self.admin,
                        AdminPuzzle(str(uuid4()), self.run_id, "a", "a-14"),
                    )
                    await page.locator(
                        '.advent-progress[data-team-id="a"][data-completed-count="14"]'
                    ).wait_for(timeout=5000)
                    self.assertEqual(
                        await page.locator(".advent-door-opening-echo").count(), 0
                    )
                    self.assertEqual(
                        await page.locator(
                            '.advent-progress[data-team-id="a"] '
                            '.advent-door--completed .advent-door__motif'
                        ).count(), 14
                    )
                    await self._screenshot(
                        page, "tv-v4-reduced-motion-a14-b10-1920x1080"
                    )
                finally:
                    await context.close()
                    await browser.close()

        asyncio.run(check())
