"""Router aggregation.

- root_router: public endpoints mounted at "/" (e.g. /health).
- api_router: business endpoints mounted under "/api".
"""

from fastapi import APIRouter

from app.api.routes import health

root_router = APIRouter()
root_router.include_router(health.router)

api_router = APIRouter(prefix="/api")
# Register future business routers here, e.g.:
# api_router.include_router(skills.router, prefix="/skills", tags=["skills"])