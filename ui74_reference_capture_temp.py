import asyncio
from pathlib import Path

from playwright.async_api import async_playwright


async def main():
    output = Path("/output/fidelity-before")
    output.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page(viewport={"width": 1400, "height": 1000})
        await page.goto("file:///reference/quizzmas-midnight-v4.html")
        frame = page.locator(".phone-frame")
        await frame.wait_for()
        await frame.evaluate("el => { el.style.maxWidth = 'none'; el.style.width = '390px'; el.style.height = '844px'; el.scrollTop = 0; }")
        await frame.screenshot(path=output / "reference-390x844.png")
        await frame.evaluate("el => { el.style.width = '320px'; el.style.height = '720px'; el.scrollTop = 0; }")
        await frame.screenshot(path=output / "reference-320x720.png")
        await browser.close()


asyncio.run(main())
