"""Captura una URL con Chromium sin ventana (Playwright).

Uso: python shot.py URL SALIDA.png [ancho] [alto] [--full] [--exe=RUTA] [--scale=1]
"""
import sys
import time

from playwright.sync_api import sync_playwright

args = [a for a in sys.argv[1:] if not a.startswith("--")]
flags = {a.split("=")[0]: (a.split("=", 1)[1] if "=" in a else True) for a in sys.argv[1:] if a.startswith("--")}
url, out = args[0], args[1]
w = int(args[2]) if len(args) > 2 else 1600
h = int(args[3]) if len(args) > 3 else 1200
scale = float(flags.get("--scale", 1))

t0 = time.time()
with sync_playwright() as p:
    kw = {"headless": True}
    if "--exe" in flags:
        kw["executable_path"] = flags["--exe"]
    browser = p.chromium.launch(**kw)
    page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=scale)
    page.goto(url, wait_until="networkidle")
    page.wait_for_timeout(int(flags.get("--wait", 300)))
    if "--clip" in flags:
        x, y, cw, ch = (float(v) for v in flags["--clip"].split(","))
        page.screenshot(path=out, clip={"x": x, "y": y, "width": cw, "height": ch})
    else:
        page.screenshot(path=out, full_page=bool(flags.get("--full")))
    browser.close()
print(f"ok {out} {time.time() - t0:.1f}s")
