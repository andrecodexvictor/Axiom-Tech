"""Stable ASGI import alias: ``uvicorn app.api:app``."""

from app.main import app, create_app

__all__ = ["app", "create_app"]
