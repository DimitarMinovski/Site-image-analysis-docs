# Step 4 — Walking Skeleton

Build the thinnest possible end-to-end path with a **stub** analyser, before any
perception work. Integration is where projects of this shape actually die, and
this is the step that de-risks it.

**Done when:** you upload a photo in the browser and see a fake verdict appear,
confirm or override it, and the override persists. After that, every later
improvement is a swap of one component behind a stable interface.

---

## Deviation from the original sketch

The earlier outline said `upload → object store → queue → worker → DB → API → UI`
with SQS as the queue. **Use a `jobs` table in Postgres instead.**

It gives the same seams — enqueue, claim, retry, dead-letter — with one fewer
component to run locally, and it is genuinely adequate in production at this
volume. Introduce SQS when throughput demands it, not before. A skeleton exists
to prove integration, and every extra piece of infrastructure is another thing
that can be broken while you are trying to learn something else.

---

## Architecture

```
  EUI app (existing)                      Python service
  ┌──────────────────┐                    ┌────────────────────────────┐
  │ upload panel     │──POST /images─────▶│ FastAPI                    │
  │ review panel     │──GET  /assessments─│   validates, dedupes,      │
  └──────────────────┘                    │   enqueues                 │
                                          └──────────┬─────────────────┘
                                                     │
                            ┌────────────────────────▼──────────────┐
                            │ Postgres                              │
                            │  images · jobs · representations      │
                            │  assessments · reviews                │
                            └────────────────────────┬──────────────┘
                                                     │ claim
                                          ┌──────────▼─────────────────┐
                            object store  │ worker                     │
                            (fs → S3)  ◀──│   analyser: STUB for now   │
                                          │   validates vs schema      │
                                          └────────────────────────────┘
```

**Language:** Python for the service and worker, because Steps 5–8 (OpenCV,
detectors) live there. The Node tooling in `tools/` stays as dev tooling — the
schemas are JSON, so they are shared without duplication.

**Local first, AWS-ready.** Every external dependency sits behind a port with
two adapters, so deployment is configuration rather than a rewrite:

| Port | Local | AWS |
|---|---|---|
| `Storage` | filesystem | S3 |
| `Database` | Postgres in Docker | RDS / Aurora |
| `Queue` | `jobs` table | same table, or SQS later |
| `Analyser` | **stub** | perception + policy + VLM |

---

## Repo layout

```
service/
  app/
    main.py              FastAPI app, routes only
    config.py            settings from env
    db.py                connection + migrations runner
    models.py            row <-> dict mapping
    routes/
      images.py          POST /images, GET /images/{sha}
      assessments.py     GET /assessments, GET /assessments/{id}
      reviews.py         POST /assessments/{id}/review
      health.py          /healthz, /readyz
    ports/
      storage.py         Storage protocol + LocalStorage + S3Storage
      analyser.py        Analyser protocol + StubAnalyser
    validation.py        JSON Schema validation against ../schema/*.json
  worker/
    run.py               claim loop
  migrations/
    001_init.sql
  tests/
    test_e2e.py          the smoke test that defines "done"
  pyproject.toml
  docker-compose.yml     postgres only
```

---

## TODO

### Phase A — foundations

- [ ] **A1** `docker-compose.yml` with Postgres 16 only. One command to start.
- [ ] **A2** `migrations/001_init.sql` with the schema below. Plain SQL, applied
      by a tiny runner — no ORM migrations framework yet.
- [ ] **A3** `config.py` reading from env: `DATABASE_URL`, `STORAGE_BACKEND`,
      `STORAGE_ROOT` / `S3_BUCKET`, `API_TOKEN`. No secrets in code.
- [ ] **A4** `ports/storage.py`: `Storage` protocol with `put(key, bytes)`,
      `get(key)`, `exists(key)`. Implement `LocalStorage` now, leave
      `S3Storage` as a stub raising `NotImplementedError`.
- [ ] **A5** `validation.py` loading `schema/representation.schema.json` and
      `schema/assessment.schema.json`, exposing `validate_assessment(doc)`.
      Reuse the existing schemas — do not restate them in Python.

### Phase B — ingest

- [ ] **B1** `POST /images` accepting multipart upload plus `site_id`,
      `cabinet_id`, `cabinet_type`.
- [ ] **B2** Compute SHA-256 of the bytes. **Idempotency:** if that hash already
      exists, return the existing image and its latest assessment. Do **not**
      create a second job. Makes retries and double-taps safe.
- [ ] **B3** Validate the upload is genuinely an image: check magic bytes, not
      the filename or declared content type. Enforce a size cap and minimum
      dimensions.
