import asyncio
import json
import os
import shutil
import struct
import zlib
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, LiveServerTestCase, override_settings

from quiz.application import start_game
from quiz.contracts import Actor, StartGame
from quiz.models import AccountRole, FragmentAward, TeamRun


class CaptureIssue74ReferenceScenario(LiveServerTestCase):
    @staticmethod
    def _landscape_png(width=640, height=220):
        rows = []
        for y in range(height):
            row = bytearray()
            for x in range(width):
                sky = y < height * 0.65
                if sky:
                    rgb = (62 + x * 25 // width, 91 + y * 25 // height, 82 + y * 15 // height)
                else:
                    rgb = (224 - y * 20 // height, 215 - y * 10 // height, 190 - y * 8 // height)
                row.extend(rgb)
            rows.append(b"\x00" + bytes(row))

        def chunk(name, data):
            payload = name + data
            return struct.pack(">I", len(data)) + payload + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)

        return (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
            + chunk(b"IEND", b"")
        )

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        package = root / "games" / "christmas-2026-demo"
        shutil.copytree(settings.BASE_DIR / "games" / "christmas-2026-demo", package)
        (package / "a" / "landscape-clue.svg").write_text('''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 110"><rect width="320" height="110" fill="#889389"/><path d="M0 85L36 74L72 82L103 65L154 83L195 70L241 84L274 64L320 77V110H0Z" fill="#b6b5a0"/><path d="M0 100Q90 80 160 95T320 92V110H0Z" fill="#e7dfc9"/><path d="M91 82V49L120 33L151 49V82Z" fill="#593f39"/><path d="M91 49L120 28L151 49Z" fill="#684539"/><path d="M114 80V60H126V80M99 55H109V65H99M134 55H144V65H134" fill="#e8c47c"/><path d="M224 88L224 26M203 57L224 13L247 57M199 69L224 33L250 69M196 81L224 48L253 81" fill="#174639" stroke="#244735" stroke-width="2"/><path d="M224 17L226 22L232 23L227 27L228 33L223 30L218 32L219 26L214 23L220 22Z" fill="#f7d686"/></svg>''')
        (package / "a" / "clue.wav").write_bytes((settings.BASE_DIR / "quiz" / "static" / "quiz" / "sound-check.wav").read_bytes())
        config_file = package / "game.json"
        config = json.loads(config_file.read_text())
        first = config["teams"]["a"]["puzzles"][13]
        first["title"] = "Het verloren kerstlied"
        first["body"] = "In het oude kerstarchief ontbreekt één woord. Onderzoek de aanwijzing en ontdek wat er is verdwenen."
        first["hint"] = "Het ontbrekende woord begint met een K."
        first["media"] = [
            {"type": "image", "path": "a/landscape-clue.svg", "alt": "Winterdorp met kerk en kerstboom"},
            {"type": "audio", "path": "a/clue.wav"},
        ]
        config_file.write_text(json.dumps(config))
        scope = override_settings(QUIZ_GAMES_ROOT=root / "games", QUIZ_SNAPSHOT_ROOT=root / "snapshots")
        scope.enable()
        self.addCleanup(scope.disable)
        users = get_user_model()
        admin = users.objects.create_user("capture-admin")
        team = users.objects.create_user("capture-team")
        AccountRole.objects.create(user=admin, role="admin")
        AccountRole.objects.create(user=team, role="team", team_id="a")
        run_id = start_game(Actor(admin.pk, "admin"), StartGame(str(uuid4()), "christmas-2026-demo")).run_id
        TeamRun.objects.filter(run_id=run_id, team_id="a").update(current_number=14, points=8, hint_tokens=2, reverse_active=True)
        FragmentAward.objects.create(run_id=run_id, team_id="a", puzzle_id="a-14", fragment="C")
        FragmentAward.objects.create(run_id=run_id, team_id="a", puzzle_id="a-15", fragment="A")
        client = Client()
        client.force_login(team)
        self.cookie = client.cookies["sessionid"].value
        self.output = Path(os.environ["UI74_SCREENSHOT_DIR"])
        self.capture_label = os.environ.get("UI74_CAPTURE_LABEL", "before")
        self.output.mkdir(parents=True, exist_ok=True)

    async def _page(self, browser, width, height):
        context = await browser.new_context(viewport={"width": width, "height": height})
        context_host = urlparse(self.live_server_url).hostname
        await context.add_cookies([{"name": "sessionid", "value": self.cookie, "domain": context_host, "path": "/"}])
        page = await context.new_page()
        response = await page.goto(f"{self.live_server_url}/team/")
        self.assertEqual(response.status, 200)
        await page.locator(".team-advent-panel").wait_for(state="attached", timeout=5000)
        image = page.locator("img.puzzle-image")
        self.assertEqual(await image.count(), 1)
        self.assertGreater(await image.evaluate("el => el.naturalWidth"), 0)
        audio = page.locator("audio.puzzle-audio")
        self.assertEqual(await audio.count(), 1)
        self.assertEqual(await audio.get_attribute("preload"), "metadata")
        hint = page.locator("[data-hint-action]")
        self.assertTrue(await hint.is_enabled())
        self.assertEqual(await hint.get_attribute("data-hint-legal"), "1")
        return context, page

    def test_capture(self):
        async def capture():
            from playwright.async_api import async_playwright
            import json as json_module
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                for width, height in ((390, 844), (320, 720), (390, 420)):
                    context, page = await self._page(browser, width, height)
                    try:
                        if height == 420:
                            answer = page.locator("#answer-input")
                            await answer.scroll_into_view_if_needed()
                            await answer.focus()
                            await answer.fill("kerst")
                        await page.screenshot(path=self.output / f"{self.capture_label}-app-{width}x{height}.png", full_page=False)
                        if (width, height) == (390, 844):
                            report = await page.evaluate("""() => {
                              const rgb = value => (value.match(/[\\d.]+/g) || []).slice(0, 3).map(Number);
                              const luminance = value => {
                                const values = rgb(value).map(part => {
                                  const channel = part / 255;
                                  return channel <= .04045 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4;
                                });
                                return .2126 * values[0] + .7152 * values[1] + .0722 * values[2];
                              };
                              const sample = selector => {
                                const node = document.querySelector(selector);
                                const style = getComputedStyle(node);
                                const foreground = style.color;
                                const background = style.backgroundColor;
                                const light = luminance(foreground), dark = luminance(background);
                                return {selector, foreground, background, contrast: (Math.max(light, dark) + .05) / (Math.min(light, dark) + .05)};
                              };
                              const box = selector => {
                                const rect = document.querySelector(selector).getBoundingClientRect();
                                return {selector, x: rect.x, y: rect.y, width: rect.width, height: rect.height, bottom: rect.bottom};
                              };
                              return {
                                viewport: {width: innerWidth, height: innerHeight, scrollWidth: document.documentElement.scrollWidth},
                                contrast: [sample('#answer-input'), sample('.answer-form .button-primary'), sample('.puzzle-action-button--hint')],
                                boxes: [box('.team-resource-bar'), box('.team-advent-sheet'), box('.answer-form'), box('.puzzle-action-stack')]
                              };
                            }""")
                            (self.output / "visual-measurements-390.json").write_text(json_module.dumps(report, indent=2))
                    finally:
                        await context.close()
                await browser.close()
        asyncio.run(capture())
