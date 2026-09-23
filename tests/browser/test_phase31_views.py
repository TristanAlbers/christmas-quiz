"""Browser acceptance for phase 3.1 package selection and no-run READY views.

Run with TEST_DATABASE_PATH set, as documented in tests/browser/README.md.
"""

import asyncio
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse

from django.contrib.auth import get_user_model
from django.test import Client, LiveServerTestCase, override_settings

from quiz.models import AccountRole


class Phase31BrowserTests(LiveServerTestCase):
    """Exercise the administrator selection flow and the team's blank READY UI."""

    def setUp(self):
        if not os.environ.get("TEST_DATABASE_PATH"):
            self.skipTest("requires disposable file-backed TEST_DATABASE_PATH")
        self.snapshots = TemporaryDirectory()
        self.addCleanup(self.snapshots.cleanup)
        scope = override_settings(QUIZ_SNAPSHOT_ROOT=Path(self.snapshots.name))
        scope.enable()
        self.addCleanup(scope.disable)
        users = get_user_model()
        self.admin_user = users.objects.create_user("phase31-browser-admin")
        self.team_user = users.objects.create_user("phase31-browser-a")
        AccountRole.objects.create(user=self.admin_user, role="admin")
        AccountRole.objects.create(user=self.team_user, role="team", team_id="a")

        admin_client = Client()
        admin_client.force_login(self.admin_user)
        self.admin_session_cookie = admin_client.cookies["sessionid"].value
        team_client = Client()
        team_client.force_login(self.team_user)
        self.team_session_cookie = team_client.cookies["sessionid"].value

    async def _page_for(self, playwright, path, session_cookie):
        browser = await playwright.chromium.launch()
        context = await browser.new_context()
        host = urlparse(self.live_server_url).hostname
        await context.add_cookies(
            [
                {
                    "name": "sessionid",
                    "value": session_cookie,
                    "domain": host,
                    "path": "/",
                }
            ]
        )
        page = await context.new_page()
        await page.goto(f"{self.live_server_url}{path}")
        return browser, context, page

    def test_admin_selects_a_package_then_reset_returns_team_to_waiting_ready(self):
        async def check():
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                admin_browser, admin_context, admin_page = await self._page_for(
                    playwright, "/admin-game/", self.admin_session_cookie
                )
                team_browser, team_context, team_page = await self._page_for(
                    playwright, "/team/", self.team_session_cookie
                )
                try:
                    await team_page.get_by_text(
                        "Waiting for an administrator", exact=False
                    ).wait_for()
                    package_select = admin_page.locator("select[name='package_id']")
                    await package_select.wait_for()
                    await package_select.select_option("christmas-2026-demo")
                    await admin_page.get_by_role("button", name="Start game").click()
                    await admin_page.get_by_text("ADVENT_QUIZ", exact=True).wait_for(
                        timeout=5000
                    )
                    await team_page.get_by_text("Demo A1", exact=False).wait_for(
                        timeout=5000
                    )

                    async def accept_reset(dialog):
                        await dialog.accept()

                    admin_page.once("dialog", accept_reset)
                    await admin_page.get_by_role(
                        "button", name="Reset full game"
                    ).click()
                    await admin_page.get_by_text("READY", exact=True).wait_for(
                        timeout=5000
                    )
                    await team_page.get_by_text(
                        "Waiting for an administrator", exact=False
                    ).wait_for(timeout=5000)
                    self.assertEqual(
                        await team_page.locator("#answer-input").count(), 0
                    )
                    self.assertNotIn(
                        "Demo A1", await team_page.locator("#live-game").inner_text()
                    )
                finally:
                    await team_context.close()
                    await team_browser.close()
                    await admin_context.close()
                    await admin_browser.close()

        asyncio.run(check())
