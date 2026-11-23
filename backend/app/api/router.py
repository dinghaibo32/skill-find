"""Router aggregation.

- root_router: public endpoints mounted at "/" (e.g. /health).
- api_router: business endpoints mounted under "/api".
"""

from fastapi import APIRouter

from app.api.routes import health, llm

root_router = APIRouter()
root_router.include_router(health.router)

api_router = APIRouter(prefix="/api")
api_router.include_router(llm.router)
