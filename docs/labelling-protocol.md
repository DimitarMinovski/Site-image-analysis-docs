# Labelling Protocol and the Step 2 Exit Gate

| | |
|---|---|
| **Version** | `0.1.0` |
| **Owner** | DUX |
| **Purpose** | Define how images are labelled, and prove the rubric is unambiguous before bulk labelling starts |

---

## 1. Why this document exists

Step 2 is not finished when the rubric is written. It is finished when **two
domain experts, labelling the same images independently from the rubric alone,
produce the same answers.**

If they disagree, the rubric is ambiguous. No model can resolve an ambiguity
that humans cannot, and a gold set labelled against an ambiguous rubric is
wrong for the lifetime of the project — every model you ever evaluate will be
measured against noise.

This is the cheapest test in the entire programme and the one most often
skipped.

---

## 2. The agreement trial

**Setup.** Select 20 images spanning the range: roughly 12 typical, 4 awkward
(glare, oblique, cables obscuring positions), 4 extreme (nearly full, nearly
empty).

**Method.** Two experts label all 20 **independently**, from
`CAB-FREE-SPACE.md` only. No discussion, no shared screen, no worked examples
beyond what the rubric contains. If a labeller needs to ask a question, that
question is a defect in the rubric — record it rather than answering it.

**Record per image:** `total_u`, `occupied_u`, `blanked_u`, `open_u`,
`occluded_u`, `usable_free_u`, `verdict`, and free-text notes.

---

## 3. Pass criteria

| Measure | Target |
|---|---|
| Verdict agreement | ≥ 18 / 20 |
| `usable_free_u` agreement within ±1U | ≥ 17 / 20 |
| Disagreements traceable to a named rubric ambiguity | 100% |
| `critical` vs `adequate` disagreements | **0** |

That last row is absolute. If one expert says a cabinet is critical and the
other says it is adequate, the rubric has a structural hole. Fix it and re-run
the trial.

**On failure:** do not negotiate the labels. Amend the rubric so the ambiguity
cannot recur, bump its version, and repeat with 20 fresh images. Two or three
iterations is normal and healthy.

---

## 4. Bulk labelling, after the gate passes

**Volume.** 300–500 images. Composition:

| Class | Share | Why |
|---|---|---|
| Typical, capture-compliant | ~55% | The working case |
| Hard but assessable | ~20% | Where accuracy is actually won |
| Should abstain | ~10% | Proves the service declines correctly |
| Near-full / near-empty | ~15% | Exercises both ends of the decision table |

Deliberately including images that **should** abstain is important. A service
that never declines is untrustworthy, and you cannot measure abstention without
labelled examples of it.

**Split.** 60% train / 20% dev / 20% test. Split by **site**, not by image —
several photos of the same cabinet across the split would leak.

Hold the test set back. Look at it rarely and never tune against it.

**Tooling.** Label Studio or CVAT, self-hosted. Not a spreadsheet: you are
labelling per-U states and bounding boxes, which spreadsheets handle badly.

**Per-U labelling.** Label every U position with one of the four states from
rubric section 4. `occluded` must be available and used honestly — a labeller
guessing behind a cable bundle corrupts the ground truth in exactly the place
the model most needs a reliable reference.

---

## 5. Second-pass audit

Have a third expert re-label a random 10% of the bulk set. This measures label
drift over the labelling period, which is real: attention and interpretation
both move over several hundred images. Report it alongside model accuracy —
**your model cannot beat your label noise**, and knowing the noise floor stops
you chasing accuracy that does not exist.

---

## 6. Deliverables of Step 2

- [ ] `CAB-FREE-SPACE.md` reviewed, section 10 open questions all resolved
- [ ] `capture-standard.md` reviewed, section 7 open questions all resolved
- [ ] `representation.schema.json` and `assessment.schema.json` validated
- [ ] Agreement trial run and **passed**
- [ ] Rubric version bumped to `1.0.0` and frozen for labelling
- [ ] Labelling tool deployed with the per-U schema configured

Only then start Step 3.
