"""Router aggregation.

- root_router: public endpoints mounted at "/" (e.g. /health).
- api_router: business endpoints mounted under "/api".
"""

from fastapi import APIRouter

from app.api.routes import agent, evals, health, llm, skills

root_router = APIRouter()
root_router.include_router(health.router)

api_router = APIRouter(prefix="/api")
api_router.include_router(llm.router)
api_router.include_router(skills.router)
api_router.include_router(agent.router)
api_router.include_router(evals.router)
