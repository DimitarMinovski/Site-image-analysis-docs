"""End-to-end tests. These define Phase F "done".

Three properties matter more than coverage:

  F1  the whole path works: upload -> job -> validated assessment -> review
  F2  uploading the same bytes twice creates one image and one job
  F3  an analyser that returns an invalid document fails the job and writes
      NOTHING to assessments

F3 is the one worth having. It proves the validation gate actually guards the
database rather than merely existing.
"""
from __future__ import annotations

import io
import os
import struct
import time
import zlib

import pytest
from fastapi.testclient import TestClient

from app import db
from app.config import settings
from app.main import app
from worker.run import process_once

AUTH = {"Authorization": f"Bearer {settings.api_token}"}


def png(width: int = 1200, height: int = 1600, seed: int = 0) -> bytes:
    """Minimal valid PNG, built by hand so the tests need no fixture files.

    `seed` changes the pixel data, which changes the SHA-256, which is what
    selects the stub's scenario - so varying it exercises different verdicts.
    """
    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = bytes([0]) + bytes([(seed + i) % 256 for i in range(width * 3)])
    raw = row * height
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


@pytest.fixture
def client():
    return TestClient(app)


def _upload(client, seed: int, **form):
    body = {"site_id": "T-SITE", "cabinet_id": f"T-CAB-{seed}", "cabinet_type": "TEST-42U"}
    body.update(form)
    return client.post("/images", files={"file": (f"c{seed}.png", png(seed=seed), "image/png")},
                       data=body, headers=AUTH)


# ---------------------------------------------------------------- auth / guards

def test_upload_requires_token(client):
    r = client.post("/images", files={"file": ("x.png", png(seed=1), "image/png")})
    assert r.status_code == 401


def test_rejects_non_image_by_magic_bytes(client):
    # a .png filename and an image content type, but the bytes are not an image
    r = client.post("/images", files={"file": ("evil.png", b"#!/bin/sh\nrm -rf /", "image/png")},
                    headers=AUTH)
    assert r.status_code == 415


def test_rejects_too_small_image(client):
    r = client.post("/images", files={"file": ("tiny.png", png(64, 64, seed=9), "image/png")},
                    headers=AUTH)
    assert r.status_code == 422


# ----------------------------------------------------------------------- F1 e2e

def test_f1_end_to_end(client):
    up = _upload(client, seed=101)
    assert up.status_code == 202, up.text
    sha = up.json()["image_sha256"]
    assert up.json()["duplicate"] is False

    assert process_once() is True              # worker drains the job

    meta = client.get(f"/images/{sha}", headers=AUTH).json()
    assert meta["job"]["status"] == "done", meta["job"]
    aid = meta["assessment_id"]
    assert aid

    got = client.get(f"/assessments/{aid}", headers=AUTH).json()
    a = got["assessment"]
    assert a["rubric"]["id"] == "CAB-FREE-SPACE"
    assert a["verdict"]["value"] in {"adequate", "limited", "critical", "borderline", "abstained"}
    assert a["verdict"]["rule_id"] >= 1                      # traceable to a rule
    assert got["representation"] is not None                 # stored separately
    assert a["measurements"]["free_u"] == (
        a["measurements"]["blanked_u"] + a["measurements"]["open_u"])
    assert any(n["aspect"] == "usable_depth" for n in a["not_determinable"])

    # review is appended, not a mutation
    rv = client.post(f"/assessments/{aid}/review",
                     json={"status": "corrected", "corrected_verdict": "limited",
                           "reviewer_id": "tester", "disputed_clause": "BLANK-1.0",
                           "note": "airflow is bottom-to-top here"}, headers=AUTH)
    assert rv.status_code == 201, rv.text

    again = client.get(f"/assessments/{aid}", headers=AUTH).json()
    assert len(again["reviews"]) == 1
    assert again["reviews"][0]["disputed_clause"] == "BLANK-1.0"
    assert again["assessment"]["verdict"]["value"] == a["verdict"]["value"]  # unchanged

    stats = client.get("/stats").json()
    assert any(c["clause"] == "BLANK-1.0" for c in stats["clause_overrides"])


# --------------------------------------------------------------- F2 idempotency

