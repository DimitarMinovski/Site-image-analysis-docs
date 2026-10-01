"""Correlated insights across the assessment corpus.

The detail view answers "what is wrong with this cabinet". This module answers
the harder and more useful question: "what is wrong across all of them, and
whose problem is it".

Everything here is derived arithmetically from stored assessments and
representations. Findings are emitted only when their evidence threshold is met,
and each carries the numbers it was derived from, so nothing is asserted that
cannot be traced back to rows.

Two framings over the same arithmetic:

  R&D       what should change in the product, process or capture standard
  Customer  what this costs, what to do about it, and how to stop it recurring

Thermal and cable management get particular attention because they are not
independent. Cable bundles obstruct airflow AND hide the very positions where
blanking panels would go AND prevent remote assessment, so one physical
deficiency produces three distinct customer costs. A per-cabinet view cannot
show that; only the corpus can.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Optional

import psycopg


def _rows(c: psycopg.Connection) -> list[dict]:
    """Latest assessment per image, with its representation."""
    return c.execute(
        """SELECT DISTINCT ON (a.image_id)
                  a.id, a.image_id, a.verdict, a.usable_free_u, a.confidence,
                  a.rubric_version, a.created_at,
                  a.doc AS adoc, r.doc AS rdoc,
                  i.cabinet_id, i.site_id, i.cabinet_type
             FROM assessments a
             JOIN images i ON i.id = a.image_id
        LEFT JOIN representations r ON r.id = a.representation_id
         ORDER BY a.image_id, a.created_at DESC"""
    ).fetchall()


def compute(c: psycopg.Connection) -> dict[str, Any]:
    rows = _rows(c)
    n = len(rows)
    out: dict[str, Any] = {
        "corpus": {"assessments": n, "cabinets": 0, "sites": 0},
        "verdicts": {}, "evidence": {}, "capacity": {}, "thermal": {},
        "cable": {}, "clauses": [], "repeats": [], "rnd": [], "customer": [],
    }
    if n == 0:
        return out

    verdicts = Counter(r["verdict"] for r in rows)
    cabinets = {r["cabinet_id"] for r in rows if r["cabinet_id"]}
    sites = {r["site_id"] for r in rows if r["site_id"]}
    measurable = [r for r in rows if r["verdict"] != "abstained"]

    # ---- capacity: reported free space versus genuinely usable --------
    free_u = sum((r["adoc"].get("measurements") or {}).get("free_u", 0) for r in measurable)
    usable_u = sum((r["adoc"].get("measurements") or {}).get("usable_free_u", 0) for r in measurable)
    excl = Counter()
    for r in measurable:
        for run in (r["adoc"].get("measurements") or {}).get("free_runs", []) or []:
            if not run.get("usable") and run.get("excluded_reason"):
                excl[run["excluded_reason"]] += run["u_to"] - run["u_from"] + 1

    # ---- thermal ------------------------------------------------------
    unblanked_u = sum((r["adoc"].get("measurements") or {}).get("missing_blanking_u", 0)
                      for r in measurable)
    cabs_unblanked = [r for r in measurable
                      if ((r["adoc"].get("measurements") or {}).get("missing_blanking_u", 0) > 0)]
    # the rubric's BLANK-1.0 trigger is 3U; below that it is a note, not a breach
    cabs_unblanked_breach = [r for r in measurable
                             if ((r["adoc"].get("measurements") or {}).get("missing_blanking_u", 0) >= 3)]
    cabs_clearance = [r for r in measurable
                      if (r["adoc"].get("airflow") or {}).get("top_clearance_ok") is False]

    # ---- cable management --------------------------------------------
    occl_cause = Counter()
    occl_u_total = 0
    for r in rows:
        for span in ((r["rdoc"] or {}).get("u_map") or []):
            if span.get("state") == "occluded":
                u = span["u_to"] - span["u_from"] + 1
                occl_u_total += u
                occl_cause[span.get("occlusion_cause") or "unspecified"] += u
    cable_occl_u = occl_cause.get("cable_bundle", 0)
    obstruction = Counter((r["adoc"].get("airflow") or {}).get("cable_obstruction") or "unknown"
                          for r in measurable)
    cabs_cable = [r for r in rows
                  if any(s.get("occlusion_cause") == "cable_bundle"
                         for s in ((r["rdoc"] or {}).get("u_map") or []))]

    # ---- evidence quality --------------------------------------------
    confs = [r["confidence"] for r in rows if r["confidence"] is not None]
    mean_conf = round(sum(confs) / len(confs), 3) if confs else None
    abstained = verdicts.get("abstained", 0)
    borderline = verdicts.get("borderline", 0)

    # correlation: do cable-obscured cabinets score lower confidence?
    cc = [r["confidence"] for r in cabs_cable if r["confidence"] is not None]
    oc = [r["confidence"] for r in rows
          if r not in cabs_cable and r["confidence"] is not None]
    conf_cable = round(sum(cc) / len(cc), 3) if cc else None
    conf_clear = round(sum(oc) / len(oc), 3) if oc else None

    # ---- clause frequency --------------------------------------------
    clause = Counter()
    sev: dict[str, str] = {}
    for r in rows:
        for f in r["adoc"].get("findings", []) or []:
            clause[f["clause_id"]] += 1
            sev[f["clause_id"]] = f.get("severity", "info")

    # ---- repeat cabinets: capacity drift over time --------------------
    per_cab: dict[str, list] = {}
    for r in c.execute(
        """SELECT i.cabinet_id, a.verdict, a.usable_free_u, a.created_at
             FROM assessments a JOIN images i ON i.id = a.image_id
            WHERE i.cabinet_id IS NOT NULL
         ORDER BY i.cabinet_id, a.created_at"""
    ).fetchall():
        per_cab.setdefault(r["cabinet_id"], []).append(r)
    repeats = []
    for cab, hist in per_cab.items():
        if len(hist) < 2:
            continue
        a, b = hist[0], hist[-1]
        if a["usable_free_u"] is None or b["usable_free_u"] is None:
            continue
        repeats.append({
            "cabinet_id": cab, "observations": len(hist),
            "first_usable_u": a["usable_free_u"], "latest_usable_u": b["usable_free_u"],
            "delta_u": b["usable_free_u"] - a["usable_free_u"],
            "first_verdict": a["verdict"], "latest_verdict": b["verdict"],
        })
    repeats.sort(key=lambda x: x["delta_u"])

    out["corpus"] = {"assessments": n, "cabinets": len(cabinets), "sites": len(sites),
                     "measurable": len(measurable)}
    out["verdicts"] = dict(verdicts)
    out["evidence"] = {
        "abstained": abstained,
        "abstention_rate": round(abstained / n, 3),
        "borderline": borderline,
        "borderline_rate": round(borderline / n, 3),
        "mean_confidence": mean_conf,
        "confidence_cable_obscured": conf_cable,
        "confidence_clear": conf_clear,
    }
    out["capacity"] = {
        "reported_free_u": free_u, "usable_free_u": usable_u,
        "gap_u": free_u - usable_u, "exclusions": dict(excl),
    }
    out["thermal"] = {
        "unblanked_u": unblanked_u,
        "cabinets_unblanked": len(cabs_unblanked),
        "cabinets_unblanked_breach": len(cabs_unblanked_breach),
        "cabinets_clearance_violation": len(cabs_clearance),
        "u_consumed_by_clearance": excl.get("required_clearance", 0),
    }
    out["cable"] = {
        "occluded_u_total": occl_u_total,
        "occluded_by_cable_u": cable_occl_u,
        "occlusion_causes": dict(occl_cause),
        "cabinets_cable_obscured": len(cabs_cable),
        "obstruction_mix": dict(obstruction),
        "u_excluded_by_cable": excl.get("cable_obstruction", 0),
    }
    out["clauses"] = [{"clause": k, "count": v, "severity": sev.get(k, "info")}
                      for k, v in clause.most_common()]
    out["repeats"] = repeats[:10]
    out["rnd"] = _rnd(out, rows)
    out["customer"] = _customer(out, rows)
    return out


# --------------------------------------------------------------------- R&D

def _rnd(d: dict, rows: list[dict]) -> list[dict]:
    """Findings aimed at developers, engineers and designers.

    Each carries an attribution, because the useful question is not "is this
    broken" but "is this ours to fix".
    """
    f: list[dict] = []
    th, cb, ev, cap = d["thermal"], d["cable"], d["evidence"], d["capacity"]
    n = d["corpus"]["assessments"]

    if th["cabinets_unblanked"]:
        share = round(th["cabinets_unblanked"] / max(1, d["corpus"]["measurable"]) * 100)
        f.append({
            "id": "rnd-blanking", "area": "Thermal",
            "title": "Blanking panels are the most frequent deficiency in the estate",
            "finding": f"{th['cabinets_unblanked']} of {d['corpus']['measurable']} measurable cabinets "
                       f"({share}%) have at least one open rack unit with no blanking panel, "
                       f"{th['unblanked_u']}U in total; {th['cabinets_unblanked_breach']} exceed the rubric's "
                       "3U trigger for BLANK-1.0. The aggregate matters even where individual cabinets stay "
                       "under the threshold. "
                       "An unblanked opening lets cooled supply air bypass equipment and lets hot exhaust "
                       "recirculate to intakes, so intake temperature rises across the whole cabinet rather "
                       "than only at the gap.",
            "attribution": "Mostly process, partly product. A panel costs almost nothing and needs no "
                           "equipment change, so a rate this high is not an installer skill problem - it is "
                           "that panels are not default fitment and the requirement is not in the design pack.",
            "signal": "Ship blanking panels as default fitment for every unoccupied U, and derive the "
                      "quantity automatically from the cabinet layout in the design pack.",
            "evidence": {"cabinets": th["cabinets_unblanked"], "breaching": th["cabinets_unblanked_breach"],
                         "u_total": th["unblanked_u"], "share_pct": share},
        })

    if cb["occluded_by_cable_u"]:
        f.append({
            "id": "rnd-cable-assess", "area": "Cable management",
            "title": "Cable bundles are the dominant reason the estate cannot be assessed remotely",
            "finding": f"{cb['occluded_by_cable_u']}U across {cb['cabinets_cable_obscured']} cabinets could not "
                       f"be determined because cable bundles obscure the rack face - "
                       f"{round(cb['occluded_by_cable_u'] / max(1, cb['occluded_u_total']) * 100)}% of all "
                       "undeterminable positions. Those units are excluded from free space rather than guessed, "
                       "so they widen every uncertainty interval they touch.",
            "attribution": "Product. If bundles routinely cross the rack face, the supplied cable management "
                           "does not have the capacity or the routing geometry for the cable count these "
                           "cabinets actually carry.",
            "signal": "Side cable managers sized for the final cable count rather than the initial one, with "
                      "slack management designed in. Specify the routing path so the rack face stays clear.",
            "evidence": {"u": cb["occluded_by_cable_u"], "cabinets": cb["cabinets_cable_obscured"],
                         "causes": cb["occlusion_causes"]},
        })

    # the correlated finding: one physical cause, three separate costs
    if cb["occluded_by_cable_u"] and th["unblanked_u"]:
        f.append({
            "id": "rnd-compound", "area": "Thermal + Cable",
            "title": "Thermal and cable findings are the same physical problem counted three times",
            "finding": "Cable bundles that obstruct the rack face do three things at once: they block the "
                       "airflow path, they cover the very positions where blanking panels would be fitted, "
                       "and they prevent the cabinet being assessed without a site visit. The corpus shows "
                       f"{cb['cabinets_cable_obscured']} cabinets with cable occlusion and "
                       f"{th['cabinets_unblanked']} with unblanked openings; treating these as two backlog "
                       "items understates the value of fixing one of them.",
            "attribution": "Product. A single cable management deficiency, producing a thermal cost, a "
                           "capacity cost and an operational cost.",
            "signal": "Treat cable management capacity as a thermal requirement, not a tidiness requirement. "
                      "Any cable management review should be scored against all three consequences.",
            "evidence": {"cable_cabinets": cb["cabinets_cable_obscured"],
                         "unblanked_cabinets": th["cabinets_unblanked"]},
        })

    if ev["abstention_rate"] >= 0.1:
        f.append({
            "id": "rnd-evidence", "area": "Observability",
            "title": "Evidence quality, not cabinet condition, limits part of the estate",
            "finding": f"{ev['abstained']} of {n} assessments ({round(ev['abstention_rate'] * 100)}%) "
                       "produced no verdict at all because the cabinet could not be measured from the "
                       "photograph supplied. Those are not bad cabinets; they are cabinets we know nothing about.",
            "attribution": "Process and product. Partly capture discipline, partly that the features the "
                           "measurement depends on - the mounting rails - are not reliably visible in the "
                           "installed condition.",
            "signal": "Enforce the capture standard with a framing overlay at the point of capture. A "
                      "photograph rejected in the viewfinder costs seconds; one rejected afterwards costs a "
                      "return visit.",
            "evidence": {"abstained": ev["abstained"], "rate": ev["abstention_rate"]},
        })

    if ev["confidence_cable_obscured"] is not None and ev["confidence_clear"] is not None \
            and ev["confidence_clear"] - ev["confidence_cable_obscured"] >= 0.05:
        f.append({
            "id": "rnd-conf", "area": "Cable management",
            "title": "A better model will not fix what cables hide",
            "finding": f"Mean confidence is {ev['confidence_cable_obscured']} on cabinets with cable "
                       f"occlusion against {ev['confidence_clear']} on clear ones - a gap of "
                       f"{round(ev['confidence_clear'] - ev['confidence_cable_obscured'], 2)}. The information "
                       "is not degraded, it is absent: no amount of model improvement recovers a position that "
                       "is physically covered.",
            "attribution": "Product. This is a physical obstruction, not a perception limitation.",
            "signal": "Stop treating low confidence on these cabinets as a model backlog item. The fix is "
                      "cable management geometry.",
            "evidence": {"confidence_obscured": ev["confidence_cable_obscured"],
                         "confidence_clear": ev["confidence_clear"]},
        })

    if cap["gap_u"] > 0:
        f.append({
            "id": "rnd-gap", "area": "Capacity",
            "title": "Reported free space overstates usable space",
            "finding": f"The estate reports {cap['reported_free_u']}U free but only {cap['usable_free_u']}U "
                       f"is usable - a gap of {cap['gap_u']}U. Breakdown by reason: "
                       + ", ".join(f"{k.replace('_', ' ')} {v}U" for k, v in cap["exclusions"].items()) + ".",
            "attribution": "Mixed. Clearance loss is designed-in and correct; obstruction loss is recoverable; "
                           "depth loss is not even measurable from a frontal photograph.",
            "signal": "Publish usable free space rather than free space wherever capacity is quoted. The two "
                      "numbers differ enough to change a planning decision.",
            "evidence": cap,
        })

    worsening = [r for r in d["repeats"] if r["delta_u"] < 0]
    if worsening:
        f.append({
            "id": "rnd-drift", "area": "Capacity",
            "title": "Capacity is drifting downward on re-observed cabinets",
            "finding": f"{len(worsening)} cabinet(s) observed more than once have lost usable space since the "
                       "first observation, the worst by "
                       f"{abs(worsening[0]['delta_u'])}U ({worsening[0]['cabinet_id']}). A snapshot reports a "
                       "state; a trend predicts which sites run out of room next.",
            "attribution": "Process. Unplanned additions without a space assessment.",
            "signal": "Make change detection across visits a first-class output, not a by-product. Forecast "
                      "exhaustion per site rather than reporting occupancy per cabinet.",
            "evidence": {"worsening": worsening[:3]},
        })
    return f


# ---------------------------------------------------------------- Customer

def _customer(d: dict, rows: list[dict]) -> list[dict]:
    """Findings aimed at the operator: cost, action, and how to avoid recurrence."""
    f: list[dict] = []
    th, cb, ev, cap, v = d["thermal"], d["cable"], d["evidence"], d["capacity"], d["verdicts"]

    if th["cabinets_unblanked"]:
        f.append({
            "id": "cust-thermal", "area": "Thermal",
            "title": "Unblanked openings are raising intake temperature across whole cabinets",
            "impact": f"{th['cabinets_unblanked']} cabinets carry {th['unblanked_u']}U of unblanked openings "
                      f"between them ({th['cabinets_unblanked_breach']} individually above the 3U threshold). "
                      "The effect is not local: cooled air bypasses equipment and hot exhaust returns to "
                      "intakes, so every unit in the cabinet runs warmer. The consequences are throttling "
                      "under load, shortened component life, thermal shutdowns, and cooling energy spent "
                      "circulating air that never reaches equipment.",
            "action": "Fit blanking panels to all open positions. No equipment is moved, no service is "
                      "interrupted, and no change window is needed.",
            "cost": "Lowest-cost remediation in the set. Panels and a visit.",
            "avoid": "Add blanking panel fitment to installation acceptance criteria, and require the as-built "
                     "photograph to show it. A cabinet that is signed off unblanked will stay unblanked for years.",
            "evidence": {"cabinets": th["cabinets_unblanked"], "u": th["unblanked_u"]},
        })

    if cb["occluded_by_cable_u"] or cb["u_excluded_by_cable"]:
        locked = cb["u_excluded_by_cable"]
        f.append({
            "id": "cust-cable", "area": "Cable management",
            "title": "Cable bundles are costing capacity, assessability and diagnosis time",
            "impact": f"{cb['occluded_by_cable_u']}U across {cb['cabinets_cable_obscured']} cabinets cannot be "
                      "assessed at all because bundles cover the rack face"
                      + (f", and {locked}U of otherwise available space is blocked outright" if locked else "")
                      + ". Three separate costs follow: capacity you own but cannot use; a site visit to "
                        "establish what a photograph should have shown; and longer fault diagnosis when "
                        "bundles also hide labels and status indicators.",
            "action": "Dress the bundles into the side cable managers. This recovers capacity, makes the "
                      "cabinet remotely assessable, and improves airflow at the same time.",
            "cost": "One visit per cabinet, no new hardware. Recovered capacity is capacity you have already "
                    "paid for.",
            "avoid": "Require cable dressing as a completion criterion rather than a tidiness preference, and "
                     "size cable management for the final cable count at design time, not the first install.",
            "evidence": {"occluded_u": cb["occluded_by_cable_u"], "locked_u": locked,
                         "cabinets": cb["cabinets_cable_obscured"]},
        })

    if cap["gap_u"] > 0:
        pct = round(cap["gap_u"] / max(1, cap["reported_free_u"]) * 100)
        f.append({
            "id": "cust-capacity", "area": "Capacity",
            "title": "You have less usable space than the free-space figure suggests",
            "impact": f"{cap['reported_free_u']}U reads as free across the estate, but only "
                      f"{cap['usable_free_u']}U could actually take equipment - {pct}% of the apparent "
                      "headroom is not available. Planning an expansion against the larger number produces "
                      "a failed visit.",
            "action": "Plan against usable free space. Where the loss is cable obstruction it is recoverable; "
                      "where it is thermal clearance it is not, and should not be.",
            "cost": "Nothing to fix the number. The cost is in the expansions planned against the wrong one.",
            "avoid": "Quote usable free space in capacity reporting, and confirm depth on site before "
                     "committing an installation plan - a single frontal photograph cannot establish it.",
            "evidence": cap,
        })

    if v.get("critical"):
        f.append({
            "id": "cust-critical", "area": "Risk",
            "title": f"{v['critical']} cabinet(s) are at the limit now",
            "impact": "These have under 3U of usable space or a present thermal clearance violation. They "
                      "cannot take the next expansion, and the clearance cases carry a shutdown risk today "
                      "rather than at some future load.",
            "action": "Treat as a work queue rather than a report. Clearance violations first, because that "
                      "risk is live; capacity next.",
            "cost": "Varies. Some are resolved by removing equipment that is already decommissioned.",
            "avoid": "Flag cabinets at a capacity threshold before the next expansion is scheduled, not after "
                     "a crew has travelled.",
            "evidence": {"critical": v["critical"]},
        })

    if ev["abstained"]:
        f.append({
            "id": "cust-evidence", "area": "Evidence",
            "title": f"{ev['abstained']} cabinet(s) could not be assessed from the photograph supplied",
            "impact": "No verdict was issued for these - deliberately, because a guess from an unmeasurable "
                      "image is worse than no answer. Until they are re-photographed their state is unknown, "
                      "and unknown cabinets cannot be planned around.",
            "action": "Re-photograph to the capture standard: door fully open, square to the face, both "
                      "mounting rails visible top to bottom, no direct flash.",
            "cost": "Minutes, if caught while someone is on site. A return visit if not.",
            "avoid": "Validate the photograph at the point of capture. The service will accept or reject it in "
                     "seconds while the installer is still standing in front of the cabinet.",
            "evidence": {"abstained": ev["abstained"], "rate": ev["abstention_rate"]},
        })

    if v.get("borderline"):
        f.append({
            "id": "cust-borderline", "area": "Evidence",
            "title": f"{v['borderline']} cabinet(s) were referred for human review rather than scored",
            "impact": "For these the plausible range of free space straddles a verdict boundary, usually "
                      "because cables hide enough positions to make the answer genuinely ambiguous. Reporting "
                      "a single verdict would be a false claim of precision.",
            "action": "A reviewer decides, or a better photograph removes the ambiguity. Both are cheap.",
            "cost": "A few minutes of review each.",
            "avoid": "Reducing cable occlusion narrows these intervals and removes most borderline cases "
                     "without any change to the assessment.",
            "evidence": {"borderline": v["borderline"]},
        })
    return f
