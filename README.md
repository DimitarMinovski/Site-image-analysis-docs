# Site Image Analysis Service

AI image analysis for site installation use cases. Owned by **Design and User
Experience (DUX)**.

First use case: **cabinet free space** (`CAB-FREE-SPACE`).

---

## Current state: Step 2 complete, Step 3 not started

| Step | What | Status |
|---|---|---|
| 1 | Prerequisites: data approval, model route, ownership | **done** |
| 2 | **The contract**: schemas, rubric, capture standard | **built, awaiting sign-off** |
| 3 | Gold set and evaluation harness | next |
| 4 | Walking skeleton (upload → stub → UI) | |
| 5 | Perception: rectify + scale | |
| 6 | Representation + policy engine | |
| 7 | Judgement layer (VLM) | |
| 8 | Detector, only if needed | |
| 9 | Review UI and feedback loop | |
| 10 | Productionise | |
| 11 | Second use case (RAG arrives here) | |

---

## Layout

```
docs/
  rubrics/CAB-FREE-SPACE.md   the rubric: definitions, clauses, decision table
  capture-standard.md         how photographs must be taken
  labelling-protocol.md       labelling rules + the Step 2 exit gate
schema/
  representation.schema.json  perception output. Policy-free, no verdicts.
  assessment.schema.json      the service's public output contract
examples/
  representation.example.json a worked 42U cabinet
  assessment.example.json     the assessment derived from it
tools/
  validate.mjs                structural + semantic validation
```

```bash
npm install
npm run validate
```

---

## The three ideas this design rests on

**1. Perception and policy are separated by a stored artefact.**
`representation.schema.json` describes what is physically in the cabinet and
contains no notion of "adequate" or "critical". `assessment.schema.json`
describes the judgement. Because the representation is stored, you can revise
the rubric and re-score years of history **without reprocessing a single
image** — and you can unit-test the entire rubric against hand-written
representations with no images at all.

**2. No language model does arithmetic.**
Every number in `measurements` is computed by the policy engine from the U map.
A model may help *perceive* (resolving what sits behind a cable bundle) and may
write the `narrative`, but the verdict is a decision-table lookup with a
`rule_id` recording which row fired. The narrative is generated *from* the
finished verdict, never alongside it — a model asked for both will always
produce a fluent justification, including for wrong verdicts, and reviewers
calibrate on fluency.

**3. The system is allowed to say "I don't know".**
Four U states, not two: `occupied`, `blanked`, `open`, `occluded`. Unknown
hardware counts as occupied, never free — failing open would let a full cabinet
be reported as having room. Abstention is a first-class verdict with a reshoot
instruction. And `not_determinable` states plainly what a single frontal
photograph cannot establish, so a 7U figure is never mistaken for 7U of
installable capacity.

---

## Before Step 3 can start

The rubric thresholds are **placeholders written to make the structure
concrete**, not quoted standards. Two gates:

1. Resolve every open question in `CAB-FREE-SPACE.md` §10 and
   `capture-standard.md` §7 with a domain expert.
2. Run the agreement trial in `labelling-protocol.md` §2 and pass it. Two
   experts labelling 20 images independently must produce the same verdicts.

A gold set labelled against an ambiguous rubric is wrong for the life of the
project — every model you ever evaluate would be measured against noise.

Only then bump the rubric to `1.0.0`, freeze it, and begin labelling.
