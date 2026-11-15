"""Static build of the website for GitHub Pages (only the standard library).

    python scripts/build_pages.py                     # -> dist-pages/
    LH_API_BASE=http://127.0.0.1:8000 python scripts/build_pages.py   # another API server

Writes ``dist-pages/`` with:

- ``es/`` = ``web/site`` and ``en/`` = ``web/site-en``, with ``js/config.js`` pointing at the
  model API on Render (the pages are static; the models run there),
- ``index.html`` at the root, which picks the language in the browser (``?lang=``, then the
  saved choice in ``localStorage['lh_lang']``, then ``navigator.languages``) and redirects,
  keeping the rest of the query string and the hash (``?auto=registro`` for the smoke test),
- the language switch (``?lang=xx`` on the server) turned into a link to the sibling folder,
- ``404.html`` and ``.nojekyll``.

All the site's own paths are relative, so it works under a project subpath such as
``https://pepert03.github.io/latent-health/``.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path

# The only place to edit when the API moves (the GitHub Actions workflow can override it with LH_API_BASE).
API_BASE = "https://latent-health-api.onrender.com"

ROOT = Path(__file__).resolve().parents[1]
SITES = {"es": ROOT / "web" / "site", "en": ROOT / "web" / "site-en"}
OUT = ROOT / "dist-pages"

# The local server's message mentions web\start.ps1; on Pages the usual cause is Render waking up.
OFFLINE = {
    "es": (
        "'El modelo no responde. Comprueba que el servidor local sigue arrancado (web\\\\start.ps1).'",
        "'El modelo no responde. El servidor gratuito se duerme si nadie lo usa: tarda hasta un minuto en "
        "despertar. Vuelve a probar en unos segundos.'",
    ),
    "en": (
        "'The model is not responding. Check that the local server is still running (web\\\\start.ps1).'",
        "'The model is not responding. The free server sleeps when idle and takes up to a minute to wake "
        "up. Try again in a few seconds.'",
    ),
}

# Runs first in every page: a ?lang= for the other language goes to the sibling folder.
LANG_GUARD = """<script>
      (function () {
        var q = new URLSearchParams(location.search), l = q.get('lang')
        if (l !== 'es' && l !== 'en') return
        try { localStorage.setItem('lh_lang', l) } catch (e) {}
        if (l === '__HERE__') return
        q.delete('lang')
        var s = q.toString(), page = location.pathname.split('/').pop()
        location.replace('../' + l + '/' + page + (s ? '?' + s : '') + location.hash)
      })()
    </script>"""

ROOT_INDEX = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>LatentHealth</title>
    <link rel="icon" type="image/svg+xml" href="en/favicon.svg" />
    <link rel="alternate" hreflang="es" href="es/" />
    <link rel="alternate" hreflang="en" href="en/" />
    <link rel="alternate" hreflang="x-default" href="./" />
    <script>
      // Language: ?lang=es|en (and it is remembered), the saved choice, the browser's languages.
      ;(function () {
        var q = new URLSearchParams(location.search), lang = q.get('lang'), saved = null
        try { saved = localStorage.getItem('lh_lang') } catch (e) {}
        if (lang === 'es' || lang === 'en') {
          try { localStorage.setItem('lh_lang', lang) } catch (e) {}
        } else if (saved === 'es' || saved === 'en') {
          lang = saved
        } else {
          var langs = navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language || '']
          lang = String(langs[0] || '').toLowerCase().indexOf('es') === 0 ? 'es' : 'en'
        }
        q.delete('lang')
        var s = q.toString()
        location.replace(lang + '/' + (s ? '?' + s : '') + location.hash)
      })()
    </script>
    <style>
      body { font: 16px/1.5 system-ui, sans-serif; margin: 0; display: grid; place-items: center; min-height: 100vh; background: #f7f5f0; color: #1d1d1b; }
      a { color: inherit; margin: 0 .5em; }
    </style>
  </head>
  <body>
    <p>LatentHealth · <a href="es/" hreflang="es" lang="es" onclick="try{localStorage.setItem('lh_lang','es')}catch(e){}">Español</a>
      <a href="en/" hreflang="en" onclick="try{localStorage.setItem('lh_lang','en')}catch(e){}">English</a></p>
  </body>
</html>
"""

# GitHub Pages serves the root 404.html for any missing path, at any depth: go home in the same language.
NOT_FOUND = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>LatentHealth · 404</title>
    <script>
      ;(function () {
        var p = location.pathname, m = p.match(/^(.*?\\/)(es|en)\\//)
        // Home of the site: up to the language folder, otherwise the first folder (project pages).
        var base = m ? m[1] : (p.match(/^\\/[^/]+\\//) || ['/'])[0]
        location.replace(base + (m ? m[2] + '/' : '') + location.search + location.hash)
      })()
    </script>
  </head>
  <body style="font: 16px/1.5 system-ui, sans-serif; text-align: center; padding: 3rem 1rem">
    <p>Página no encontrada · Page not found</p>
  </body>
</html>
"""


def _switch_links(html: str, other: str, page: str) -> str:
    """``href="?lang=other"`` -> link to the same page in the sibling folder (and remember the choice)."""
    target = "../" + other + "/" + ("" if page == "index.html" else page)
    remember = f"try{{localStorage.setItem('lh_lang','{other}')}}catch(e){{}}"
    return html.replace(f'href="?lang={other}"', f'href="{target}" onclick="{remember}"')


def build(api_base: str = API_BASE, out: Path = OUT) -> Path:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for code, src in SITES.items():
        other = "en" if code == "es" else "es"
        dest = out / code
        shutil.copytree(src, dest)

        config = dest / "js" / "config.js"
        text = config.read_text(encoding="utf-8")
        text, n = re.subn(r"export const API_BASE = '[^']*'", f"export const API_BASE = '{api_base.rstrip('/')}'", text)
        if n != 1:
            sys.exit(f"{config}: API_BASE not found")
        config.write_text(text, encoding="utf-8", newline="\n")

        lib = dest / "js" / "lib.js"
        text = lib.read_text(encoding="utf-8")
        old, new = OFFLINE[code]
        if old not in text:
            sys.exit(f"{lib}: the OFFLINE message changed; update OFFLINE in build_pages.py")
        lib.write_text(text.replace(old, new), encoding="utf-8", newline="\n")

        for page in dest.glob("*.html"):
            html = page.read_text(encoding="utf-8")
            html = _switch_links(html, other, page.name)
            if 'href="?lang=' in html:
                sys.exit(f"{page}: language link not rewritten")
            charset = '<meta charset="utf-8" />'
            if charset not in html:
                sys.exit(f"{page}: no {charset}")
            html = html.replace(charset, charset + "\n    " + LANG_GUARD.replace("__HERE__", code), 1)
            page.write_text(html, encoding="utf-8", newline="\n")

    (out / "index.html").write_text(ROOT_INDEX, encoding="utf-8", newline="\n")
    (out / "404.html").write_text(NOT_FOUND, encoding="utf-8", newline="\n")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    return out


if __name__ == "__main__":
    base = os.environ.get("LH_API_BASE", "").strip() or API_BASE
    folder = build(base)
    files = sum(1 for p in folder.rglob("*") if p.is_file())
    print(f"{folder} - {files} files - API {base}")
