# Capture Standard — Cabinet Free Space

| | |
|---|---|
| **Version** | `0.1.0` (DRAFT) |
| **Owner** | DUX |
| **Applies to** | Photographs submitted for `CAB-FREE-SPACE` assessment |

> This document has more effect on final accuracy than the choice of model.
> A compliant photograph can be measured to within 1U. A non-compliant one
> cannot be measured at all, and the service will correctly refuse to try.

---

## 1. The two required shots

**Shot 1 — Full cabinet face (mandatory).**

- Door **fully open** and held open, not resting against the frame
- Camera **square to the cabinet face**: stand centred, lens at roughly
  mid-cabinet height, phone held vertical, not tilted up or down
- The **entire** cabinet interior in frame, including the **top rail and the
  bottom rail**. Both rails must be visible along their full height — this is
  what the scale measurement depends on
- Both left and right mounting rails visible
- No flash. Use ambient light or a torch held off-axis

**Shot 2 — Cable concentration close-up (mandatory if any bundle obscures a
rack position).**

- Frame the densest cable region so the rack positions behind it are as visible
  as possible
- Include at least 2U of recognisable equipment for reference

---

## 2. Why each rule exists

Installers comply with rules they understand, so state the reason:

| Rule | Consequence if broken |
|---|---|
| Both rails fully in frame | Scale cannot be derived; assessment abstains |
| Square to the face | Perspective error propagates directly into U counts |
| No flash | Glare on glossy equipment hides panel edges and labels |
| Door fully open | Door edge is read as an obstruction or hides rack positions |
| Close-up of cable bundles | Obscured U count as `occluded` and widen uncertainty |

---

## 3. Framing overlay (for the installer app)

Enforce compliance at capture rather than rejecting afterwards. The overlay
should show:

- A vertical guide pair the installer aligns to the left and right rails
- Top and bottom edge markers that must both sit inside the frame
- A live tilt indicator, green within ±3° of vertical
- A blocking message when the cabinet outline is not fully contained

Rejecting a photo an hour after the installer has left site costs a return
visit. Rejecting it in the viewfinder costs three seconds.

---

## 4. Metadata — captured automatically, never typed

| Field | Source |
|---|---|
| `site_id` | Work order context |
| `cabinet_id` | Work order context, or QR/asset label on the cabinet |
| `cabinet_type` | Site data record — **not** the installer's judgement |
| `captured_at` | Device clock |

`cabinet_type` supplies `total_u` for the `GEOM-1.0` cross-check. Asking an
installer to type it introduces exactly the error the cross-check exists to
catch.

---

## 5. Automatic quality gate

Evaluated before any assessment. Failure returns a reshoot instruction, not a
verdict.

| Check | Threshold (DRAFT — calibrate in Step 3) |
|---|---|
| Both rails detected over ≥90% of height | required |
| Estimated yaw from square | ≤ 8° |
| Sharpness score | ≥ 0.45 |
| Glare fraction of cabinet face | ≤ 0.20 |
| Cabinet face visible fraction | ≥ 0.85 |
| Shortest cabinet-face dimension | ≥ 1200 px |

Thresholds are placeholders. Set them in Step 3 from the labelled set: pick the
values that separate images a human could assess from ones they could not.

---

## 6. What good and bad look like

Assemble a one-page visual reference from real photographs once the gold set
exists — four compliant examples and six failures, each captioned with the rule
broken and the reshoot instruction. Distribute this to installer teams instead
of this document.

---

## 7. Open questions for sign-off

1. Can the installer app enforce the overlay, or is capture via a generic
   camera app for now?
2. Is `cabinet_id` reliably available from the work order, or is an asset label
   scan needed?
3. Minimum device camera specification across the installer fleet — this sets
   the resolution floor in section 5.
4. Is a torch acceptable on site, or must the standard work under cabinet
   lighting only?
