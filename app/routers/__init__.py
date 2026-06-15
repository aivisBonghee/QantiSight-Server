from app.routers.cases import router as cases_router
from app.routers.search import router as search_router
from app.routers.upload import router as upload_router
from app.routers.analysis import router as analysis_router

__all__ = ["cases_router", "search_router", "upload_router", "analysis_router"]
