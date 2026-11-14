"""Aggregates all v1 route modules (one router per resource)."""

from fastapi import APIRouter

from app.api.v1 import auth, connections, conversations, datasets, health, history, reports

api_router = APIRouter()
for module in (health, auth, datasets, connections, conversations, history, reports):
    api_router.include_router(module.router)
