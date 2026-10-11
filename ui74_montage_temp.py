import asyncio
import base64
from pathlib import Path

from playwright.async_api import async_playwright


async def main():
    root = Path("/output")
    output = root / "fidelity-after"
    def image_data(name):
        return "data:image/png;base64," + base64.b64encode((root / name).read_bytes()).decode()

    markup = """<!doctype html><meta charset='utf-8'><style>
    body{margin:0;background:#12221f;color:#f6e6c3;font:16px system-ui;padding:24px}
    h1{font:28px Georgia,serif;margin:0 0 18px}.row{display:flex;gap:24px;align-items:start;margin-bottom:28px}
    figure{margin:0}figcaption{margin:0 0 8px;font-weight:700}.shot{display:block;object-fit:cover;object-position:top;border:1px solid #8d7650}
    .w390{width:390px;height:844px}.w320{width:320px;height:720px}
    </style><h1>Issue #74 · V4 reference fidelity diagnosis</h1>
    <div class='row'><figure><figcaption>Before · 390 × 844</figcaption><img class='shot w390' src='BEFORE390'></figure><figure><figcaption>Approved V4 · 390 × 844</figcaption><img class='shot w390' src='REF390'></figure><figure><figcaption>After · 390 × 844</figcaption><img class='shot w390' src='AFTER390'></figure></div>
    <div class='row'><figure><figcaption>Before · 320 × 720</figcaption><img class='shot w320' src='BEFORE320'></figure><figure><figcaption>Approved V4 · 320 × 720</figcaption><img class='shot w320' src='REF320'></figure><figure><figcaption>After · 320 × 720</figcaption><img class='shot w320' src='AFTER320'></figure></div>"""
    markup = (markup.replace("BEFORE390", image_data("fidelity-before/before-app-390x844.png"))
              .replace("REF390", image_data("fidelity-before/reference-390x844.png"))
              .replace("AFTER390", image_data("fidelity-after/after-app-390x844.png"))
              .replace("BEFORE320", image_data("fidelity-before/before-app-320x720.png"))
              .replace("REF320", image_data("fidelity-before/reference-320x720.png"))
              .replace("AFTER320", image_data("fidelity-after/after-app-320x720.png")))
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page(viewport={"width": 1280, "height": 2100})
        await page.set_content(markup, wait_until="load")
        await page.screenshot(path=output / "phase3-before-reference-after.png", full_page=True)
        await browser.close()


asyncio.run(main())
