from fastapi import FastAPI
from app.api.router import api_router
from app.config import get_settings
from contextlib import asynccontextmanager
from app.database import connect_to_database, close_database
from app.core.errors import register_exception_handlers, request_id_middleware
from app.core.logging import configure_logging, log_event

# Load settings once when the module is imported (fails early if a
# required setting such as APP_NAME is missing).
settings = get_settings()
configure_logging("INFO")

# Runs code at application startup and shutdown. Everything before `yield`
# runs on startup; everything after it runs on shutdown.
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Open the shared MongoDB connection once, not on every request.
    await connect_to_database()
    try:
        yield  # The application serves requests while paused here.
    finally:
        # Close the connection on shutdown, even if the app stopped with an error.
        await close_database()

# The FastAPI application. lifespan hooks in the startup/shutdown logic above.
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan
)

# Register the middleware and exception handlers.
app.middleware("http")(request_id_middleware)
register_exception_handlers(app)

# Register all the routes. The individual endpoints live in app/api/routes/
# and are combined in app/api/router.py.
app.include_router(api_router)