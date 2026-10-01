"""Insights are derived, not asserted.

The property that matters: a finding must not appear unless its evidence exists.
A dashboard that always has something alarming to say trains people to ignore it.
"""
from __future__ import annotations

import hashlib

from app import db, insights
from app.ports.analyser import StubAnalyser


def _seed(n: int) -> None:
    """Insert assessments covering every stub scenario."""
    stub = StubAnalyser()
    with db.conn() as c:
        for i in range(60):
            sha = hashlib.sha256(f"ins-{i}".encode()).hexdigest()
            img = db.insert_image(
                c, sha256=sha, storage_key=f"k/{sha}", content_type="image/png",
                byte_size=1, site_id="S1", cabinet_id=f"CAB-{i % 7}",
                cabinet_type="TEST-42U", width_px=1400, height_px=1000, captured_at=None)
            rep, ass = stub.analyse(b"", img)
            r = db.insert_representation(c, img["id"], rep)
            db.insert_assessment(c, img["id"], r["id"], ass)
        c.commit()


def test_empty_corpus_emits_no_findings():
    with db.conn() as c:
        d = insights.compute(c)
    assert d["corpus"]["assessments"] == 0
    assert d["rnd"] == [] and d["customer"] == []


def test_findings_are_derived_from_the_corpus():
    _seed(60)
    with db.conn() as c:
        d = insights.compute(c)

    assert d["corpus"]["assessments"] > 0
    assert set(d["verdicts"]) <= {"adequate", "limited", "critical", "borderline", "abstained"}

    # thermal and cable aggregates must be internally consistent
    assert d["cable"]["occluded_by_cable_u"] <= d["cable"]["occluded_u_total"]
    assert sum(d["cable"]["occlusion_causes"].values()) == d["cable"]["occluded_u_total"]
    assert d["capacity"]["usable_free_u"] <= d["capacity"]["reported_free_u"]
    assert d["capacity"]["gap_u"] == d["capacity"]["reported_free_u"] - d["capacity"]["usable_free_u"]
    assert d["thermal"]["cabinets_unblanked_breach"] <= d["thermal"]["cabinets_unblanked"]

    # both audiences get findings, and every finding carries its evidence
    assert d["rnd"] and d["customer"]
    for f in d["rnd"]:
        assert {"area", "title", "finding", "attribution", "signal", "evidence"} <= set(f)
    for f in d["customer"]:
        assert {"area", "title", "impact", "action", "cost", "avoid", "evidence"} <= set(f)

    # the correlated finding only appears when BOTH causes are present
    ids = {f["id"] for f in d["rnd"]}
    if d["cable"]["occluded_by_cable_u"] and d["thermal"]["unblanked_u"]:
        assert "rnd-compound" in ids
    else:
        assert "rnd-compound" not in ids


def test_confidence_correlation_only_claimed_when_real():
    _seed(60)
    with db.conn() as c:
        d = insights.compute(c)
    ids = {f["id"] for f in d["rnd"]}
    ev = d["evidence"]
    if ev["confidence_clear"] is not None and ev["confidence_cable_obscured"] is not None:
        gap = ev["confidence_clear"] - ev["confidence_cable_obscured"]
        assert ("rnd-conf" in ids) == (gap >= 0.05)
