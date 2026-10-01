# Service — Walking Skeleton

End-to-end path for `CAB-FREE-SPACE` with a **stub** analyser. No perception, no
model calls. The point is to prove the integration seams, so that Steps 5–7 each
replace exactly one component.

**Status:** Phases A, B, C, D and F complete and verified. Phase E (browser UI in
the EUI app) outstanding.

---

## Run it

```bash
cd service
make db        # start postgres, create siteimg
make venv      # python 3.12 venv + deps
make migrate
make api       # terminal 1  -> http://127.0.0.1:8000
make worker    # terminal 2
make test      # 8 tests
```

Postgres comes from Homebrew (`postgresql@16`); `docker-compose.yml` is there if
you prefer Docker. The app only needs `DATABASE_URL`, so either works.

Quick exercise:

```bash
TOKEN=dev-token-change-me
curl -X POST http://127.0.0.1:8000/images \
  -H "Authorization: Bearer $TOKEN" \
  -F file=@cabinet.jpg -F site_id=SITE-ECHO-11 \
  -F cabinet_id=CAB-1 -F cabinet_type=BYB-501-42U

curl http://127.0.0.1:8000/assessments -H "Authorization: Bearer $TOKEN"
curl http://127.0.0.1:8000/stats
```

---

## Layout

```
app/
  config.py              all settings from env, no secret defaults
  db.py                  psycopg + migrations; the claim query lives here
  validation.py          the contract gate: schema + semantic invariants
  main.py                FastAPI app, CORS, bearer auth
  ports/
    storage.py           Storage: LocalStorage | S3Storage
    analyser.py          Analyser: StubAnalyser | PipelineAnalyser
    model.py             ModelClient: NullModel | BedrockModel | OpenAIModel
  routes/                health, images, assessments
worker/run.py            claim loop, validation gate, structured logs
migrations/001_init.sql  five tables
tests/test_e2e.py        F1 end-to-end, F2 idempotency, F3 the gate
```

---

## Endpoints

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/healthz` | no | process alive |
| GET | `/readyz` | no | db, schemas, storage + active config |
| GET | `/stats` | no | row counts and **per-clause override rate** |
| POST | `/images` | yes | multipart upload; `202` new, `200` duplicate |
| GET | `/images/{sha}` | yes | metadata, job state, latest assessment |
| GET | `/images/{sha}/bytes` | yes | original image |
| GET | `/assessments` | yes | filter by `cabinet_id`, `verdict` |
| GET | `/assessments/{id}` | yes | assessment + representation + reviews |
| POST | `/assessments/{id}/review` | yes | appends a review row |

---

## The four properties worth knowing

**Idempotent by image SHA-256.** Re-uploading the same bytes returns the
existing record and creates no second job, so every retry path is safe. Verified
by `test_f2`.

**The validation gate guards the database.** Analyser output is checked against
both JSON Schemas *and* the semantic invariants before anything is written. A
bad document produces a failed job with the reason retained and **zero rows**.
Verified by `test_f3`, which feeds in a deliberately inconsistent document and
asserts nothing was persisted.

**The stub exercises all five verdict states.** Scenario is chosen from the image
SHA, cycling `adequate`, `limited`, `critical`, `borderline`, `abstained`. Teams
build a UI against the happy path and then find abstention has nowhere to render.
Every scenario is also asserted to satisfy the full contract.

**Reviews are rows, not columns.** An assessment is never mutated. `/stats`
already reports per-clause dispute counts, so the signal that tells you which
clauses are wrong accumulates from day one instead of being retrofitted.

---

## Moving to AWS

Configuration only. No call site changes.

```bash
DATABASE_URL=postgresql://user:pass@...rds.amazonaws.com:5432/siteimg
STORAGE_BACKEND=s3
S3_BUCKET=...
AWS_REGION=eu-north-1
pip install -e '.[aws]'
```

Before anything reachable by more than one person:

- Replace the static bearer token with the real identity provider. It is an
  interim measure and labelled as such in `main.py`.
- Bucket: default encryption, public access blocked, region pinned to whatever
  the data approval specified, retention policy set. Site photographs are
  customer infrastructure imagery.
- `/images/{sha}/bytes` should become a presigned S3 URL
  (`S3Storage.presign_get` already exists) so image bytes stop traversing the API.
- Keep the `jobs` table unless throughput demands SQS. It provides the same
  seams — enqueue, claim, retry, dead-letter — with one fewer component.

---

## Enabling a model for Steps 5–7

```bash
MODEL_PROVIDER=bedrock   MODEL_ID=...   # pip install -e '.[aws]'
MODEL_PROVIDER=openai    MODEL_ID=...   # pip install -e '.[openai]'
```

The contract is one method:

```python
describe_image(image_bytes, prompt, json_schema) -> dict
```

Bytes in, validated JSON out, nothing provider-specific past the boundary. That
is what lets the evaluation harness benchmark a new model by changing one
environment variable and re-running against the gold set — so "a new model is
available" becomes an afternoon's measurement rather than a rebuild.

`NullModel` is the default and raises with instructions rather than returning
something plausible.

---

## What is deliberately absent

No perception, no real policy engine, no model calls, no SQS, no auth system, no
detector, no retrieval layer. Each is a later step that swaps one component.

Resisting these is what made the skeleton finishable.

---

## Outstanding

**Phase E** — the review panel in the EUI app: upload form, assessment list,
detail view with findings and cited clauses, review controls, and treatments for
all five verdict states. `abstained` must show the reshoot instruction, and
`borderline` needs its own visual treatment. CORS is already configured for
`localhost:3000`.
