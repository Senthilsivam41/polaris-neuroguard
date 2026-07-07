import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.api.endpoints import router as api_router

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception occurred: %s", str(exc))
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected internal server error occurred."},
    )

@app.get("/health")
def health_check():
    return {"status": "ok"}

app.include_router(api_router, prefix=settings.API_V1_STR)
