from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.api.router import api_router
from app.auth.throttle import LoginThrottle
from app.core.config import Settings
from app.db.session import create_session_factory
from app.media.service import S3MediaStorage


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="Cat's House API")
    app.state.settings = settings
    app.state.session_factory = create_session_factory(settings.database_url)
    app.state.media_storage = S3MediaStorage(settings)
    app.state.login_throttle = LoginThrottle()
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret.get_secret_value(),
        https_only=settings.session_cookie_secure,
        same_site="lax",
    )
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app(Settings())
