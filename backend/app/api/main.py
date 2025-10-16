from fastapi import APIRouter

from .routes import entries, graph, insights, login, search, timeline, users, utils
from app.core.config import settings

api_router = APIRouter()

@api_router.get("/", tags=["api"])
def api_root():
    return {
        "message": "CLU API v1",
        "available_endpoints": [
            "login",
            "users", 
            "entries",
            "search",
            "timeline",
            "graph",
            "insights",
            "utils"
        ],
        "docs": "/docs"
    }

api_router.include_router(login.router)
api_router.include_router(users.router)
api_router.include_router(utils.router)
api_router.include_router(entries.router)
api_router.include_router(search.router)
api_router.include_router(timeline.router)
api_router.include_router(graph.router)
api_router.include_router(insights.router)

