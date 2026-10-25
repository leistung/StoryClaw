"""Stable ASGI entrypoint. Composition lives in app.gateway.app."""
from app.gateway.app import app, lifespan

__all__ = ["app", "lifespan"]
