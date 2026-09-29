# Clause Authoring

How clauses are written, numbered, implemented and retired.

---

## 1. What a clause is

A clause is the **atomic unit of traceability**. It joins three things that
otherwise live apart:

| | |
|---|---|
| **Authority** | the specification or requirement the rule comes from |
| **Implementation** | the code check or model judgement that evaluates it |
| **Output** | the finding a reviewer or customer reads |

That is the entire point of `BLANK-1.0`. "Non-compliant per BLANK-1.0" can be
looked up, disputed and fixed. "The AI thinks it looks cramped" cannot be.

**Clauses produce findings. The decision table produces the verdict.** These are
separate. Some clauses drive the verdict (`THERMAL-2.1` forces `critical`),
others only ever raise an informational finding (`OCC-1.0`). A clause is not a
row of the decision table, though it may reference one.

---

## 2. Where clauses come from

**Clauses are harvested, not invented.** Every one should trace to an existing
authority:

- installation specifications
- product documentation (CPI), especially per-model thermal clearance
- site design documents
- operator contractual requirements
- DUX design guidelines
- **recurring field root causes that are already written down**

That last source is the richest and the most overlooked. The Site AI Analysis
tab already records cabinet-space root causes: cable bundles consuming ~40% of
free space, unplanned additions taking cabinets to ~95% capacity, less than 2U
airflow clearance, legacy equipment never removed after upgrades. Each is a
clause candidate, because each is recurring, consequential and — mostly —
observable. `OCC-3.0` and `CAP-5.1` in the catalogue are exactly this: harvested
from that data, marked `candidate` until the data source and thresholds are
confirmed.

A clause you invented yourself, with `authority.status: internal`, is
legitimate — but only if you own the requirement. `OCC-1.0` (fail closed on
unknown hardware) is ours. `BLANK-1.0` is not: somebody else's thermal
specification governs it, and that reference must be found.

---

## 3. The admission test

Six questions. A candidate that fails any of them is not yet a clause.

**Observable?** Can it be seen in the available evidence? If not, it becomes a
`flag_only` clause that states a limitation (`DEPTH-3.0`, `CAP-5.0`) rather than
a rule that is silently never evaluated.

**Atomic?** One requirement, one check. If the statement contains "and", split
it into two clauses.

**Decidable?** Would two experts, given the same image and nothing else, reach
the same answer? If not, the clause needs a numeric threshold — that is what
thresholds are *for*.

**Sourced?** Which document mandates this? A clause without an authority is an
opinion with a reference number attached.

**Consequential?** If nothing changes when it is violated, delete it. Clauses
that produce findings nobody acts on train reviewers to ignore all findings.

**Remediable?** What should someone actually do? A finding without a remedy is a
complaint.

---

## 4. Identifiers are permanent

`PREFIX-major.minor`, prefix drawn from the declared domain list.

**An ID is a public contract.** It may already be printed in a customer report
or quoted in a ticket. Therefore:

- **Never renumber.**
- **Never change what an ID means.** Bump the minor version only for
  clarification that cannot change an outcome. If the change *can* alter whether
  a cabinet passes, issue a **new ID** and deprecate the old one.
- Deprecated clauses stay in the catalogue with `status: deprecated` and
  `superseded_by` set, so historical findings remain resolvable.

The test for minor-bump versus new-ID: re-run the clause over the gold set under
both wordings. If any verdict changes, it needed a new ID.

---

## 5. One catalogue, machine-readable

Not one document per clause. A single catalogue, because clauses must be
diffable as a set and they cross-reference each other.

But the catalogue is **JSON, not prose**, because four consumers need to read
clauses programmatically: the policy engine, the review UI, coverage reporting,
and eventually the retrieval layer that makes the model cite clause IDs.

`CAB-FREE-SPACE.clauses.json` is the single source of truth. Section 6 of the
rubric is **generated** from it:

```bash
node tools/clauses.mjs check     # validate
node tools/clauses.mjs render    # regenerate rubric section 6
```

Never hand-edit that table. Generation is what stops the prose and the
implementation drifting apart once a domain expert edits markdown and an
engineer edits code.

---

## 6. The `inputs` field earns its keep

Each clause declares which representation fields it reads. `tools/clauses.mjs
check` verifies every one of them resolves in `representation.schema.json`.

This catches the failure mode where a clause references data the perception
layer never produces. Without the check it would present as a clause that
silently never fires — indistinguishable from a cabinet that is simply compliant.

It is also half of Level 2 closure testing: proof that policy needs nothing the
representation does not carry.

---

## 7. Lifecycle

1. **Authored** from an authority, passing the admission test
2. **Implemented** as a policy-engine check, a VLM judgement, or a flag
3. **Tested** with a fixture that asserts it fires when it should, and does not
   when it should not
4. **Fires in production**, producing a finding with evidence
5. **Reviewed** — confirmed or overridden
6. **Tuned or retired**

### Step 5 is the feedback loop that matters

Track **override rate per clause**. A clause overridden 60% of the time is a bad
clause: either its threshold is wrong or it is not genuinely observable. This is
the single most useful quality signal the catalogue produces, and it costs
nothing beyond recording which clause a reviewer disagreed with.

Expect interpretive clauses (`evaluated_by: vlm_judgement`) to carry a higher
override rate than deterministic ones. Compare each clause against its own
history, not against the others.

### Also track coverage

Which clauses have **never fired**? Either the estate is genuinely compliant, or
the clause is broken, unimplemented, or reading a field perception never
populates. You cannot tell the difference without asking, so ask on a schedule.

---

## 8. Current sign-off blockers

`node tools/clauses.mjs check` reports these. As of catalogue `0.2.0`, five
active clauses have `authority.status: unverified` — `BLANK-1.0`,
`THERMAL-2.1`, `CABLE-4.3`, `DEPTH-3.0`, `ACCESS-6.0`.

`THERMAL-2.1` is the most consequential: it forces a `critical` verdict, and its
clearance figure must come from real per-product documentation. It cannot be
authored generically, because the requirement differs by equipment model.
