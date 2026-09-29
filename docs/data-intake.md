# Data Intake Worksheet

Everything needed from you to move `CAB-FREE-SPACE` from draft `0.1.0` to a
frozen `1.0.0` fit for labelling.

Fill in the `ANSWER:` lines directly in this file and commit it, or hand back the
CSVs in `intake/`. Items marked **BLOCKING** stop labelling; items marked
**LATER** can be resolved during Step 3.

| Priority | Do this |
|---|---|
| 1 | Fill `intake/cabinet-types.csv` and `intake/equipment-catalogue.csv` — pure lookup, no judgement |
| 2 | Run the 20-image agreement trial (§8 below). It answers most of §4, §5 and §7 empirically |
| 3 | Resolve §4, §5, §7 using what the trial surfaced |
| 4 | Chase §6 authorities in parallel — slowest item, start now |

---

## What you do NOT need to provide

Section 3 of the rubric contains the only values that are already settled,
because they come from a published standard (`EIA-310` / `IEC 60297-3-100`):

- 1U = 44.45 mm
- mounting hole pattern 15.875 / 15.875 / 12.7 mm
- 19-inch panel width

These are the basis of the scale measurement and need no input from you.

---

## Section 3 — Reference geometry

### 3.1 Cabinet types in scope — **BLOCKING**

**Needed:** every cabinet type the service will assess, with its properties.
**Why:** `GEOM-1.0` cross-checks measured height against the type record; §without
it, the integrity check that catches scale failures cannot run.
**Format:** `intake/cabinet-types.csv`
**Provider:** site data / cabinet product owner

Columns, with reasons:

| Column | Why it is needed |
|---|---|
| `cabinet_type` | join key against site data |
| `total_u` | the `GEOM-1.0` comparison value |
| `rail_type` | universal / square / threaded — affects hole-pattern detection |
| `rails_visible` | some cabinets cover the rails; those can never satisfy `GEOM-1.1` and will always abstain. Identify them now rather than discovering it in the gold set |
| `usable_depth_mm` | the `DEPTH-3.0` figure, per type |
| `airflow_design` | front-to-back vs bottom-to-top, which may change whether `BLANK-1.0` applies |
| `has_variants` | plinths and extension bays cause legitimate `GEOM-1.0` mismatches |

**ANSWER:** file provided? ☐  · number of types: ____

### 3.2 Which cabinet types are out of scope — **BLOCKING**

**Needed:** any type deliberately excluded, and why.
**Why:** an unlisted type will be assessed anyway and fail confusingly.

**ANSWER:** ______________________________________________

---

## Section 4 — U-state definitions

The 20-image trial will answer most of these faster than discussion will.

### 4.1 Does `blanked` count as available? — **BLOCKING**

The rubric currently says **yes**: a blanking panel is a removable airflow
control, not equipment, so the position is available capacity.

**ANSWER:** confirm yes ☐ · change to no ☐ · reason: ______________

### 4.2 Confirm fail-closed on unknown hardware — **BLOCKING**

The rubric counts unclassifiable hardware as `occupied`, never free, because
failing open would report a full cabinet as having room.

**ANSWER:** confirm ☐ · disagree ☐ · reason: ______________

### 4.3 What exactly counts as `occupied`? — **BLOCKING**

Mark each: occupied / available / other.

| Item | Your answer |
|---|---|
| Equipment | occupied |
| Populated shelf | ______ |
| **Empty** shelf | ______ |
| Horizontal cable manager | ______ |
| Patch panel (in use) | ______ |
| Patch panel (spare ports) | ______ |
| PDU, horizontally mounted | ______ |
| Ventilation gap left by design | ______ |

The empty-shelf row is the one labellers will disagree on. Decide it explicitly.

### 4.4 Zero-U side-rail PDUs — **BLOCKING** (schema gap)

Vertically mounted PDUs occupy no rack units but consume depth and obstruct
access. The schema currently **cannot record them at all** — they silently do
not exist. Proposed fix: a separate `zero_u_occupants[]` array.

**ANSWER:** do these occur in your estate? yes ☐ no ☐ · apply fix? ☐

### 4.5 Rear-mounted equipment behind a front blanking panel — **BLOCKING** (schema gap, highest risk)

The most dangerous gap found. A front blanking panel reads as *available*, but
equipment mounted from the rear makes the position unusable. The service would
report space that cannot be installed into, possibly as `adequate`.

