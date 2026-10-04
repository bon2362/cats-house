from fastapi import APIRouter

from app.api.routes import auth, health, imports, people

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(health.router)
api_router.include_router(imports.router)
api_router.include_router(people.router)
