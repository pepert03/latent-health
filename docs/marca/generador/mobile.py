import sys
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 375, "height": 812}, device_scale_factor=1)
    pg.goto("http://127.0.0.1:8000/logos.html", wait_until="networkidle")
    pg.wait_for_timeout(500)
    print("scrollWidth", pg.evaluate("document.documentElement.scrollWidth"), "height", pg.evaluate("document.documentElement.scrollHeight"))
    pg.screenshot(path="shots/mobile.png", clip={"x": 0, "y": 0, "width": 375, "height": 1700}, full_page=True)
    pg2 = b.new_page(viewport={"width": 1100, "height": 900}, device_scale_factor=1)
    pg2.goto("http://127.0.0.1:8000/logos.html", wait_until="networkidle")
    pg2.wait_for_timeout(500)
    print("1100 scrollWidth", pg2.evaluate("document.documentElement.scrollWidth"))
    pg2.screenshot(path="shots/medium.png", clip={"x": 0, "y": 0, "width": 1100, "height": 900}, full_page=True)
    b.close()
