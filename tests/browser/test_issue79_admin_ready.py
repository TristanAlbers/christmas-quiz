"""Real Django/Chromium acceptance for Game Master READY (#79)."""

import asyncio
import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, LiveServerTestCase, override_settings

from quiz.application import reset_game
from quiz.contracts import Actor, RunCommand
from quiz.models import AccountRole, Run, StartReceipt


class GameMasterReadyBrowserTests(LiveServerTestCase):
    def setUp(self):
        if not os.environ.get("TEST_DATABASE_PATH"):
            self.skipTest("requires disposable file-backed TEST_DATABASE_PATH")

        fixture = settings.QUIZ_GAMES_ROOT / "christmas-2026-demo"
        self.root = TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        root = Path(self.root.name)
        self.games = root / "games"
        self.games.mkdir()
        shutil.copytree(fixture, self.games / "christmas-2026-demo")
        bad = self.games / "broken-package"
        bad.mkdir()
        (bad / "game.json").write_text("{}", encoding="utf-8")
        self.snapshots = root / "snapshots"
        self.snapshots.mkdir()
        scope = override_settings(
            QUIZ_GAMES_ROOT=self.games,
            QUIZ_SNAPSHOT_ROOT=self.snapshots,
        )
        scope.enable()
        self.addCleanup(scope.disable)

        users = get_user_model()
        self.admin_user = users.objects.create_user("ready-admin", password="secret")
        self.team_user = users.objects.create_user("ready-team", password="secret")
        AccountRole.objects.create(user=self.admin_user, role="admin")
        AccountRole.objects.create(user=self.team_user, role="team", team_id="a")
        self.admin = Actor(self.admin_user.pk, "admin")
        client = Client()
        client.force_login(self.admin_user)
        self.admin_cookie = client.cookies["sessionid"].value

    async def _screenshot(self, page, name):
        root = os.environ.get("UI79_SCREENSHOT_DIR")
        if root:
            path = Path(root)
            path.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(path / f"{name}.png"), full_page=True)

    def test_invalid_package_and_admin_only_discovery_does_not_stage_snapshot(self):
        response = self.client.get("/admin-game/")
        self.assertEqual(response.status_code, 302)
        self.client.force_login(self.team_user)
        self.assertEqual(self.client.get("/admin-game/").status_code, 403)
        self.assertEqual(self.client.get("/admin-game/state/").status_code, 403)
        bad_team_start = self.client.post(
            "/admin-game/start/",
            {"package_id": "christmas-2026-demo", "request_id": "not-a-uuid"},
        )
        self.assertEqual(bad_team_start.status_code, 400)
        self.assertNotContains(self.client.get("/team/"), "broken-package")
        self.client.force_login(self.admin_user)
        ready = self.client.get("/admin-game/")
        self.assertContains(ready, "broken-package")
        self.assertContains(ready, "Ongeldig")
        self.assertContains(ready, "christmas-2026-demo")
        self.assertIn(b"disabled", ready.content)
        self.assertEqual(list(self.snapshots.iterdir()), [])
        self.assertEqual(Run.objects.count(), 0)

        rejected = self.client.post(
            "/admin-game/start/",
            {"package_id": "broken-package", "request_id": str(uuid4())},
        )
        self.assertEqual(rejected.status_code, 400)
        self.assertContains(
            rejected,
            "Spel starten is niet gelukt",
            status_code=400,
        )
        self.assertEqual(Run.objects.count(), 0)
        self.assertEqual(StartReceipt.objects.count(), 0)
        self.assertEqual(list(self.snapshots.iterdir()), [])

    def test_native_select_pointer_poll_and_single_start_then_reset(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                try:
                    context = await browser.new_context(
                        viewport={"width": 390, "height": 844},
                        reduced_motion="reduce",
                    )
                    host = urlparse(self.live_server_url).hostname
                    await context.add_cookies([{
                        "name": "sessionid",
                        "value": self.admin_cookie,
                        "domain": host,
                        "path": "/",
                    }])
                    page = await context.new_page()
                    await page.goto(f"{self.live_server_url}/admin-game/")
                    selector = page.get_by_label("Beschikbare spelpakketten")
                    self.assertEqual(await selector.count(), 1)
                    self.assertTrue(
                        await page.locator(
                            "option[value='broken-package']"
                        ).is_disabled()
                    )
                    self.assertEqual(
                        await page.locator("#admin-poller").get_attribute(
                            "hx-trigger"
                        ),
                        "every 500ms [!document.hidden], "
                        "visibilitychange[!document.hidden] from:document",
                    )
                    for width in (320, 390, 768, 1024):
                        await page.set_viewport_size({"width": width, "height": 844})
                        await page.wait_for_timeout(60)
                        self.assertLessEqual(
                            await page.evaluate("document.documentElement.scrollWidth"),
                            width + 1,
                        )
                        await self._screenshot(page, f"admin-ready-{width}")
                    await page.set_viewport_size({"width": 390, "height": 844})
                    await selector.select_option("christmas-2026-demo")
                    await selector.focus()
                    await selector.evaluate("el => window.__readySelect = el")
                    await page.evaluate("""() => {
                        window.__readyPolls = 0;
                        new MutationObserver(records => {
                            if (records.some(r => r.type === 'childList')) {
                                window.__readyPolls++;
                            }
                        }).observe(
                            document.getElementById('admin-state'),
                            {childList: true}
                        );
                    }""")
                    await page.wait_for_function("() => window.__readyPolls >= 2")
                    self.assertTrue(
                        await selector.evaluate(
                            "el => el === window.__readySelect && "
                            "document.activeElement === el"
                        )
                    )
                    self.assertEqual(
                        await selector.input_value(), "christmas-2026-demo"
                    )
                    self.assertNotEqual(
                        await selector.evaluate(
                            "el => getComputedStyle(el).outlineStyle"
                        ),
                        "none",
                    )

                    # A changed invalid-package reason is a read-only update.
                    # It must not replace the still-valid native selection.
                    old_diagnostic_context = await page.locator(
                        "#admin-package-diagnostics .poll-context"
                    ).input_value()
                    await asyncio.to_thread(
                        (self.games / "broken-package" / "game.json").write_text,
                        "{broken",
                        encoding="utf-8",
                    )
                    await page.get_by_text(
                        "game.json is missing, unreadable, or invalid JSON"
                    ).wait_for(timeout=5000)
                    self.assertNotEqual(
                        await page.locator(
                            "#admin-package-diagnostics .poll-context"
                        ).input_value(),
                        old_diagnostic_context,
                    )
                    self.assertTrue(
                        await selector.evaluate(
                            "el => el === window.__readySelect && "
                            "document.activeElement === el"
                        )
                    )
                    self.assertEqual(
                        await selector.input_value(), "christmas-2026-demo"
                    )

                    # Hold native select pointer through real status swaps.
                    bounds = await selector.bounding_box()
                    await page.mouse.move(
                        bounds["x"] + 15, bounds["y"] + bounds["height"] / 2
                    )
                    await page.mouse.down()
                    await page.wait_for_function("() => window.__readyPolls >= 4")
                    self.assertTrue(
                        await selector.evaluate("el => el === window.__readySelect")
                    )
                    await page.mouse.up()
                    self.assertEqual(
                        await selector.input_value(), "christmas-2026-demo"
                    )

                    button = page.get_by_role("button", name="Spel starten")
                    await button.scroll_into_view_if_needed()
                    bounds = await button.bounding_box()
                    await page.mouse.move(bounds["x"] + bounds["width"] / 2,
                                          bounds["y"] + bounds["height"] / 2)
                    await button.evaluate("el => window.__readyStart = el")
                    await page.mouse.down()
                    await page.wait_for_function("() => window.__readyPolls >= 6")
                    self.assertTrue(
                        await button.evaluate("el => el === window.__readyStart")
                    )
                    await page.mouse.up()
                    await page.get_by_role("button", name="Spel pauzeren").wait_for()
                    self.assertEqual(await page.locator("#package-id").count(), 0)
                    await self._screenshot(page, "admin-after-start-390")
                    run_id = await asyncio.to_thread(
                        lambda: str(Run.objects.get(active=True).id)
                    )
                    await asyncio.to_thread(
                        reset_game,
                        self.admin,
                        RunCommand(str(uuid4()), run_id),
                    )
                    await page.reload()
                    await page.get_by_label("Beschikbare spelpakketten").wait_for()
                    self.assertEqual(
                        await page.get_by_label(
                            "Beschikbare spelpakketten"
                        ).input_value(),
                        "",
                    )
                    await self._screenshot(page, "admin-ready-after-reset-390")
                finally:
                    await context.close()
                    await browser.close()

        asyncio.run(check())
        self.assertEqual(Run.objects.count(), 1)
        self.assertEqual(StartReceipt.objects.count(), 1)
        run = Run.objects.get()
        self.assertFalse(run.active)
        self.assertEqual(run.package_id, "christmas-2026-demo")
        self.assertTrue(Path(run.snapshot_path).exists())
