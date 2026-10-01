"""Database access and migrations.

Deliberately a thin layer over psycopg rather than an ORM. At this stage the
queries are the interesting part - particularly the claim query - and hiding
them behind an ORM would obscure the one piece of concurrency behaviour the
skeleton exists to prove.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

import psycopg
from psycopg.rows import dict_row

from .config import settings

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


@contextmanager
def conn() -> Iterator[psycopg.Connection]:
    with psycopg.connect(settings.database_url, row_factory=dict_row) as c:
        yield c


def migrate() -> list[str]:
    """Apply .sql files in order. Idempotent: every statement is IF NOT EXISTS."""
    applied = []
    with conn() as c:
        c.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        c.commit()
        done = {r["filename"] for r in c.execute("SELECT filename FROM schema_migrations").fetchall()}
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if path.name in done:
                continue
            c.execute(path.read_text())
            c.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (path.name,))
            c.commit()
            applied.append(path.name)
    return applied


def healthy() -> bool:
    try:
        with conn() as c:
            c.execute("SELECT 1")
        return True
    except Exception:
        return False


# --------------------------------------------------------------------- images

def find_image_by_sha(c: psycopg.Connection, sha: str) -> Optional[dict]:
    return c.execute("SELECT * FROM images WHERE sha256 = %s", (sha,)).fetchone()


def insert_image(c: psycopg.Connection, **kw: Any) -> dict:
    return c.execute(
        """INSERT INTO images
             (sha256, storage_key, content_type, byte_size, site_id, cabinet_id,
              cabinet_type, width_px, height_px, captured_at)
           VALUES (%(sha256)s, %(storage_key)s, %(content_type)s, %(byte_size)s,
                   %(site_id)s, %(cabinet_id)s, %(cabinet_type)s,
                   %(width_px)s, %(height_px)s, %(captured_at)s)
           RETURNING *""",
        kw,
    ).fetchone()


# ----------------------------------------------------------------------- jobs

def enqueue(c: psycopg.Connection, image_id: int) -> dict:
    return c.execute(
        "INSERT INTO jobs (image_id, status) VALUES (%s,'queued') RETURNING *",
        (image_id,),
    ).fetchone()


def claim_job(c: psycopg.Connection, worker_id: str) -> Optional[dict]:
    """Atomically take the oldest queued job.

    FOR UPDATE SKIP LOCKED is what makes multiple workers safe from the start:
    each transaction locks a different row instead of contending for the same
    one, and no job is handed out twice.
    """
    row = c.execute(
        """SELECT id FROM jobs
            WHERE status = 'queued'
            ORDER BY created_at
            FOR UPDATE SKIP LOCKED
            LIMIT 1"""
    ).fetchone()
    if row is None:
        return None
    job = c.execute(
        """UPDATE jobs
              SET status='running', attempts = attempts + 1,
                  started_at = now(), worker_id = %s
            WHERE id = %s
        RETURNING *""",
        (worker_id, row["id"]),
    ).fetchone()
    c.commit()
    return job


def finish_job(c: psycopg.Connection, job_id: int) -> None:
    c.execute("UPDATE jobs SET status='done', finished_at=now(), error=NULL WHERE id=%s", (job_id,))
    c.commit()


def fail_job(c: psycopg.Connection, job_id: int, error: str) -> str:
    """Mark failed, or dead once attempts are exhausted. Error text is kept."""
    row = c.execute("SELECT attempts FROM jobs WHERE id=%s", (job_id,)).fetchone()
    status = "dead" if row and row["attempts"] >= settings.max_attempts else "failed"
    c.execute(
        "UPDATE jobs SET status=%s, finished_at=now(), error=%s WHERE id=%s",
        (status, error[:4000], job_id),
    )
    c.commit()
    return status


def requeue_failed(c: psycopg.Connection) -> int:
    cur = c.execute("UPDATE jobs SET status='queued' WHERE status='failed'")
    c.commit()
    return cur.rowcount


def job_for_image(c: psycopg.Connection, image_id: int) -> Optional[dict]:
    return c.execute(
        "SELECT * FROM jobs WHERE image_id=%s ORDER BY created_at DESC LIMIT 1", (image_id,)
    ).fetchone()


# -------------------------------------------------- representations / assessments

def insert_representation(c: psycopg.Connection, image_id: int, doc: dict) -> dict:
    return c.execute(
        """INSERT INTO representations (image_id, schema_version, perception_version, doc)
           VALUES (%s,%s,%s,%s) RETURNING *""",
        (
            image_id,
            doc.get("schema_version", "1.0.0"),
            doc.get("provenance", {}).get("perception_version", settings.perception_version),
            json.dumps(doc),
        ),
    ).fetchone()


def insert_assessment(c: psycopg.Connection, image_id: int,
                      representation_id: Optional[int], doc: dict) -> dict:
    v = doc.get("verdict", {})
    prov = doc.get("provenance", {})
    return c.execute(
        """INSERT INTO assessments
             (image_id, representation_id, rubric_id, rubric_version,
              policy_engine_version, perception_version, model_provider, model_id,
              verdict, verdict_rule, usable_free_u, confidence, doc)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
        (
            image_id,
            representation_id,
            doc.get("rubric", {}).get("id", "CAB-FREE-SPACE"),
            doc.get("rubric", {}).get("version", settings.rubric_version),
            prov.get("policy_engine_version", settings.policy_engine_version),
            prov.get("perception_version"),
            settings.model_provider if settings.model_provider != "none" else None,
            prov.get("vlm_model"),
            v.get("value", "abstained"),
            v.get("rule_id"),
            doc.get("measurements", {}).get("usable_free_u"),
            doc.get("uncertainty", {}).get("confidence"),
            json.dumps(doc),
        ),
    ).fetchone()


