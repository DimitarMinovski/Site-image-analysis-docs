"""FastAPI application.

Bound to loopback by default. Every mutating route requires a bearer token:
an endpoint that accepts files and writes them to storage is a hole even in a
prototype, and auth is much harder to add once people are using it.
"""
from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routes import assessments, health, images

app = FastAPI(
    title="Site Image Analysis",
    version="0.1.0",
    description="Walking skeleton for the CAB-FREE-SPACE use case. Stub analyser.",
)

# The EUI app is served from :3000 and this API from :8000, so the browser
# treats them as different origins and blocks requests without this.
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


def require_token(authorization: str | None = Header(default=None)) -> None:
    """Interim auth. Replace with the real identity provider before any
    deployment that is reachable by more than one person."""
    expected = f"Bearer {settings.api_token}"
    if authorization != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


app.include_router(health.router, tags=["health"])
app.include_router(images.router, tags=["images"], dependencies=[Depends(require_token)])
app.include_router(assessments.router, tags=["assessments"], dependencies=[Depends(require_token)])
