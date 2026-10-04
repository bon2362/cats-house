from fastapi import APIRouter

from app.api.routes import admin_genealogy, auth, exports, health, imports, media, people, tree

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(health.router)
api_router.include_router(imports.router)
api_router.include_router(people.router)
api_router.include_router(tree.router)
api_router.include_router(admin_genealogy.router)
api_router.include_router(media.router)
api_router.include_router(exports.router)
