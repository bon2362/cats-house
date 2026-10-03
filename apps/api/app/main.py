from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import Settings


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="Cat's House API")
    app.state.settings = settings
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app(Settings())
