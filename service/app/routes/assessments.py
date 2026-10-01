"""Assessment reads and review submission.

A review is a new row, never a mutation of the assessment. An assessment is a
statement about what the rules said at a point in time; a review is a human act
upon it. Keeping them separate is what makes per-clause override rate - the
signal that tells us which clauses are wrong - computable at all.
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .. import db

router = APIRouter()

VERDICTS = {"adequate", "limited", "critical", "borderline", "abstained"}


class ReviewIn(BaseModel):
    status: Literal["confirmed", "corrected", "rejected"]
    reviewer_id: Optional[str] = None
    corrected_verdict: Optional[str] = None
    note: Optional[str] = None
    # Naming the disputed clause is what turns a disagreement into a measurable
    # defect in a specific rule rather than general dissatisfaction.
    disputed_clause: Optional[str] = Field(
        default=None, description="Clause the reviewer disagrees with, if any"
    )


@router.get("/assessments")
def list_assessments(
    cabinet_id: Optional[str] = None,
    verdict: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    if verdict and verdict not in VERDICTS:
        raise HTTPException(400, f"verdict must be one of {sorted(VERDICTS)}")
    with db.conn() as c:
        rows = db.list_assessments(c, cabinet_id=cabinet_id, verdict=verdict,
                                   limit=limit, offset=offset)
    return {
        "count": len(rows),
        "items": [
            {
                "id": r["id"],
                "image_sha256": r["sha256"],
                "site_id": r["site_id"],
                "cabinet_id": r["cabinet_id"],
                "cabinet_type": r["cabinet_type"],
                "verdict": r["verdict"],
                "verdict_rule": r["verdict_rule"],
                "usable_free_u": r["usable_free_u"],
                "confidence": r["confidence"],
                "rubric_version": r["rubric_version"],
                "review_status": r["review_status"],
                "review_required": (r["doc"].get("review") or {}).get("required", False),
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ],
    }


@router.get("/assessments/{aid}")
def get_assessment(aid: int) -> dict:
    with db.conn() as c:
        row = db.get_assessment(c, aid)
        if not row:
            raise HTTPException(404, "unknown assessment")
        reviews = db.reviews_for(c, aid)
    return {
        "id": row["id"],
        "image_sha256": row["sha256"],
        "site_id": row["site_id"],
        "cabinet_id": row["cabinet_id"],
        "cabinet_type": row["cabinet_type"],
        "rubric": {"id": row["rubric_id"], "version": row["rubric_version"]},
        "versions": {
            "policy_engine": row["policy_engine_version"],
            "perception": row["perception_version"],
            "model_provider": row["model_provider"],
            "model_id": row["model_id"],
        },
        "assessment": row["doc"],
        "representation": row["representation_doc"],
        "reviews": [
            {
                "status": r["status"],
                "reviewer_id": r["reviewer_id"],
                "corrected_verdict": r["corrected_verdict"],
                "disputed_clause": r["disputed_clause"],
                "note": r["note"],
                "reviewed_at": r["reviewed_at"].isoformat(),
            }
            for r in reviews
        ],
        "created_at": row["created_at"].isoformat(),
    }


@router.post("/assessments/{aid}/review", status_code=201)
def submit_review(aid: int, body: ReviewIn) -> dict:
    if body.status == "corrected" and not body.corrected_verdict:
        raise HTTPException(400, "corrected_verdict is required when status is 'corrected'")
    if body.corrected_verdict and body.corrected_verdict not in VERDICTS:
        raise HTTPException(400, f"corrected_verdict must be one of {sorted(VERDICTS)}")

    with db.conn() as c:
        if not db.get_assessment(c, aid):
            raise HTTPException(404, "unknown assessment")
        row = db.insert_review(
            c, aid, body.status, body.reviewer_id,
            body.corrected_verdict, body.note, body.disputed_clause,
        )
    return {
        "id": row["id"],
        "assessment_id": aid,
        "status": row["status"],
        "disputed_clause": row["disputed_clause"],
        "reviewed_at": row["reviewed_at"].isoformat(),
    }
