"""Headers that keep the site out of search engines and other sites' frames, plus robots.txt."""

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

ROBOTS_TXT = "User-agent: *\nDisallow: /\n"
SECURITY_HEADERS = {
    "X-Robots-Tag": "noindex, nofollow, noarchive",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "X-Content-Type-Options": "nosniff",
}


def add_security_headers(app: FastAPI) -> None:
    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        return response

    @app.get("/robots.txt", include_in_schema=False)
    def robots() -> PlainTextResponse:
        return PlainTextResponse(ROBOTS_TXT)
