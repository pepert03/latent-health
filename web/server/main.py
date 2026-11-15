"""Local server for the LatentHealth site.

One process and one port: the ``/api/...`` routes call the real models in
``src/latenthealth`` (which are not modified) and everything else serves the site (``web/site``).

Start it (from the repository root)::

    powershell -ExecutionPolicy Bypass -File web\\start.ps1

Interactive route documentation is at ``/api/docs``.
"""

from __future__ import annotations

import logging
import mimetypes
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from latenthealth.i18n import LANG, lang_from_headers

from .routes import chat, home, model

WEB_DIR = Path(__file__).resolve().parents[1]
DIST_DIR = WEB_DIR / "site"  # the site: HTML, CSS and JavaScript with no build step
log = logging.getLogger("latenthealth.web")

# On some Windows machines the registry maps .js to text/plain and the browser rejects the modules.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("font/woff2", ".woff2")

_models_ready = threading.Event()


def _warm_up() -> None:
    """Loads the models in the background so the first demo request does not wait."""
    for module in (home, model):
        try:
            module.warm_up()
        except Exception:  # the web app must start even if a model fails to warm up
            log.exception("Could not warm up %s", module.__name__)
    _models_ready.set()


@asynccontextmanager
async def lifespan(_: FastAPI):
    threading.Thread(target=_warm_up, name="warm-up-models", daemon=True).start()
    yield


app = FastAPI(
    title="LatentHealth · local site server",
    description="Synthetic data. Decision-support prototype; it does not diagnose.",
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)


class LanguageMiddleware:
    """Sets the response language for the request: header `X-Lang` (es|en), else `Accept-Language`.

    Pure ASGI so the context variable reaches the route handlers (also the sync ones,
    which run in a thread pool with a copy of this context).
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        code = lang_from_headers(headers.get("x-lang"), headers.get("accept-language"))
        token = LANG.set(code)

        async def send_with_lang(message):
            if message["type"] == "http.response.start":
                extra = [(b"content-language", code.encode()), (b"vary", b"X-Lang, Accept-Language")]
                message = {**message, "headers": [*message.get("headers", []), *extra]}
            await send(message)

        try:
            await self.app(scope, receive, send_with_lang)
        finally:
            LANG.reset(token)


app.add_middleware(LanguageMiddleware)


class Health(BaseModel):
    status: str
    models_ready: bool
    site_built: bool


@app.get("/api/health", tags=["Status"])
def health() -> Health:
    """Liveness check: the web app uses it to know whether the model is available."""
    return Health(
        status="ok",
        models_ready=_models_ready.is_set(),
        site_built=(DIST_DIR / "index.html").is_file(),
    )


app.include_router(home.router)
app.include_router(chat.router)
app.include_router(model.router)


class SPAStaticFiles(StaticFiles):
    """Site files; any path that is not a file returns index.html."""

    async def get_response(self, path: str, scope):
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            parts = path.replace("\\", "/").split("/")  # on Windows the path arrives with "\"
            if exc.status_code == 404 and parts[0] != "api" and "." not in parts[-1]:
                response = await super().get_response("index.html", scope)
            else:
                raise
        # The site changes often during the demo: make the browser always check for a new version
        # (with ETag the response is a 304 and nothing is downloaded again).
        response.headers["Cache-Control"] = "no-cache"
        return response


class BilingualSite:
    """Serves the Spanish site (``web/site``) or the English one (``web/site-en``).

    Choice, in order: ``?lang=es|en`` (and it is remembered in a cookie), the ``lh_lang`` cookie,
    and otherwise the browser's ``Accept-Language`` (Spanish for ``es*``, English for everyone else).
    """

    COOKIE = "lh_lang"

    def __init__(self, sites: dict[str, SPAStaticFiles]):
        self.sites = sites

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.sites["en"](scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        query = dict(p.split("=", 1) for p in scope.get("query_string", b"").decode("latin-1").split("&") if "=" in p)
        cookies = dict(
            c.strip().split("=", 1) for c in headers.get("cookie", "").split(";") if "=" in c
        )
        chosen = query.get("lang") if query.get("lang") in self.sites else None
        code = chosen or (cookies.get(self.COOKIE) if cookies.get(self.COOKIE) in self.sites else None)
        code = code or lang_from_headers(None, headers.get("accept-language"))
        if code not in self.sites:
            code = "en"

        async def send_with_cookie(message):
            if message["type"] == "http.response.start":
                extra = [(b"vary", b"Cookie, Accept-Language"), (b"content-language", code.encode())]
                if chosen:
                    cookie = f"{self.COOKIE}={chosen}; Path=/; Max-Age=31536000; SameSite=Lax"
                    extra.append((b"set-cookie", cookie.encode()))
                message = {**message, "headers": [*message.get("headers", []), *extra]}
            await send(message)

        await self.sites[code](scope, receive, send_with_cookie)


# Always last: the site takes everything that is not /api.
_sites = {
    code: SPAStaticFiles(directory=folder, html=True)
    for code, folder in (("es", DIST_DIR), ("en", WEB_DIR / "site-en"))
    if folder.is_dir()
}
if _sites:
    app.mount("/", BilingualSite(_sites), name="web")
