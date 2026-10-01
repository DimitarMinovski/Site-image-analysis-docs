"""Analyser port.

    analyse(image_bytes, image_row) -> (representation, assessment)

StubAnalyser returns canned but schema-valid and internally consistent
documents. It is replaced in Steps 5-7 by a pipeline that rectifies, scales,
detects, builds the representation, and applies the policy engine.

Two design points matter here.

The stub picks its scenario from the image SHA, deterministically, cycling all
FIVE verdict states including abstained and borderline. Teams build the UI
against the happy path and then discover abstention has nowhere to render.
Exercising every state from day one costs nothing and forces the interface to
be honest.

The scenarios are canned rather than generated. A generator would drift out of
agreement with the schema invariants; these five are each internally consistent
by construction - the U map covers every position exactly once, free_u equals
blanked plus open, occluded is excluded, and the verdict follows from the
decision table.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from ..config import settings


class Analyser(Protocol):
    def analyse(self, image: bytes, image_row: dict) -> tuple[dict, dict]: ...
    def describe(self) -> str: ...


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# Five scenarios, one per verdict state. Each is hand-checked against the
# semantic invariants in tools/validate.mjs.
_SCENARIOS = [
    {
        "key": "adequate",
        "total": 42,
        "u_map": [
            {"u_from": 1, "u_to": 28, "state": "occupied", "occupied_class": "equipment", "confidence": 0.9},
            {"u_from": 29, "u_to": 40, "state": "blanked", "confidence": 0.92},
            {"u_from": 41, "u_to": 42, "state": "open", "confidence": 0.9},
        ],
        "counts": {"occupied": 28, "blanked": 12, "open": 2, "occluded": 0},
        "free_u": 14, "largest": 14, "usable": 14, "missing_blanking": 2,
        "runs": [{"u_from": 29, "u_to": 42, "usable": True, "excluded_reason": None}],
        "rule": 10, "verdict": "adequate",
        "basis": "usable_free_u=14 satisfies rule 10 (>= 6) with airflow compliant.",
        "low": 14, "high": 14, "stable": True, "conf": 0.88,
        "obstruction": "none", "blanking_ok": True, "clearance_ok": True,
    },
    {
        "key": "limited",
        "total": 42,
        "u_map": [
            {"u_from": 1, "u_to": 1, "state": "occupied", "occupied_class": "equipment",
             "equipment_model": "Baseband 6648", "equipment_u_height_catalogue": 1, "confidence": 0.91},
            {"u_from": 2, "u_to": 5, "state": "open", "confidence": 0.88},
            {"u_from": 6, "u_to": 7, "state": "occluded", "occlusion_cause": "cable_bundle", "confidence": 0.64},
            {"u_from": 8, "u_to": 20, "state": "occupied", "occupied_class": "equipment", "confidence": 0.86},
            {"u_from": 21, "u_to": 24, "state": "blanked", "confidence": 0.9},
            {"u_from": 25, "u_to": 25, "state": "open", "confidence": 0.87},
            {"u_from": 26, "u_to": 42, "state": "occupied", "occupied_class": "unknown_hardware", "confidence": 0.58},
        ],
        "counts": {"occupied": 31, "blanked": 4, "open": 5, "occluded": 2},
        "free_u": 9, "largest": 5, "usable": 7, "missing_blanking": 5,
        "runs": [
            {"u_from": 2, "u_to": 3, "usable": False, "excluded_reason": "required_clearance"},
            {"u_from": 4, "u_to": 5, "usable": True, "excluded_reason": None},
            {"u_from": 21, "u_to": 25, "usable": True, "excluded_reason": None},
        ],
        "rule": 8, "verdict": "limited",
        "basis": "missing_blanking_u=5 meets the >=3 trigger of rule 8. usable_free_u=7 would otherwise "
                 "have satisfied rule 10; airflow is the constraint here, not space.",
        "low": 9, "high": 11, "stable": True, "conf": 0.64,
        "obstruction": "moderate", "blanking_ok": False, "clearance_ok": True,
    },
    {
        "key": "critical",
        "total": 42,
        "u_map": [
            {"u_from": 1, "u_to": 40, "state": "occupied", "occupied_class": "equipment", "confidence": 0.89},
            {"u_from": 41, "u_to": 41, "state": "blanked", "confidence": 0.91},
            {"u_from": 42, "u_to": 42, "state": "open", "confidence": 0.9},
        ],
        "counts": {"occupied": 40, "blanked": 1, "open": 1, "occluded": 0},
        "free_u": 2, "largest": 2, "usable": 2, "missing_blanking": 1,
        "runs": [{"u_from": 41, "u_to": 42, "usable": True, "excluded_reason": None}],
        "rule": 6, "verdict": "critical",
        "basis": "usable_free_u=2 is below the rule 6 threshold of 3.",
        "low": 2, "high": 2, "stable": True, "conf": 0.9,
        "obstruction": "low", "blanking_ok": True, "clearance_ok": True,
    },
    {
        "key": "borderline",
        "total": 42,
        "u_map": [
            {"u_from": 1, "u_to": 33, "state": "occupied", "occupied_class": "equipment", "confidence": 0.87},
            {"u_from": 34, "u_to": 36, "state": "blanked", "confidence": 0.9},
            {"u_from": 37, "u_to": 38, "state": "open", "confidence": 0.88},
            {"u_from": 39, "u_to": 42, "state": "occluded", "occlusion_cause": "cable_bundle", "confidence": 0.55},
        ],
        "counts": {"occupied": 33, "blanked": 3, "open": 2, "occluded": 4},
        "free_u": 5, "largest": 5, "usable": 5, "missing_blanking": 2,
        "runs": [{"u_from": 34, "u_to": 38, "usable": True, "excluded_reason": None}],
        "rule": 4, "verdict": "borderline",
        "basis": "At free_u=5 the verdict is limited (rule 9); at free_u=9 it is adequate (rule 10). "
                 "4 occluded units make the interval straddle a threshold, so rule 4 defers to a human.",
        "low": 5, "high": 9, "stable": False, "conf": 0.47,
        "obstruction": "moderate", "blanking_ok": True, "clearance_ok": True,
    },
    {
        "key": "abstained",
        "total": 42,
        "u_map": [
            {"u_from": 1, "u_to": 42, "state": "occluded", "occlusion_cause": "glare", "confidence": 0.18},
        ],
        "counts": {"occupied": 0, "blanked": 0, "open": 0, "occluded": 42},
        "free_u": 0, "largest": 0, "usable": 0, "missing_blanking": 0,
        "runs": [],
        "rule": 1, "verdict": "abstained",
        "basis": "Quality gate failed: rails not detected and glare over 41% of the cabinet face. "
                 "No verdict is issued when the cabinet cannot be measured.",
        "low": 0, "high": 42, "stable": True, "conf": 0.18,
        "obstruction": None, "blanking_ok": None, "clearance_ok": None,
        "abstain_reason": "quality_gate_failed",
        "reshoot": "Open the cabinet door fully, stand square to the face, and ensure both mounting "
                   "rails are visible top to bottom. Avoid direct flash on glossy equipment.",
        "quality_failed": True,
    },
]


class StubAnalyser:
    """Deterministic, schema-valid, and exercises every verdict state."""

    def _scenario(self, sha: str) -> dict:
        return _SCENARIOS[int(sha[:8], 16) % len(_SCENARIOS)]

    def analyse(self, image: bytes, image_row: dict) -> tuple[dict, dict]:
        sha = image_row["sha256"]
        s = self._scenario(sha)
        failed = s.get("quality_failed", False)

        representation = {
            "schema_version": "1.0.0",
            "image": {
                "sha256": sha,
                "source": "installer_upload",
                "width_px": image_row.get("width_px") or 3024,
                "height_px": image_row.get("height_px") or 4032,
            },
            "site": {
                "site_id": image_row.get("site_id"),
                "cabinet_id": image_row.get("cabinet_id") or f"unknown-{sha[:8]}",
                "cabinet_type": image_row.get("cabinet_type"),
                "cabinet_total_u_declared": s["total"],
            },
            "quality": {
                "gate_passed": not failed,
                "issues": ["rails_not_detected", "excessive_glare"] if failed else [],
                "glare_fraction": 0.41 if failed else 0.08,
                "face_visible_fraction": 0.52 if failed else 0.94,
            },
            "rectification": {"applied": not failed, "homography_rmse_px": None if failed else 1.4},
            "scale": {
                "px_per_u": None if failed else 38.6,
                "method": "unavailable" if failed else "rail_hole_pattern",
                "confidence": 0.12 if failed else 0.93,
                "residual_pct": None if failed else 0.9,
                "measured_total_u": None if failed else s["total"],
            },
            "u_map": s["u_map"],
            "depth": {"determinable": False, "reason": "single_frontal_image"},
            "capacity": {"power_determinable": False, "ports_determinable": False},
            "provenance": {
                "perception_version": settings.perception_version,
                "detector_version": None,
                "vlm_model": None,
                "produced_at": _now(),
                "pipeline_stages": [],
            },
        }

        findings = []
        if s["missing_blanking"] >= 3:
            findings.append({
                "clause_id": "BLANK-1.0", "severity": "major",
                "text": f"{s['missing_blanking']} open rack units have no blanking panels fitted, "
                        "permitting hot air recirculation across the cabinet face.",
                "recommendation": "Fit blanking panels to the open positions. No equipment change required.",
                "source": "policy_engine",
            })
        if s["counts"]["occluded"] > 0:
            findings.append({
                "clause_id": "OCC-2.0", "severity": "info",
                "text": f"{s['counts']['occluded']} rack units could not be determined and are "
                        "excluded from free space rather than guessed.",
                "recommendation": "Provide a close-up of the obscured region, or dress cables clear of the rack face.",
                "source": "policy_engine",
            })
        if failed:
            findings.append({
                "clause_id": "GEOM-1.1", "severity": "critical",
                "text": "Scale could not be established from the rail hole pattern.",
                "recommendation": "Re-shoot with both mounting rails fully in frame.",
                "source": "policy_engine",
            })

        assessment = {
            "schema_version": "1.0.0",
            "rubric": {"id": "CAB-FREE-SPACE", "version": settings.rubric_version},
            "representation_ref": {
                "image_sha256": sha,
                "site_id": image_row.get("site_id"),
                "cabinet_id": image_row.get("cabinet_id"),
            },
            "measurements": {
                "total_u": s["total"],
                "occupied_u": s["counts"]["occupied"],
                "blanked_u": s["counts"]["blanked"],
                "open_u": s["counts"]["open"],
                "occluded_u": s["counts"]["occluded"],
                "free_u": s["free_u"],
                "largest_contiguous_free_u": s["largest"],
                "usable_free_u": s["usable"],
                "reserved_u": 0,
                "missing_blanking_u": s["missing_blanking"],
                "free_runs": s["runs"],
            },
            "airflow": {
                "blanking_compliant": s["blanking_ok"],
                "top_clearance_ok": s["clearance_ok"],
                "cable_obstruction": s["obstruction"],
            },
            "verdict": {
                "value": s["verdict"],
                "rule_id": s["rule"],
                "basis": s["basis"],
                "abstain_reason": s.get("abstain_reason"),
                "reshoot_instruction": s.get("reshoot"),
            },
            "uncertainty": {
                "free_u_low": s["low"],
                "free_u_high": s["high"],
                "verdict_stable_across_interval": s["stable"],
                "confidence": s["conf"],
            },
            "not_determinable": [
                {"aspect": "usable_depth", "clause_id": "DEPTH-3.0",
                 "note": "Single frontal image. Available units may be unusable if equipment "
                         "protrudes behind the rail."},
                {"aspect": "power_capacity", "clause_id": "CAP-5.0",
                 "note": "Power compartment not visible. Free rack units do not imply expansion capacity."},
            ],
            "findings": findings,
            "narrative": self._narrative(s),
            "review": {
                # critical, abstained and borderline always go to a human.
                "required": s["verdict"] in {"critical", "abstained", "borderline"},
                "reason": {"critical": "verdict_critical", "abstained": "abstained",
                           "borderline": "borderline"}.get(s["verdict"]),
                "status": "pending",
            },
            "provenance": {
                "produced_at": _now(),
                "policy_engine_version": settings.policy_engine_version,
                "perception_version": settings.perception_version,
                "vlm_model": None,
                "vlm_prompt_version": None,
            },
        }
        return representation, assessment

    def _narrative(self, s: dict) -> str:
        if s["verdict"] == "abstained":
            return ("This cabinet could not be assessed. The mounting rails were not detectable and "
                    "glare covered more than 40% of the cabinet face, so no scale could be established. "
                    "A verdict would be a guess, so none has been issued.")
        n = (f"This {s['total']}U cabinet has {s['free_u']} free rack units, of which {s['usable']} "
             f"are realistically usable.")
        if s["counts"]["occluded"]:
            n += f" {s['counts']['occluded']} units could not be assessed and are excluded rather than guessed."
        if s["missing_blanking"] >= 3:
            n += (f" The constraint is airflow rather than space: {s['missing_blanking']} open positions "
                  "lack blanking panels, which is a no-risk change that would improve the verdict.")
        if not s["stable"]:
            n += (" The plausible range of free space straddles a verdict threshold, so this has been "
                  "referred for human review rather than reported with false precision.")
        n += (" Usable depth and spare power capacity could not be determined from a single frontal "
              "image, so the figure above should not be read as installable capacity without a site check.")
        return n

    def describe(self) -> str:
        return f"stub:{settings.perception_version}"


class PipelineAnalyser:
    """Steps 5-7. Rectify, scale, detect, build representation, apply policy."""

    def analyse(self, image: bytes, image_row: dict) -> tuple[dict, dict]:
        raise NotImplementedError(
            "ANALYSER=pipeline is not implemented yet. Steps 5-7 replace the stub: "
            "A/B rectify and scale, C detect, D representation, E judgement."
        )

    def describe(self) -> str:
        return "pipeline:unimplemented"


def get_analyser() -> Analyser:
    return PipelineAnalyser() if settings.analyser == "pipeline" else StubAnalyser()
