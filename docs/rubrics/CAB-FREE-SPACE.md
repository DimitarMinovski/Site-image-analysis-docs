# Cabinet Free Space — Rubric `CAB-FREE-SPACE`

| | |
|---|---|
| **Rubric ID** | `CAB-FREE-SPACE` |
| **Version** | `0.1.0` |
| **Status** | **DRAFT — requires domain sign-off before any labelling begins** |
| **Owner** | Design and User Experience (DUX) |
| **Applies to** | 19-inch equipment cabinets at radio access sites |
| **Input** | One rectified frontal photograph of the cabinet interior, door open |

> **Read this first.** Every threshold in section 7 is a placeholder written to
> make the structure concrete. They are engineering judgement, not a quoted
> Ericsson standard. Section 10 lists exactly what a domain expert must confirm
> or change before this rubric is used to label data. Do not skip that step —
> labelling against wrong thresholds produces a gold set that is wrong for the
> lifetime of the project.

---

## 1. Purpose

Determine how much genuinely usable space remains in a site cabinet, and whether
the current state presents a thermal or serviceability risk.

The assessment answers three questions in order:

1. How many rack units are physically available?
2. How many of those could realistically be installed into?
3. Does the present state violate a stated requirement?

A verdict of `adequate` / `limited` / `critical` is **derived** from those
answers by the decision table in section 7. It is never assessed directly.

---

## 2. Scope and limitations

**In scope.** Vertical occupancy of the cabinet front plane, blanking panel
presence, visible cable obstruction, and visible top clearance.

**Explicitly out of scope for a single frontal image.** These must be reported
as *not determinable* rather than guessed:

| Not determinable | Why | Field |
|---|---|---|
| Usable depth behind the rail | No depth information in one frontal view | `depth.determinable = false` |
| Spare DC breaker positions | Usually inside a closed power compartment | `capacity.power_determinable` |
| Spare fibre / patch ports | Not legible at cabinet-wide framing | `capacity.ports_determinable` |
| Weight loading limits | Not observable | out of scope |
| Rear-side occupancy | Not in frame | out of scope |

This matters because **free rack units are not the same as expansion capacity.**
A cabinet with 10U free and no spare breaker positions cannot take new
equipment. The rubric reports the U figure honestly and flags the unknowns
rather than implying a capacity conclusion it cannot support.

---

## 3. Reference geometry

These are real, stable values from `EIA-310` / `IEC 60297-3-100` and are the
basis of all measurement:

| Quantity | Value |
|---|---|
| 1 rack unit (U) | 44.45 mm (1.75 in) |
| Mounting hole pattern within 1U | 15.875 / 15.875 / 12.7 mm |
| Standard panel width | 19 in |

The repeating hole pattern is the **primary scale reference**. Because it is
periodic and dimensionally fixed, pixels-per-U can be derived from the image
itself with no fiducial marker and no assumption about cabinet height.

`total_u` must additionally be cross-checked against the cabinet type record
from site data. Disagreement is an abstention trigger (clause `GEOM-1.0`).

---

## 4. U-state definitions

Every rack unit position is assigned exactly one state. Four states, not two —
collapsing them is the single largest source of silent error.

| State | Definition | Counts toward `free_u`? |
|---|---|---|
| `occupied` | Contains equipment, shelf, PDU, cable manager, or patch panel | No |
| `blanked` | Blanking panel fitted, nothing installed behind it | **Yes** |
| `open` | No panel, nothing installed | **Yes** |
| `occluded` | Cannot be determined — obscured by cables, glare, or out of frame | **No** |

Two rules that are easy to get wrong:

**`blanked` is available space.** A blanking panel is a removable airflow
control, not equipment. The U is available capacity and counts as free.

**Unknown hardware is `occupied`, never free.** If the detector sees something
it cannot classify, the U is occupied. Failing open — treating unrecognised
objects as empty space — produces the one genuinely dangerous error in this
system: a full cabinet reported as having room.

`occluded` U are excluded from `free_u` and counted separately. They widen the
uncertainty interval rather than being resolved by assumption.

---

## 5. Derived quantities

Computed arithmetically from the U map. **Never** produced by a language model.

```
available_u              = count(blanked) + count(open)
free_u                   = available_u
occluded_u               = count(occluded)
largest_contiguous_free_u = longest run of consecutive available U
```

`usable_free_u` is the figure that drives the verdict. A contiguous run of
available U is **usable** only if all of the following hold:

- it is not designated as required clearance above a unit under `THERMAL-2.1`
- no cable obstruction of severity `high` overlaps the run
- usable depth is satisfied, or depth is not determinable *and* the run is
  flagged accordingly

