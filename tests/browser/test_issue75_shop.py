"""Real Django/HTMX 390x844 first-look acceptance for issue #75."""

import asyncio
import json
import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, LiveServerTestCase, override_settings

from quiz.application import start_game
from quiz.contracts import Actor, StartGame
from quiz.models import AccountRole, TeamRun


class Issue75ShopBrowserTests(LiveServerTestCase):
    def setUp(self):
        if not os.environ.get("TEST_DATABASE_PATH"):
            self.skipTest("requires disposable file-backed TEST_DATABASE_PATH")

        self.alt_prices = self._testMethodName.endswith("alternate_snapshot_prices")
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        package = root / "games" / "christmas-2026-demo"
        shutil.copytree(settings.BASE_DIR / "games" / "christmas-2026-demo", package)
        config_file = package / "game.json"
        config = json.loads(config_file.read_text())
        if self.alt_prices:
            config.update(hint_cost=4, uno_reverse_cost=5, freeze_cost=7)
            config_file.write_text(json.dumps(config))
        self.expected = (
            ["4 punten", "5 punten", "7 punten", "Gratis"]
            if self.alt_prices
            else ["1 punt", "2 punten", "3 punten", "Gratis"]
        )

        scope = override_settings(
            QUIZ_GAMES_ROOT=root / "games",
            QUIZ_SNAPSHOT_ROOT=root / "snapshots",
        )
        scope.enable()
        self.addCleanup(scope.disable)

        users = get_user_model()
        admin = users.objects.create_user("issue75-admin")
        team = users.objects.create_user("issue75-team")
        AccountRole.objects.create(user=admin, role="admin")
        AccountRole.objects.create(user=team, role="team", team_id="a")
        self.run_id = start_game(
            Actor(admin.pk, "admin"),
            StartGame(str(uuid4()), "christmas-2026-demo"),
        ).run_id
        TeamRun.objects.filter(run_id=self.run_id, team_id="a").update(
            points=6 if self.alt_prices else 8,
            reverse_active=not self.alt_prices,
        )
        client = Client()
        client.force_login(team)
        self.session_cookie = client.cookies["sessionid"].value
        screenshot_dir = os.environ.get("UI75_SCREENSHOT_DIR")
        self.screenshot_dir = Path(screenshot_dir) if screenshot_dir else None
        if self.screenshot_dir:
            self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    async def _capture(self):
        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            context = await browser.new_context(
                viewport={"width": 390, "height": 844},
                reduced_motion="reduce",
            )
            try:
                host = urlparse(self.live_server_url).hostname
                await context.add_cookies(
                    [{
                        "name": "sessionid",
                        "value": self.session_cookie,
                        "domain": host,
                        "path": "/",
                    }]
                )
                page = await context.new_page()
                response = await page.goto(f"{self.live_server_url}/team/")
                self.assertEqual(response.status, 200)
                await page.locator(".team-advent-panel").wait_for(timeout=5000)
                await page.get_by_role("button", name="Winkel", exact=False).click()
                dialog = page.locator("#team-shop-dialog")
                await dialog.wait_for(state="visible")
                self.assertTrue(await dialog.evaluate("el => el.open"))
                self.assertEqual(await page.locator(".shop-item").count(), 4)
                prices = await page.locator(".shop-item__price").all_inner_texts()
                self.assertEqual(prices, self.expected)
                # Readable type on a real phone; never squeeze labels into
                # unreadably small text to fit the shop above the fold.
                text_sizes = await page.evaluate(
                    """() => Object.fromEntries(
                        [
                            ['name', '.shop-item__details strong'],
                            ['description', '.shop-item__details small'],
                            ['price', '.shop-item__price'],
                            ['button', '.shop-item__action button'],
                        ].map(([key, selector]) => [
                            key,
                            parseFloat(getComputedStyle(
                                document.querySelector(selector)
                            ).fontSize),
                        ])
                    )"""
                )
                self.assertGreaterEqual(text_sizes["name"], 16)
                self.assertGreaterEqual(text_sizes["description"], 14)
                self.assertGreaterEqual(text_sizes["price"], 15)
                self.assertGreaterEqual(text_sizes["button"], 14)
                self.assertEqual(
                    await page.locator(".shop-dialog__balance strong").inner_text(),
                    "✦ 6 punten" if self.alt_prices else "✦ 8 punten",
                )
                self.assertEqual(
                    await page.locator(
                        ".shop-item--reverse .resource-reverse-card"
                    ).count(),
                    1,
                )
                # At shop size, the white oval and arrows must stay centered
                # inside the red card in both owned and purchasable states.
                self.assertEqual(
                    await page.locator(
                        ".shop-item--reverse .resource-reverse-card__brand, "
                        ".shop-item--reverse .resource-reverse-card__name"
                    ).count(),
                    0,
                )
                card_layout = await page.evaluate(
                    """() => {
                        const card = document.querySelector(
                            '.shop-item--reverse .resource-reverse-card'
                        );
                        const oval = card.querySelector(
                            '.resource-reverse-card__symbol'
                        );
                        const a = card.getBoundingClientRect();
                        const b = oval.getBoundingClientRect();
                        return {
                            centeredX: Math.abs(
                                (a.left + a.right) / 2 - (b.left + b.right) / 2
                            ),
                            centeredY: Math.abs(
                                (a.top + a.bottom) / 2 - (b.top + b.bottom) / 2
                            ),
                            inside: b.left >= a.left && b.right <= a.right
                                && b.top >= a.top && b.bottom <= a.bottom,
                            extraOval: getComputedStyle(card, '::before').display
                        };
                    }"""
                )
                self.assertLessEqual(card_layout["centeredX"], 1)
                self.assertLessEqual(card_layout["centeredY"], 1)
                self.assertTrue(card_layout["inside"])
                self.assertEqual(card_layout["extraOval"], "none")
                if self.alt_prices:
                    self.assertEqual(
                        await page.locator("form.shop-item--reverse").count(), 1
                    )
                    self.assertTrue(
                        await page.get_by_role(
                            "button", name="Uno Reverse kopen (5)"
                        ).is_enabled()
                    )
                    self.assertTrue(
                        await page.locator(
                            ".shop-item--freeze [data-shop-insufficient]"
                        ).is_visible()
                    )
                else:
                    self.assertEqual(
                        await page.locator(
                            ".shop-item--reverse .shop-item__unavailable"
                        ).inner_text(),
                        "Al actief",
                    )
                    self.assertEqual(
                        await page.locator(".shop-item--reverse button").count(), 0
                    )
                self.assertTrue(
                    await page.evaluate(
                        "() => document.documentElement.scrollWidth <= innerWidth"
                    )
                )
                metrics = await dialog.evaluate(
                    """el => {
                        const a = el.getBoundingClientRect();
                        const cards = [...el.querySelectorAll('.shop-item')].map(n => {
                            const r = n.getBoundingClientRect();
                            return {x:r.x,y:r.y,width:r.width,height:r.height};
                        });
                        return {
                            viewport:{width:innerWidth,height:innerHeight},
                            dialog:{x:a.x,y:a.y,width:a.width,height:a.height},
                            cards,
                            maxScrollWidth:document.documentElement.scrollWidth
                        };
                    }"""
                )
                self.assertGreaterEqual(metrics["dialog"]["x"], 0)
                self.assertLessEqual(
                    metrics["dialog"]["x"] + metrics["dialog"]["width"], 390
                )
                # Four actions keep their own bounds and the dialog scrolls
                # vertically rather than compressing fonts or spilling sideways.
                self.assertTrue(
                    await page.evaluate(
                        """() => [...document.querySelectorAll(
                            '.shop-item__details, .shop-item__action'
                        )].every(node => {
                            const child = node.getBoundingClientRect();
                            const parent = node.closest('.shop-item')
                                .getBoundingClientRect();
                            return child.left >= parent.left - 1
                                && child.right <= parent.right + 1;
                        })"""
                    )
                )
                button = page.locator(".shop-item--hint button")
                await button.evaluate("el => { window.__issue75Button = el; }")
                await page.wait_for_timeout(1200)
                self.assertTrue(
                    await button.evaluate("el => el === window.__issue75Button")
                )
                self.assertTrue(await dialog.evaluate("el => el.open"))

                if self.screenshot_dir:
                    label = (
                        "alternate-snapshot"
                        if self.alt_prices
                        else "demo-armed-reverse"
                    )
                    await page.screenshot(
                        path=self.screenshot_dir / f"issue75-{label}-390x844.png",
                        full_page=False,
                    )
                    (self.screenshot_dir / f"issue75-{label}-metrics.json").write_text(
                        json.dumps(metrics, indent=2)
                    )
            finally:
                await context.close()
                await browser.close()

    def test_shop_demo_armed_reverse(self):
        asyncio.run(self._capture())

    def test_shop_alternate_snapshot_prices(self):
        asyncio.run(self._capture())