def latest_assessment_for_image(c: psycopg.Connection, image_id: int) -> Optional[dict]:
    return c.execute(
        "SELECT * FROM assessments WHERE image_id=%s ORDER BY created_at DESC LIMIT 1",
        (image_id,),
    ).fetchone()


def list_assessments(c: psycopg.Connection, *, cabinet_id: Optional[str] = None,
                     verdict: Optional[str] = None, limit: int = 50,
                     offset: int = 0) -> list[dict]:
    sql = [
        """SELECT a.*, i.sha256, i.site_id, i.cabinet_id, i.cabinet_type,
                  (SELECT r.status FROM reviews r WHERE r.assessment_id = a.id
                    ORDER BY r.reviewed_at DESC LIMIT 1) AS review_status
             FROM assessments a JOIN images i ON i.id = a.image_id"""
    ]
    where, params = [], {}
    if cabinet_id:
        where.append("i.cabinet_id = %(cabinet_id)s")
        params["cabinet_id"] = cabinet_id
    if verdict:
        where.append("a.verdict = %(verdict)s")
        params["verdict"] = verdict
    if where:
        sql.append("WHERE " + " AND ".join(where))
    sql.append("ORDER BY a.created_at DESC LIMIT %(limit)s OFFSET %(offset)s")
    params.update(limit=limit, offset=offset)
    return c.execute("\n".join(sql), params).fetchall()


def get_assessment(c: psycopg.Connection, aid: int) -> Optional[dict]:
    return c.execute(
        """SELECT a.*, i.sha256, i.site_id, i.cabinet_id, i.cabinet_type,
                  r.doc AS representation_doc
             FROM assessments a
             JOIN images i ON i.id = a.image_id
        LEFT JOIN representations r ON r.id = a.representation_id
            WHERE a.id = %s""",
        (aid,),
    ).fetchone()


# --------------------------------------------------------------------- reviews

def insert_review(c: psycopg.Connection, assessment_id: int, status: str,
                  reviewer_id: Optional[str], corrected_verdict: Optional[str],
                  note: Optional[str], disputed_clause: Optional[str]) -> dict:
    row = c.execute(
        """INSERT INTO reviews
             (assessment_id, status, reviewer_id, corrected_verdict, note, disputed_clause)
           VALUES (%s,%s,%s,%s,%s,%s) RETURNING *""",
        (assessment_id, status, reviewer_id, corrected_verdict, note, disputed_clause),
    ).fetchone()
    c.commit()
    return row


def reviews_for(c: psycopg.Connection, assessment_id: int) -> list[dict]:
    return c.execute(
        "SELECT * FROM reviews WHERE assessment_id=%s ORDER BY reviewed_at DESC",
        (assessment_id,),
    ).fetchall()


def clause_override_rates(c: psycopg.Connection) -> list[dict]:
    """Per-clause disagreement rate - the quality signal from step 9.

    Present from the skeleton onwards so the data accumulates from day one
    rather than being retrofitted once somebody asks for it.
    """
    return c.execute(
        """SELECT disputed_clause AS clause, COUNT(*) AS disputes
             FROM reviews
            WHERE disputed_clause IS NOT NULL
         GROUP BY disputed_clause
         ORDER BY disputes DESC"""
    ).fetchall()


def counts(c: psycopg.Connection) -> dict:
    return {
        "images": c.execute("SELECT count(*) AS n FROM images").fetchone()["n"],
        "jobs": {
            r["status"]: r["n"]
            for r in c.execute("SELECT status, count(*) AS n FROM jobs GROUP BY status").fetchall()
        },
        "assessments": c.execute("SELECT count(*) AS n FROM assessments").fetchone()["n"],
        "reviews": c.execute("SELECT count(*) AS n FROM reviews").fetchone()["n"],
    }
