"""Issue #73: real Django/HTMX TV Advent V4, one-shot doors and public privacy."""

import asyncio
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse
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
        self.browser_engine = os.environ.get("ISSUE73_BROWSER_ENGINE", "chromium")
        self.assertIn(self.browser_engine, {"chromium", "webkit"})
        self.manifest = json.loads(
            (Path(__file__).resolve().parents[2] / "quiz/chocolate_manifest.json")
            .read_text()
        )
        self.snapshots = TemporaryDirectory()
        self.addCleanup(self.snapshots.cleanup)
        scope = override_settings(QUIZ_SNAPSHOT_ROOT=Path(self.snapshots.name))
        scope.enable()
        self.addCleanup(scope.disable)

        user = get_user_model().objects.create_user("issue73-tv-admin")
        AccountRole.objects.create(user=user, role="admin")
        self.client.force_login(user)
        self.admin_cookie = self.client.cookies["sessionid"].value
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
                browser = await getattr(playwright, self.browser_engine).launch()
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
                            await cabinet.locator(".advent-door__motif").count(),
                            completed,
                        )
                        self.assertEqual(
                            await cabinet.locator(".advent-door__chocolate").count(),
                            completed,
                        )
                        subjects = await cabinet.locator(
                            ".advent-door__motif image"
                        ).evaluate_all(
                            "els => els.map(e => e.getAttribute('href')"
                            ".split('/').pop().split('.')[0])"
                        )
                        self.assertEqual(subjects, [
                            entry["subject"]
                            for entry in self.manifest["mapping"][:completed]
                        ])
                        self.assertEqual(await cabinet.locator(
                            ".advent-door:not(.advent-door--completed) image"
                        ).count(), 0)
                        self.assertEqual(await cabinet.locator(
                            ".advent-door--completed .advent-door__number"
                        ).count(), 0)
                    self.assertEqual(
                        (await page.locator(".game-clock strong").inner_text())[:5],
                        "01:24",
                    )
                    # The event label must be legible from TV viewing distance.
                    sizes = await page.evaluate("""() => {
                        const event = document.querySelector('.public-advent-event');
                        return [
                            parseFloat(getComputedStyle(event).fontSize),
                            parseFloat(getComputedStyle(event.querySelector('span')).fontSize)
                        ];
                    }""")
                    self.assertGreaterEqual(sizes[0], 26)
                    self.assertGreaterEqual(sizes[1], 22)
                    # Measure the CHOCOLATE against the opening, not merely
                    # the decorative SVG against its chocolate wrapper.
                    self.assertTrue(await page.locator(
                        ".public-status--advent .advent-door--completed"
                    ).evaluate_all("""doors => doors.every(door => {
                        const r = door.querySelector('.advent-door__reveal')
                            .getBoundingClientRect();
                        const c = door.querySelector('.advent-door__chocolate')
                            .getBoundingClientRect();
                        return Math.abs(c.left+c.width/2-r.left-r.width/2) < 1.5 &&
                               Math.abs((c.top-r.top)-(r.bottom-c.bottom)) < 1.5;
                    })"""))

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
                    # The SVG motif and calendar must retain DOM identity
                    # through real 500ms polls, not merely look stable.
                    await page.evaluate("""() => {
                        window.__stableCalendar = document.querySelector(
                            '.advent-progress[data-team-id="a"] .advent-calendar'
                        );
                        window.__stableMotif = window.__stableCalendar.querySelector(
                            '.advent-door__motif'
                        );
                        window.__tvPolls = 0;
                        document.body.addEventListener('htmx:afterRequest', e => {
                            if (e.detail.elt.id === 'overview-poller') {
                                window.__tvPolls += 1;
                            }
                        });
                    }""")
                    await page.wait_for_function(
                        "() => window.__tvPolls >= 3", timeout=5000
                    )
                    self.assertTrue(await page.evaluate("""() => (
                        document.querySelector(
                          '.advent-progress[data-team-id="a"] .advent-calendar'
                        ) === window.__stableCalendar &&
                        document.querySelector(
                          '.advent-progress[data-team-id="a"] .advent-door__motif'
                        ) === window.__stableMotif
                    )"""))
                    self.assertTrue(await page.locator(
                        ".advent-door__motif"
                    ).evaluate_all("""els => els.every(svg => {
                        const c = svg.parentElement.getBoundingClientRect();
                        const b = svg.getBoundingClientRect();
                        return Math.abs(b.x+b.width/2-c.x-c.width/2) < 1 &&
                               Math.abs(b.y+b.height/2-c.y-c.height/2) < 1;
                    })"""))
                    self.assertEqual(
                        await page.locator(
                            ".advent-door--completed .advent-door__hinge"
                        ).count(), 23
                    )
                    self.assertEqual(
                        await page.locator(
                            ".advent-door--completed .advent-door__hinge"
                        ).first.evaluate("el => getComputedStyle(el).display"),
                        "block",
                    )
                    self.assertEqual(
                        await page.locator(
                            ".advent-door--future .advent-door__hinge"
                        ).first.evaluate("el => getComputedStyle(el).display"),
                        "none",
                    )
                    self.assertTrue(await page.locator(
                        ".advent-door--completed"
                    ).first.evaluate("""door =>
                        getComputedStyle(door, '::before').content !== 'none'
                    """))
                    # #103: Advent no longer offers operator audio controls.
                    panel = page.locator("#overview-audio-player")
                    self.assertEqual(await panel.count(), 1)
                    self.assertFalse(await panel.is_visible())
                    self.assertFalse(
                        await page.locator("#music-audio-action").is_visible()
                    )
                    self.assertFalse(
                        await page.locator("#music-audio-volume").is_visible()
                    )
                    await page.evaluate("""() => {
                        window.__issue103Player = document.getElementById(
                            'music-player'
                        );
                    }""")
                    gap = await page.evaluate("""() => {
                        const summary = document.querySelector(
                            '.public-advent-summary'
                        ).getBoundingClientRect();
                        const calendar = document.querySelector(
                            '.public-calendar-grid'
                        ).getBoundingClientRect();
                        return calendar.top - summary.bottom;
                    }""")
                    self.assertGreaterEqual(gap, 0)
                    self.assertLessEqual(gap, 80)
                    await page.wait_for_timeout(1100)
                    self.assertEqual(
                        await page.locator(".advent-door-opening-echo").count(), 0
                    )
                    await self._screenshot(page, "tv-v4-advent-a13-b10-1920x1080")
                    await page.set_viewport_size({"width": 1024, "height": 768})
                    self.assertFalse(await panel.is_visible())
                    self.assertTrue(await page.evaluate("""() =>
                        window.__issue103Player ===
                            document.getElementById('music-player')
                    """))
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
                        }).observe(document.body, {childList: true, subtree: true});
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
                    # The transient animation MUST inherit the same TV
                    # compartment palette as the permanent completed door.
                    await page.locator(
                        ".public-status--advent > .advent-door-opening-echo"
                    ).wait_for(timeout=2000)
                    echo_checks = await page.evaluate("""() => {
                        const echo = document.querySelector(
                            '.public-status--advent > .advent-door-opening-echo'
                        );
                        const source = document.querySelector(
                            '.advent-progress[data-team-id="a"] ' +
                            '.advent-door[data-door-number="14"]'
                        );
                        const echoReveal = echo.querySelector('.advent-door__reveal');
                        const liveReveal = source.querySelector('.advent-door__reveal');
                        const reveal = echoReveal.getBoundingClientRect();
                        const choc = echo.querySelector('.advent-door__chocolate')
                            .getBoundingClientRect();
                        const liveChoc = source.querySelector(
                            '.advent-door__chocolate'
                        ).getBoundingClientRect();
                        return {
                            backgroundMatches: getComputedStyle(echoReveal)
                                .backgroundImage === getComputedStyle(liveReveal)
                                .backgroundImage,
                            chocolateCentered:
                                Math.abs(choc.x+choc.width/2 -
                                         reveal.x-reveal.width/2) < 1.5 &&
                                Math.abs((choc.top-reveal.top) -
                                         (reveal.bottom-choc.bottom)) < 1.5,
                            chocolateSameSize:
                                Math.abs(choc.width-liveChoc.width) < 2 &&
                                               Math.abs(choc.height-liveChoc.height) < 2
                        };
                    }""")
                    self.assertTrue(echo_checks["backgroundMatches"], echo_checks)
                    self.assertTrue(echo_checks["chocolateCentered"], echo_checks)
                    self.assertTrue(echo_checks["chocolateSameSize"], echo_checks)
                    # The clock continues polling while the opening flap animates.
                    # Those polls must not replace the temporary echo or cabinet.
                    await page.evaluate("""() => {
                        window.__openingEcho = document.querySelector(
                            '.public-status--advent > .advent-door-opening-echo'
                        );
                        window.__openingCabinet = document.querySelector(
                            '.advent-progress[data-team-id="a"] .advent-calendar'
                        );
                        window.__openingPolls = 0;
                        document.body.addEventListener('htmx:afterRequest', e => {
                            if (e.detail.elt.id === 'overview-poller') {
                                window.__openingPolls += 1;
                            }
                        });
                    }""")
                    await page.wait_for_function(
                        "() => window.__openingPolls >= 1", timeout=3500
                    )
                    self.assertTrue(await page.evaluate("""() => (
                        document.querySelector(
                            '.public-status--advent > .advent-door-opening-echo'
                        ) === window.__openingEcho &&
                        document.querySelector(
                            '.advent-progress[data-team-id="a"] .advent-calendar'
                        ) === window.__openingCabinet
                    )"""))
                    await self._screenshot(page, "tv-v4-opening-a14-b10-1920x1080")
                    await page.wait_for_timeout(350)
                    await self._screenshot(
                        page, "tv-v4-opening-midframe-a14-b10-1920x1080"
                    )
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
                browser = await getattr(playwright, self.browser_engine).launch()
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

    def test_full_artwork_centres_clear_of_doors_at_overview_sizes(self):
        # Deliberately omit winner history to inspect every earned chocolate
        # beneath the separately tested production final-victory stage.
        PuzzleProgress.objects.filter(run_id=self.run_id).update(
            completed=True, reward_awarded=True, completion_route="admin_force",
        )
        TeamRun.objects.filter(run_id=self.run_id).update(
            current_number=25, activity_state="FINISHED",
        )
        Run.objects.filter(pk=self.run_id).update(global_state="FINISHED")

        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser = await getattr(playwright, self.browser_engine).launch()
                page = await browser.new_page()
                try:
                    await page.goto(f"{self.live_server_url}/overview/")
                    images = await page.locator(
                        ".advent-door__motif image"
                    ).evaluate_all("els => els.map(e => e.getAttribute('href'))")
                    self.assertEqual(len(images), 50)
                    self.assertEqual(len(set(images)), 11)
                    self.assertEqual(images[:25], images[25:])
                    # Exercise the actual locally served image bytes, not just
                    # valid-looking URLs in an unloaded SVG image element.
                    await page.evaluate("""async urls => Promise.all(
                        [...new Set(urls)].map(url => new Promise((resolve, reject) => {
                            const image = new Image();
                            image.onload = () => resolve(image.naturalWidth);
                            image.onerror = () => reject(new Error(url));
                            image.src = url;
                        }))
                    )""", images)
                    self.assertEqual(await page.locator(
                        ".advent-door__number"
                    ).count(), 0)
                    for width, height in (
                        (1024, 768), (1280, 720), (1920, 900),
                        (1920, 1080), (2560, 1440),
                    ):
                        await page.set_viewport_size({"width": width, "height": height})
                        geometry = await page.locator(
                            ".advent-door--completed"
                        ).evaluate_all("""(doors, assets) => doors.map(door => {
                            const svg = door.querySelector('svg');
                            const matrix = svg.getScreenCTM();
                            const subject = svg.querySelector('image')
                                .getAttribute('href').split('/').pop().split('.')[0];
                            const [l,t,r,b] =
                                assets[subject].visible_bounds_alpha_gt_16;
                            const a = new DOMPoint(l,t).matrixTransform(matrix);
                            const z = new DOMPoint(r,b).matrixTransform(matrix);
                            const well = door.querySelector('.advent-door__reveal')
                                .getBoundingClientRect();
                            const edge = getComputedStyle(door, '::before');
                            const edgeRight = door.getBoundingClientRect().left +
                                parseFloat(edge.left) + parseFloat(edge.width) +
                                parseFloat(edge.borderLeftWidth) +
                                parseFloat(edge.borderRightWidth);
                            return {
                                subject, clearance: a.x - edgeRight,
                                centreX: Math.abs((a.x+z.x-well.left-well.right)/2),
                                centreY: Math.abs((a.y+z.y-well.top-well.bottom)/2),
                                inside: a.x >= well.left && z.x <= well.right &&
                                    a.y >= well.top && z.y <= well.bottom,
                                proportional: Math.abs(matrix.a-matrix.d) < .00001
                            };
                        })""", self.manifest["assets"])
                        for shape in geometry:
                            with self.subTest(size=(width, height), shape=shape):
                                self.assertTrue(shape["inside"])
                                self.assertTrue(shape["proportional"])
                                self.assertLess(shape["centreX"], 1)
                                self.assertLess(shape["centreY"], 1)
                                self.assertGreaterEqual(shape["clearance"], 10)
                finally:
                    await browser.close()

        asyncio.run(check())

    def test_game_master_shows_earned_clues_with_accessible_names(self):
        self._representative_progress()

        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser = await getattr(playwright, self.browser_engine).launch()
                context = await browser.new_context()
                await context.add_cookies([{
                    "name": "sessionid", "value": self.admin_cookie,
                    "domain": urlparse(self.live_server_url).hostname, "path": "/",
                }])
                page = await context.new_page()
                try:
                    await page.goto(f"{self.live_server_url}/admin-game/")
                    for width, height in ((1024, 768), (390, 844)):
                        await page.set_viewport_size({"width": width, "height": height})
                        for team_id, count in (("a", 13), ("b", 10)):
                            cabinet = page.locator(
                                f'.gm-admin-team-panel[data-team="{team_id}"] '
                                '.advent-progress'
                            )
                            self.assertEqual(
                                await cabinet.locator(".advent-door").count(), 25
                            )
                            completed = cabinet.locator(".advent-door--completed")
                            self.assertEqual(await completed.count(), count)
                            self.assertTrue(await completed.evaluate_all(
                                """doors => doors.every(door => {
                                    const reveal = door.querySelector(
                                        '.advent-door__reveal');
                                    const image = door.querySelector('svg');
                                    const box = image.getBoundingClientRect();
                                    const flap = door.querySelector(
                                        '.advent-door__flap');
                                    return getComputedStyle(reveal).display
                                        !== 'none' && getComputedStyle(flap).visibility
                                        === 'hidden' &&
                                        box.width > 0 && box.height > 0;
                                })"""
                            ))
                            subjects = await completed.locator(
                                '.advent-door__motif image'
                            ).evaluate_all(
                                "els => els.map(e => e.getAttribute('href')"
                                ".split('/').pop().split('.')[0])"
                            )
                            self.assertEqual(subjects, [
                                entry["subject"]
                                for entry in self.manifest["mapping"][:count]
                            ])
                            self.assertIn(
                                "chocolade: engel",
                                await completed.first.aria_snapshot(),
                            )
                            closed = cabinet.locator(
                                '.advent-door:not(.advent-door--completed)'
                            )
                            self.assertEqual(await closed.locator('image').count(), 0)
                            self.assertEqual(
                                await closed.locator('.advent-door__number').count(),
                                25 - count,
                            )
                            labels = await closed.evaluate_all(
                                "els => els.map(e => e.getAttribute('aria-label'))"
                            )
                            self.assertTrue(all('chocolade' not in x for x in labels))
                finally:
                    await browser.close()

        asyncio.run(check())
