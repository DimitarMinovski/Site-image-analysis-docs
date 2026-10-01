"""Health and readiness.

Unauthenticated on purpose: a load balancer must be able to call them.
They expose no site data, only which dependencies are reachable.
"""
from __future__ import annotations

from fastapi import APIRouter, Response, status

from .. import db
from ..config import settings
from ..ports.analyser import get_analyser
from ..ports.storage import get_storage
from ..validation import schemas_loadable

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict:
    """Process is up. Says nothing about dependencies."""
    return {"status": "ok", "service": "site-image-analysis", "version": "0.1.0"}


@router.get("/readyz")
def readyz(response: Response) -> dict:
    checks = {
        "database": db.healthy(),
        "schemas": schemas_loadable(),
        "storage": False,
    }
    storage_desc = "unavailable"
    try:
        s = get_storage()
        storage_desc = s.describe()
        s.exists("readiness-probe")  # exercises the adapter without writing
        checks["storage"] = True
    except Exception:
        pass

    ready = all(checks.values())
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "ready": ready,
        "checks": checks,
        "config": {
            "storage": storage_desc,
            "analyser": get_analyser().describe(),
            "model_provider": settings.model_provider,
            "rubric_version": settings.rubric_version,
        },
    }


@router.get("/stats")
def stats() -> dict:
    """Row counts and per-clause override rates. Cheap operational visibility."""
    with db.conn() as c:
        return {**db.counts(c), "clause_overrides": db.clause_override_rates(c)}


@router.get("/insights")
def insights() -> dict:
    """Correlated findings across the whole corpus, framed for R&D and for the
    customer. Aggregation lives server-side, next to the data, so it is testable
    and the browser is not sent every assessment document."""
    from ..insights import compute

    with db.conn() as c:
        return compute(c)
