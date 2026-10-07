from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.api.router import api_router
from app.auth.throttle import LoginThrottle
from app.core.config import Settings
from app.db.session import create_session_factory
from app.web.limits import add_rate_limit
from app.web.protection import add_security_headers
from app.web.site import mount_site


def create_app(settings: Settings) -> FastAPI:
    # In public mode the API description (/docs, /openapi.json) is not published.
    hidden = {"docs_url": None, "redoc_url": None, "openapi_url": None} if settings.public_mode else {}
    app = FastAPI(title="Cat's House API", **hidden)
    app.state.settings = settings
    app.state.session_factory = create_session_factory(settings.database_url)
    app.state.login_throttle = LoginThrottle()
    add_rate_limit(app)  # inside the session middleware: it needs to see the owner's session
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret.get_secret_value(),
        https_only=settings.session_cookie_secure,
        same_site="lax",
    )
    app.include_router(api_router, prefix="/api/v1")
    add_security_headers(app)
    if settings.web_dist is not None:
        mount_site(app, settings.web_dist)
    return app


app = create_app(Settings())
