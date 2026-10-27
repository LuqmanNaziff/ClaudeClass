from fastapi import FastAPI
from app.api.router import api_router

app = FastAPI(
    title="Claude AI for Programmers and Automation C2 2026",
    version="0.1.0",
)

app.include_router(api_router)