- [ ] **B4** Write bytes to `Storage` under `images/{sha256[:2]}/{sha256}`.
      Content-addressed, so it is naturally deduplicated.
- [ ] **B5** Insert `images` row, then insert a `jobs` row with
      `status='queued'`. Same transaction.
- [ ] **B6** Return `202` with the image sha and job id.

### Phase C — worker and stub

- [ ] **C1** Claim loop using `SELECT ... FOR UPDATE SKIP LOCKED` so multiple
      workers are safe from day one.
- [ ] **C2** `StubAnalyser` returning a hardcoded but **schema-valid**
      assessment. Derive the verdict from the sha — see the note below.
- [ ] **C3** Validate the analyser's output against
      `assessment.schema.json` **before** writing. On failure, mark the job
      `failed` with the validation error. This is what keeps the contract
      honest once a real analyser arrives.
- [ ] **C4** Insert `representations` and `assessments` rows. Stamp
      `rubric_version`, `perception_version`, `policy_engine_version`.
- [ ] **C5** Mark the job `done`. On exception: increment `attempts`, and after
      3 attempts set `status='dead'` with the error text retained.
- [ ] **C6** Structured JSON logs including `job_id` and image sha on every line.

> **C2 matters more than it looks.** Make the stub return a *different* verdict
> depending on the image hash, cycling through `adequate`, `limited`,
> `critical`, `abstained` and `borderline`. Teams build the UI against the happy
> path and then discover that abstention has nowhere to render and borderline has
> no visual treatment. Exercising all five states now costs nothing and forces the
> UI to be honest.

### Phase D — read API

- [ ] **D1** `GET /assessments?cabinet_id=&verdict=&status=` with pagination.
- [ ] **D2** `GET /assessments/{id}` returning the full assessment document,
      the representation, and review state.
- [ ] **D3** `GET /images/{sha}/bytes` streaming the original, for the UI to
      display. Later becomes a presigned URL rather than proxied bytes.
- [ ] **D4** `POST /assessments/{id}/review` with `status`
      (`confirmed` / `corrected` / `rejected`), optional `corrected_verdict`,
      optional note. **Append a `reviews` row; never mutate the assessment.**
- [ ] **D5** `/healthz` (process alive) and `/readyz` (DB and storage reachable).

### Phase E — UI panel in the existing EUI app

- [ ] **E1** New tab in the app, alongside Site AI Analysis. Two views: an upload
      form and a results list.
- [ ] **E2** Upload view: file picker, site/cabinet fields, submit, show job
      accepted.
- [ ] **E3** List view: cabinet, verdict badge, confidence, review status. Filter
      by verdict.
- [ ] **E4** Detail view: the image, the measurements table, `free_runs` with
      exclusion reasons, findings with cited clause IDs, and the narrative.
- [ ] **E5** Render **all five** verdict states. `abstained` must show the
      `reshoot_instruction` prominently rather than an empty verdict badge, and
      `borderline` needs its own treatment.
- [ ] **E6** Review controls: Confirm / Correct / Reject, posting to D4 and
      reflecting the result.
- [ ] **E7** Show `not_determinable` explicitly on the detail view, so a free-U
      figure is never read as installable capacity.
- [ ] **E8** Sort out CORS. The app is served from `:3000` and the API from
      `:8000`, so the browser will block requests until the API sets
      `Access-Control-Allow-Origin` for the dev origin. Expect to lose an hour
      here if unprepared.

### Phase F — proof and hygiene

- [ ] **F1** `tests/test_e2e.py`: upload a fixture image, poll until the job
      completes, assert an assessment exists and validates, post a review,
      assert it persisted.
- [ ] **F2** Idempotency test: upload the same bytes twice, assert one image row
      and one job.
- [ ] **F3** Bad-output test: force the analyser to return an invalid document,
      assert the job is marked `failed` and nothing is written to `assessments`.
- [ ] **F4** `make dev` or equivalent: compose up, migrate, run API, run worker.
- [ ] **F5** `README` section: how to run it, and the swap points for later steps.

---

## Data model

