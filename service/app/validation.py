"""Validation gate.

Two layers, mirroring tools/validate.mjs so Python and Node agree:

  structural  the document conforms to the JSON Schema
  semantic    invariants a schema cannot express - the U map covers every
              position exactly once, free_u really is blanked plus open,
              occluded units are excluded, the verdict follows the rules,
              and every cited clause exists in the catalogue

The worker runs this BEFORE writing anything. A document that fails is a failed
job, not a stored row. That is the mechanism that keeps the contract honest once
a real analyser replaces the stub: if perception starts emitting something
incoherent, the pipeline stops instead of quietly persisting it.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

from .config import settings


class ContractError(ValueError):
    """Raised when a produced document breaks the contract."""


@lru_cache(maxsize=4)
def _schema(name: str) -> dict:
    return json.loads((settings.schema_dir / f"{name}.schema.json").read_text())


@lru_cache(maxsize=1)
def _clause_ids() -> frozenset[str]:
    p = settings.schema_dir.parent / "docs" / "rubrics" / "CAB-FREE-SPACE.clauses.json"
    if not p.is_file():
        return frozenset()
    return frozenset(c["id"] for c in json.loads(p.read_text())["clauses"])


def _structural(name: str, doc: dict) -> list[str]:
    v = Draft202012Validator(_schema(name))
    return [
        f"{'/'.join(str(x) for x in e.path) or '(root)'}: {e.message}"
        for e in sorted(v.iter_errors(doc), key=lambda e: list(e.path))
    ]


def _semantic_representation(doc: dict) -> list[str]:
    errs: list[str] = []
    u = sorted(doc["u_map"], key=lambda s: s["u_from"])

    for s in u:
        if s["u_to"] < s["u_from"]:
            errs.append(f"span {s['u_from']}-{s['u_to']} is inverted")
        if s["state"] == "occupied" and not s.get("occupied_class"):
            errs.append(f"U{s['u_from']}-{s['u_to']} occupied without occupied_class (OCC-1.0)")
        if s["state"] == "occluded" and not s.get("occlusion_cause"):
            errs.append(f"U{s['u_from']}-{s['u_to']} occluded without a cause")

    if u and u[0]["u_from"] != 1:
        errs.append("u_map does not start at U1")
    for a, b in zip(u, u[1:]):
        if b["u_from"] <= a["u_to"]:
            errs.append(f"u_map spans overlap at U{b['u_from']}")
        elif b["u_from"] != a["u_to"] + 1:
            errs.append(f"u_map has a gap before U{b['u_from']}")

    total = doc["scale"].get("measured_total_u")
    if isinstance(total, int):
        covered = sum(s["u_to"] - s["u_from"] + 1 for s in u)
        if covered != total:
            errs.append(f"u_map covers {covered}U, expected {total}")
        if u and u[-1]["u_to"] != total:
            errs.append(f"u_map ends at U{u[-1]['u_to']}, expected U{total}")
    return errs


def _semantic_assessment(doc: dict, representation: dict | None = None) -> list[str]:
    errs: list[str] = []
    m, v, unc = doc["measurements"], doc["verdict"], doc.get("uncertainty", {})

    if m["free_u"] != m["blanked_u"] + m["open_u"]:
        errs.append(f"free_u={m['free_u']} but blanked+open={m['blanked_u'] + m['open_u']}")
    if m["free_u"] + m["occupied_u"] + m["occluded_u"] != m["total_u"]:
        errs.append("free + occupied + occluded != total_u (occluded must not count as free, OCC-2.0)")

    runs = m.get("free_runs", [])
    usable = sum(r["u_to"] - r["u_from"] + 1 for r in runs if r["usable"])
    if runs and m["usable_free_u"] != usable:
        errs.append(f"usable_free_u={m['usable_free_u']} but usable runs total {usable}")
    for r in runs:
        if r["usable"] != (r.get("excluded_reason") is None):
            errs.append(f"run {r['u_from']}-{r['u_to']}: usable flag and excluded_reason disagree")
    if m["usable_free_u"] > m["free_u"]:
        errs.append("usable_free_u exceeds free_u")
    if m["largest_contiguous_free_u"] > m["free_u"]:
        errs.append("largest_contiguous_free_u exceeds free_u")

    if unc:
        if not (unc["free_u_low"] <= m["free_u"] <= unc["free_u_high"]):
            errs.append("free_u lies outside its own uncertainty interval")
        if unc["free_u_high"] - unc["free_u_low"] < m["occluded_u"]:
            errs.append("uncertainty interval is narrower than the occluded unit count")
        if not unc["verdict_stable_across_interval"] and v["value"] != "borderline":
            errs.append("verdict is unstable across the interval but not reported as borderline (rule 4)")

    if (v["value"] == "abstained") != (v.get("abstain_reason") is not None):
        errs.append("abstain_reason must be present exactly when the verdict is abstained")
    if v["value"] == "abstained" and not v.get("reshoot_instruction"):
        errs.append("an abstained verdict must carry a reshoot_instruction")

    known = _clause_ids()
    if known:
        cited = {f["clause_id"] for f in doc.get("findings", [])} | \
                {n["clause_id"] for n in doc.get("not_determinable", [])}
        for c in sorted(cited - known):
            errs.append(f"finding cites unknown clause {c}")

    if representation is not None:
        if doc["representation_ref"]["image_sha256"] != representation["image"]["sha256"]:
            errs.append("assessment references a different image than the representation")
    return errs


def validate_pair(representation: dict, assessment: dict) -> None:
    """Validate both documents. Raises ContractError listing every problem."""
    errs = [f"representation/structural: {e}" for e in _structural("representation", representation)]
    if not errs:
        errs += [f"representation/semantic: {e}" for e in _semantic_representation(representation)]
    errs += [f"assessment/structural: {e}" for e in _structural("assessment", assessment)]
    if not any(e.startswith("assessment/structural") for e in errs):
        errs += [f"assessment/semantic: {e}" for e in _semantic_assessment(assessment, representation)]
    if errs:
        raise ContractError("; ".join(errs))


def schemas_loadable() -> bool:
    try:
        _schema("representation")
        _schema("assessment")
        return True
    except Exception:
        return False
