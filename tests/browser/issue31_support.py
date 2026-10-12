import os
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import Client, LiveServerTestCase, override_settings

from quiz.application import start_game
from quiz.contracts import Actor, StartGame
from quiz.models import AccountRole


class Issue31BrowserCase(LiveServerTestCase):
    def setUp(self):
        if not os.environ.get("TEST_DATABASE_PATH"):
            self.skipTest("requires disposable file-backed TEST_DATABASE_PATH")
        self.snapshots = TemporaryDirectory()
        self.addCleanup(self.snapshots.cleanup)
        scope = override_settings(QUIZ_SNAPSHOT_ROOT=Path(self.snapshots.name))
        scope.enable()
        self.addCleanup(scope.disable)

        users = get_user_model()
        admin_user = users.objects.create_user("issue31-browser-admin")
        a_user = users.objects.create_user("issue31-browser-a")
        b_user = users.objects.create_user("issue31-browser-b")
        AccountRole.objects.create(user=admin_user, role="admin")
        AccountRole.objects.create(user=a_user, role="team", team_id="a")
        AccountRole.objects.create(user=b_user, role="team", team_id="b")
        self.admin = Actor(admin_user.pk, "admin")
        self.run_id = start_game(
            self.admin, StartGame(str(uuid4()), "christmas-2026-demo")
        ).run_id
        self.a_cookie = self._session_cookie(a_user)
        self.b_cookie = self._session_cookie(b_user)

    def _session_cookie(self, user):
        client = Client()
        client.force_login(user)
        return client.cookies["sessionid"].value

    async def page_for(self, playwright, cookie):
        # CI exercises the same purchase transition in Chromium and WebKit.
        engine = os.environ.get("ISSUE31_BROWSER_ENGINE", "chromium")
        if engine not in {"chromium", "webkit"}:
            raise ValueError("ISSUE31_BROWSER_ENGINE must be chromium or webkit")
        browser = await getattr(playwright, engine).launch()
        context = (
            await browser.new_context(viewport={"width": 390, "height": 844})
            if engine == "webkit"
            else await browser.new_context()
        )
        host = urlparse(self.live_server_url).hostname
        await context.add_cookies(
            [{"name": "sessionid", "value": cookie, "domain": host, "path": "/"}]
        )
        page = await context.new_page()
        await page.goto(f"{self.live_server_url}/team/")
        return browser, context, page