def test_f2_idempotent_upload(client):
    first = _upload(client, seed=202)
    assert first.status_code == 202
    sha = first.json()["image_sha256"]
    process_once()

    second = _upload(client, seed=202)
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert second.json()["image_sha256"] == sha

    with db.conn() as c:
        imgs = c.execute("SELECT count(*) AS n FROM images WHERE sha256=%s", (sha,)).fetchone()["n"]
        img = db.find_image_by_sha(c, sha)
        jobs = c.execute("SELECT count(*) AS n FROM jobs WHERE image_id=%s",
                         (img["id"],)).fetchone()["n"]
    assert imgs == 1
    assert jobs == 1, "a duplicate upload must not enqueue a second job"


# ------------------------------------------------------- F3 the validation gate

def test_f3_invalid_analyser_output_is_not_persisted(client, monkeypatch):
    up = _upload(client, seed=303)
    sha = up.json()["image_sha256"]
    with db.conn() as c:
        img = db.find_image_by_sha(c, sha)
        before = c.execute("SELECT count(*) AS n FROM assessments").fetchone()["n"]

    class Broken:
        def analyse(self, image, image_row):
            rep = {
                "schema_version": "1.0.0",
                "image": {"sha256": image_row["sha256"], "width_px": 10, "height_px": 10},
                "site": {"site_id": "x", "cabinet_id": "y"},
                "quality": {"gate_passed": True, "issues": []},
                "scale": {"px_per_u": 10.0, "method": "rail_hole_pattern",
                          "confidence": 0.9, "measured_total_u": 10},
                # inconsistent: claims 10U but the map only covers 5
                "u_map": [{"u_from": 1, "u_to": 5, "state": "open", "confidence": 0.9}],
                "provenance": {"perception_version": "broken", "produced_at": "2026-10-01T00:00:00Z"},
            }
            ass = {
                "schema_version": "1.0.0",
                "rubric": {"id": "CAB-FREE-SPACE", "version": "0.1.0"},
                "representation_ref": {"image_sha256": image_row["sha256"]},
                # free_u does not equal blanked + open
                "measurements": {"total_u": 10, "occupied_u": 5, "blanked_u": 0, "open_u": 5,
                                 "occluded_u": 0, "free_u": 9,
                                 "largest_contiguous_free_u": 5, "usable_free_u": 5},
                "verdict": {"value": "adequate", "rule_id": 10, "basis": "nonsense"},
                "provenance": {"produced_at": "2026-10-01T00:00:00Z",
                               "policy_engine_version": "broken"},
            }
            return rep, ass

        def describe(self):
            return "broken"

    monkeypatch.setattr("worker.run.get_analyser", lambda: Broken())
    assert process_once() is True

    with db.conn() as c:
        after = c.execute("SELECT count(*) AS n FROM assessments").fetchone()["n"]
        job = db.job_for_image(c, img["id"])
    assert after == before, "an invalid document must not be persisted"
    assert job["status"] in {"failed", "dead"}
    assert "contract violation" in (job["error"] or "")
    assert "free_u" in job["error"]


# ------------------------------------------------- all five verdict states exist

def test_stub_exercises_every_verdict_state():
    from app.ports.analyser import StubAnalyser

    import hashlib

    seen = set()
    stub = StubAnalyser()
    for i in range(400):
        # real hashes: f"{i:064x}" has leading zeros, so sha[:8] never varies
        sha = hashlib.sha256(str(i).encode()).hexdigest()
        _, a = stub.analyse(b"", {"sha256": sha, "site_id": "s", "cabinet_id": "c",
                                  "cabinet_type": "t", "width_px": 3000, "height_px": 4000})
        seen.add(a["verdict"]["value"])
    assert seen == {"adequate", "limited", "critical", "borderline", "abstained"}, seen


def test_every_stub_scenario_passes_the_contract():
    """Every canned scenario must satisfy both schemas and all invariants."""
    from app.ports.analyser import StubAnalyser
    from app.validation import validate_pair

    import hashlib

    stub = StubAnalyser()
    checked = set()
    for i in range(400):
        sha = hashlib.sha256(str(i).encode()).hexdigest()
        rep, ass = stub.analyse(b"", {"sha256": sha, "site_id": "s", "cabinet_id": "c",
                                      "cabinet_type": "t", "width_px": 3000, "height_px": 4000})
        validate_pair(rep, ass)          # raises on any violation
        checked.add(ass["verdict"]["value"])
    assert len(checked) == 5