```sql
CREATE TABLE images (
  id            BIGSERIAL PRIMARY KEY,
  sha256        TEXT NOT NULL UNIQUE,          -- idempotency key
  storage_key   TEXT NOT NULL,
  site_id       TEXT,
  cabinet_id    TEXT,
  cabinet_type  TEXT,
  width_px      INT,
  height_px     INT,
  captured_at   TIMESTAMPTZ,
  uploaded_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON images (cabinet_id, uploaded_at DESC);   -- change detection later

CREATE TABLE jobs (
  id            BIGSERIAL PRIMARY KEY,
  image_id      BIGINT NOT NULL REFERENCES images(id),
  status        TEXT NOT NULL CHECK (status IN ('queued','running','done','failed','dead')),
  attempts      INT NOT NULL DEFAULT 0,
  error         TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at    TIMESTAMPTZ,
  finished_at   TIMESTAMPTZ
);
CREATE INDEX ON jobs (status, created_at);               -- the claim query

CREATE TABLE representations (
  id                  BIGSERIAL PRIMARY KEY,
  image_id            BIGINT NOT NULL REFERENCES images(id),
  schema_version      TEXT NOT NULL,
  perception_version  TEXT NOT NULL,
  doc                 JSONB NOT NULL,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE assessments (
  id                     BIGSERIAL PRIMARY KEY,
  image_id               BIGINT NOT NULL REFERENCES images(id),
  representation_id      BIGINT REFERENCES representations(id),
  rubric_id              TEXT NOT NULL,
  rubric_version         TEXT NOT NULL,
  policy_engine_version  TEXT NOT NULL,
  verdict                TEXT NOT NULL,      -- extracted for querying
  usable_free_u          INT,                -- extracted for querying
  doc                    JSONB NOT NULL,     -- the whole assessment
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON assessments (image_id, created_at DESC);
CREATE INDEX ON assessments (verdict);

CREATE TABLE reviews (
  id                 BIGSERIAL PRIMARY KEY,
  assessment_id      BIGINT NOT NULL REFERENCES assessments(id),
  status             TEXT NOT NULL CHECK (status IN ('confirmed','corrected','rejected')),
  reviewer_id        TEXT,
  corrected_verdict  TEXT,
  note               TEXT,
  reviewed_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### Five invariants worth honouring now

**Content-addressed and idempotent.** The image SHA is the identity. Re-uploading
is free and safe, which makes every retry path simple.

**Assessments are append-only.** Never `UPDATE` one. Re-scoring inserts a new
row. That is what makes "re-score history against rubric 1.1" a query rather
than a migration.

**Representations are stored separately.** They are the expensive artefact.
Keeping them means a rubric change never requires reprocessing pixels.

**Reviews are separate rows, not columns.** A review is a human act *on* an
assessment, not a mutation of it. Per-clause override rate — the quality signal
that tells you which clauses are wrong — is only computable if this history
survives.

**Version columns, not a config file.** `rubric_version`,
`perception_version`, `policy_engine_version` on every row. When a verdict
changes you must be able to say whether the cabinet changed or the rules did.

---

## Security — do these in the skeleton, not later

- [ ] **S1** The upload endpoint **must** require authentication. An open
      endpoint that accepts files and writes them to storage is a hole, even in
      a prototype. A static bearer token from env is enough for now; note it as
      interim.
- [ ] **S2** Bind the API to `127.0.0.1` for local development. Do not expose it
      on `0.0.0.0` "just for testing".
- [ ] **S3** Validate image content by magic bytes, enforce a size cap, and cap
      decoded dimensions to avoid decompression-bomb images.
- [ ] **S4** Never log image bytes or full storage paths with customer
      identifiers. Log the SHA.
- [ ] **S5** Before any AWS deployment: encryption at rest on the bucket, block
      public access, region pinned to whatever your data approval specified, and
      a retention policy. Site photographs are customer infrastructure imagery.

---

## What NOT to build in Step 4

Resisting these is what keeps the skeleton thin:

- No perception. No OpenCV, no rectification, no scale detection.
- No real policy engine. The stub returns a canned document.
- No VLM. No model calls of any kind.
- No authentication system. One static token.
- No SQS, no Lambda, no Step Functions, no Kubernetes.
- No detector, no training, no GPU.
- No retrieval layer.

Each of those is a later step that swaps exactly one component.

---

## Definition of done

Demonstrable in a browser, end to end:

1. Upload a cabinet photo with site and cabinet IDs → job accepted
2. Within seconds, an assessment appears in the list with a verdict badge
3. Open it → image, measurements, findings with clause IDs, narrative,
   `not_determinable` section
4. Confirm or override → the review persists and is visible on reload
5. Re-upload the same file → no duplicate, existing assessment returned
6. A stub image that yields `abstained` → UI shows the reshoot instruction
7. `tests/test_e2e.py` passes from a clean `docker compose up`

At that point the interfaces are proven and Step 5 becomes: replace
`StubAnalyser` with something real.