```
usable_free_u = sum of lengths of usable runs
```

If the site design reserves U for planned equipment, those U are excluded from
`usable_free_u` and reported as `reserved_u`.

---

## 6. Clause catalogue

Stable IDs. Findings cite these, and citations may reach customer-facing
reports, so **never renumber a clause** — deprecate and add.

| Clause | Requirement | Image-determinable |
|---|---|---|
| `GEOM-1.0` | `total_u` must match the cabinet type record | Yes |
| `GEOM-1.1` | Scale must derive from the rail hole pattern, not an assumed height | Yes |
| `OCC-1.0` | Unclassifiable hardware is counted as occupied | Yes |
| `OCC-2.0` | Occluded U are never counted as free | Yes |
| `BLANK-1.0` | `open` U in an active airflow path require blanking panels | Yes |
| `THERMAL-2.1` | Minimum top clearance above units requiring it | Yes (if visible) |
| `CABLE-4.3` | Cable bundles must not obstruct otherwise available U | Yes |
| `DEPTH-3.0` | Available U must meet minimum usable depth | **No** — flag only |
| `CAP-5.0` | Free U without spare power positions is not expansion capacity | **No** — flag only |
| `ACCESS-6.0` | Serviceability clearance must be maintained at the cabinet face | Partially |

---

## 7. Verdict decision table

Evaluated top to bottom, **first match wins**. Exhaustive: `usable_free_u` is a
non-negative integer, so rules 8 and 9 cover all remaining cases.

| # | Condition | Result |
|---|---|---|
| 1 | Quality gate failed | `ABSTAIN` |
| 2 | `scale.confidence < 0.70` or `GEOM-1.0` mismatch | `ABSTAIN` |
| 3 | `occluded_u > 6` | `ABSTAIN` |
| 4 | Verdict differs at the two ends of the `free_u` uncertainty interval | `BORDERLINE` → human review |
| 5 | `THERMAL-2.1` violated | `critical` |
| 6 | `usable_free_u < 3` | `critical` |
| 7 | `cable_obstruction == high` | `limited` |
| 8 | `missing_blanking_u >= 3` | `limited` |
| 9 | `usable_free_u` in 3..5 | `limited` |
| 10 | `usable_free_u >= 6` | `adequate` |

Note the ordering choices, which are deliberate:

**Abstention outranks everything.** A cabinet that cannot be measured must not
receive a verdict. The correct output is a reshoot request.

**Thermal violation outranks free space.** A cabinet with 15U free and no top
clearance above a baseband is `critical`, because the risk is present now.

**`BORDERLINE` exists so thresholds are honest.** If the measurement is
7U ± 3U, the verdict genuinely differs across that range, and picking one is a
false claim of precision. It goes to a human instead.

---

## 8. Abstention rules

The service **must** be able to decline. Abstention is a success state, not a
failure. Triggers are rules 1–3 above, plus:

- cabinet frame not fully in frame (top or bottom rail missing)
- rail hole pattern not detectable along a sufficient run
- more than 20% of the cabinet face lost to glare or shadow

Every abstention returns an `abstain_reason` and a specific reshoot
instruction, routed to the existing *Better Photo Needed* flow.

---

## 9. Confidence

`confidence` in v0.1.0 is the minimum of the component confidences (scale,
detection, occlusion fraction). This is a placeholder.

**It must be calibrated in Step 3.** A stated 0.80 has to mean "right about 80%
of the time", measured on the gold set. An uncalibrated confidence score is
worse than none, because reviewers learn within a fortnight that it means
nothing and then ignore it permanently.

---

## 10. Open questions — required before sign-off

A domain expert must resolve each of these. Until then this rubric is not fit
for labelling.

1. **Verdict thresholds.** Are 3 / 6 the right `usable_free_u` boundaries?
   These should reflect the smallest realistic expansion unit.
2. **Minimum usable depth** for `DEPTH-3.0` — a concrete millimetre figure.
3. **Which equipment requires top clearance**, and how much, for
   `THERMAL-2.1`. Needs the real product list.
4. **Does `blanked` count as free?** This rubric says yes. Confirm.
5. **`missing_blanking_u >= 3`** — is 3 the right trigger, and does it depend on
   airflow design (front-to-back vs bottom-to-top)?
6. **Cabinet types in scope**, with their `total_u`, for the `GEOM-1.0` check.
7. **Is power capacity in scope** at all, or does `CAP-5.0` stay a flag?
8. **`occluded_u > 6`** — right abstention threshold, or should it scale with
   cabinet size?

---

## 11. Change log

| Version | Date | Change |
|---|---|---|
| 0.1.0 | 2026-09-24 | Initial draft. Structure complete, thresholds placeholder. |