Proposed fix: `rear_state` per U (`unknown` / `occupied` / `clear`), defaulting
to `unknown`, with the rubric treating `blanked` + `rear_state: unknown` as not
usable without a site check.

**ANSWER:** does rear mounting occur? yes ☐ no ☐ · apply fix? ☐

### 4.6 Half-width units sharing one U — **LATER** (schema gap)

Two devices side by side in the same rack unit. The schema has no horizontal
dimension, so the second device disappears. Fix costs complexity everywhere, so
only worth it if this genuinely occurs.

**ANSWER:** occurs? yes ☐ no ☐ rare ☐

### 4.7 Non-integer-height devices — **LATER** (schema gap)

A 1.5U device must round to 2U, losing part of a unit. Recommendation: accept
the rounding and document it as a known bias rather than switching to
millimetre indexing, which complicates everything downstream.

**ANSWER:** accept rounding ☐ · need mm precision ☐

### 4.8 Equipment catalogue — **BLOCKING**

**Needed:** every equipment model that appears in these cabinets.
**Why:** converts a recognition into a measurement, cross-checks geometry, and
supplies the `THERMAL-2.1` clearance requirement per model.
**Format:** `intake/equipment-catalogue.csv`
**Provider:** product data / CPI

**ANSWER:** file provided? ☐ · number of models: ____ · coverage estimate: ____%

---

## Section 5 — Derived quantities

### 5.1 Smallest realistic expansion unit — **BLOCKING**

**This single number sets the §7 thresholds.** If the smallest thing you ever
install is 2U, then a 2U gap is meaningful; if it is 6U, a 2U gap is noise.

**ANSWER:** ____ U

### 5.2 Minimum usable depth for `DEPTH-3.0` — **BLOCKING**

Currently unset. Needs a millimetre figure, per cabinet type if it varies.

**ANSWER:** ____ mm (or per type in the CSV ☐)

### 5.3 Minimum usable run length — **BLOCKING**

Is a single isolated 1U gap counted as usable free space?

**ANSWER:** minimum run to count: ____ U

### 5.4 Should required clearance be excluded from `usable_free_u`? — **BLOCKING**

The rubric currently **excludes** it: U reserved as thermal clearance above a
unit are free but not usable. The worked example does this.

**ANSWER:** confirm ☐ · change ☐

### 5.5 Handling of depth-not-determinable — **BLOCKING**

When depth is unknown (always, from one frontal image), currently the run counts
as usable **and** is flagged. The alternative is to exclude it, which would make
almost every cabinet `critical`.

**ANSWER:** keep flag-and-count ☐ · exclude ☐ · other: __________

### 5.6 Reserved U — **LATER**

Does site design reserve rack units for planned equipment, and if so where does
that data live? Without a source, `reserved_u` stays 0.

**ANSWER:** exists? yes ☐ no ☐ · source system: __________

---

## Section 6 — Clause catalogue

Five active clauses have **unverified authority**. Each needs a real document,
version and section. A clause without an authority is an opinion with a
reference number.

Run `node tools/clauses.mjs check` at any time to see the current list.

| Clause | What to find | Priority |
|---|---|---|
| `THERMAL-2.1` | Per-model top-clearance requirement from CPI. **Most consequential — it forces a `critical` verdict.** Cannot be authored generically | **BLOCKING** |
| `BLANK-1.0` | The thermal or installation spec mandating blanking panels, plus whether it depends on airflow design | **BLOCKING** |
| `DEPTH-3.0` | Spec governing usable depth, plus the figure (see 5.2) | **BLOCKING** |
| `CABLE-4.3` | Cable management spec. Your field data records bundles consuming ~40% of free space — find the governing rule | LATER |
| `ACCESS-6.0` | Safety or installation standard for working clearance | LATER |

**ANSWER — one line per clause:**

```
THERMAL-2.1  document: ____________________ version: ____ section: ____
BLANK-1.0    document: ____________________ version: ____ section: ____
DEPTH-3.0    document: ____________________ version: ____ section: ____
CABLE-4.3    document: ____________________ version: ____ section: ____
ACCESS-6.0   document: ____________________ version: ____ section: ____
```

### 6.6 Candidate clauses — **LATER**

Two clauses were harvested from root causes already recorded in your Site AI
Analysis tab. Both are inactive pending a data source.

- **`OCC-3.0`** decommissioned equipment still installed. Needs a
  decommissioning record to join against. **Where does that live?**
- **`CAP-5.1`** cabinet approaching capacity. Needs an occupancy threshold.

**ANSWER:** OCC-3.0 data source: __________ · CAP-5.1 threshold: ____%

### 6.7 Missing clauses — **BLOCKING**

Review your existing recorded root causes for cabinet space. Anything recurring,
consequential and observable that is not yet a clause?

**ANSWER:** ______________________________________________

---

## Section 7 — Verdict decision table

Every threshold below is a placeholder I invented to make the structure
concrete. **None is an Ericsson standard.**

### 7.1 `usable_free_u` bands — **BLOCKING**

Currently `< 3` → critical, `3..5` → limited, `>= 6` → adequate. Derive from
5.1: roughly, adequate should mean "can take the next expansion comfortably".

**ANSWER:** critical below ____ U · limited ____ to ____ U · adequate from ____ U

### 7.2 `missing_blanking_u` trigger — **BLOCKING**

Currently 3 open units without panels caps the verdict at `limited`.

**ANSWER:** trigger at ____ U · should it ever be `critical`? yes ☐ no ☐

### 7.3 Occlusion abstention threshold — **BLOCKING**

Currently abstain above 6 occluded U. Should this be fixed, or proportional to
cabinet size (e.g. 15% of `total_u`)?

**ANSWER:** fixed at ____ U ☐ · proportional at ____% ☐

### 7.4 Definition of `high` cable obstruction — **BLOCKING**

Currently coverage fraction ≥ 0.5 of the spanned units.

**ANSWER:** ____ (0–1)

### 7.5 Scale confidence floor — **LATER**

Currently abstain below 0.70. Best set empirically in Step 3 from the labelled
set — pick the value separating images a human could assess from ones they
could not.

**ANSWER:** keep 0.70 for now ☐ · set to ____

### 7.6 Confirm rule ordering — **BLOCKING**

Two deliberate choices:

- **Abstention outranks everything.** An unmeasurable cabinet gets a reshoot
  request, never a verdict.
- **Thermal violation outranks free space.** 15U free with no clearance above a
  baseband is still `critical`, because the risk is present now.

**ANSWER:** confirm both ☐ · disagree: ______________

---

## Section 8 — The labelling task

Do this **before** finalising §4, §5 and §7. Disagreements between two labellers
are the fastest way to find which definitions are genuinely ambiguous.

### 8.1 Select 20 images

| Count | Kind |
|---|---|
| 12 | typical, capture-compliant |
| 4 | awkward but assessable — glare, oblique, cables obscuring positions |
| 4 | extreme — one nearly full, one nearly empty, two with unusual contents |

Source from ECO. Record `site_id`, `cabinet_id`, `cabinet_type` for each.

### 8.2 Label independently

Two domain experts, **no discussion, no shared screen**, working only from
`CAB-FREE-SPACE.md`. Use `intake/agreement-trial.csv`.

**If a labeller needs to ask a question, do not answer it — record it.** That
question is a defect in the rubric, and it is the most valuable output of the
exercise.

### 8.3 Pass criteria

| Measure | Target |
|---|---|
| Verdict agreement | ≥ 18 / 20 |
| `usable_free_u` within ±1U | ≥ 17 / 20 |
| `critical` vs `adequate` disagreements | **0** |

The last row is absolute. If one expert says critical and the other says
adequate, the rubric has a structural hole.

### 8.4 On failure

Do **not** negotiate the labels. Amend the rubric so the ambiguity cannot
recur, bump the version, repeat with 20 fresh images. Two or three iterations is
normal.

### 8.5 Then bulk label

Only after the trial passes and §4/§5/§7 are settled: 300–500 images per
`docs/labelling-protocol.md` §4, split **by site** not by image.

**ANSWER:** trial run ☐ · verdict agreement ____/20 · questions raised: ____

---

## Section 9 — Capture standard

Four items from `capture-standard.md` §7, needed before the quality gate can be
tuned.

**ANSWER:**
```
overlay enforceable in installer app?   yes / no / later
cabinet_id available from work order?   yes / no  (else asset label scan needed)
minimum device camera spec across fleet: ____________
torch permitted on site?                yes / no
```

---

## Completion

Step 2 is finished when:

- [ ] `intake/cabinet-types.csv` provided
- [ ] `intake/equipment-catalogue.csv` provided
- [ ] All **BLOCKING** items above answered
- [ ] `node tools/clauses.mjs check` reports no unverified authority on active clauses
- [ ] Agreement trial passed
- [ ] Rubric bumped to `1.0.0` and frozen

Then Step 3 begins: gold set and evaluation harness.
