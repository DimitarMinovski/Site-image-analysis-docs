-- Walking skeleton schema.
--
-- Five invariants are encoded here rather than left to application discipline:
--
--   1. images.sha256 is UNIQUE. The image content is the identity, so
--      re-uploading the same bytes cannot create a second row and every retry
--      path is therefore safe.
--   2. assessments is append-only by convention: re-scoring INSERTs a new row.
--      That is what makes "re-score all history against rubric 1.1" a query
--      instead of a migration. Nothing UPDATEs an assessment.
--   3. representations is a separate table. It is the expensive artefact, so
--      keeping it means a rubric change never has to reprocess pixels.
--   4. reviews are rows, not columns on assessments. Per-clause override rate
--      is the signal that tells us which clauses are wrong, and it only exists
--      if this history survives.
--   5. Version columns on every produced row, so a changed verdict can be
--      attributed to either the cabinet or the rules.

CREATE TABLE IF NOT EXISTS images (
  id            BIGSERIAL PRIMARY KEY,
  sha256        TEXT        NOT NULL UNIQUE,
  storage_key   TEXT        NOT NULL,
  content_type  TEXT        NOT NULL,
  byte_size     BIGINT      NOT NULL,
  site_id       TEXT,
  cabinet_id    TEXT,
  cabinet_type  TEXT,
  width_px      INT,
  height_px     INT,
  captured_at   TIMESTAMPTZ,
  uploaded_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- supports change detection over time for one cabinet
CREATE INDEX IF NOT EXISTS images_cabinet_idx ON images (cabinet_id, uploaded_at DESC);

CREATE TABLE IF NOT EXISTS jobs (
  id            BIGSERIAL PRIMARY KEY,
  image_id      BIGINT      NOT NULL REFERENCES images(id) ON DELETE CASCADE,
  status        TEXT        NOT NULL CHECK (status IN ('queued','running','done','failed','dead')),
  attempts      INT         NOT NULL DEFAULT 0,
  error         TEXT,
  worker_id     TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at    TIMESTAMPTZ,
  finished_at   TIMESTAMPTZ
);
-- the claim query: WHERE status='queued' ORDER BY created_at FOR UPDATE SKIP LOCKED
CREATE INDEX IF NOT EXISTS jobs_claim_idx ON jobs (status, created_at);

CREATE TABLE IF NOT EXISTS representations (
  id                 BIGSERIAL PRIMARY KEY,
  image_id           BIGINT      NOT NULL REFERENCES images(id) ON DELETE CASCADE,
  schema_version     TEXT        NOT NULL,
  perception_version TEXT        NOT NULL,
  doc                JSONB       NOT NULL,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS representations_image_idx ON representations (image_id, created_at DESC);

CREATE TABLE IF NOT EXISTS assessments (
  id                    BIGSERIAL PRIMARY KEY,
  image_id              BIGINT      NOT NULL REFERENCES images(id) ON DELETE CASCADE,
  representation_id     BIGINT      REFERENCES representations(id) ON DELETE SET NULL,
  rubric_id             TEXT        NOT NULL,
  rubric_version        TEXT        NOT NULL,
  policy_engine_version TEXT        NOT NULL,
  perception_version    TEXT,
  model_provider        TEXT,
  model_id              TEXT,
  -- extracted from doc for querying; doc remains the source of truth
  verdict               TEXT        NOT NULL,
  verdict_rule          INT,
  usable_free_u         INT,
  confidence            REAL,
  doc                   JSONB       NOT NULL,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS assessments_image_idx   ON assessments (image_id, created_at DESC);
CREATE INDEX IF NOT EXISTS assessments_verdict_idx ON assessments (verdict);
CREATE INDEX IF NOT EXISTS assessments_rubric_idx  ON assessments (rubric_id, rubric_version);

CREATE TABLE IF NOT EXISTS reviews (
  id                BIGSERIAL PRIMARY KEY,
  assessment_id     BIGINT      NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
  status            TEXT        NOT NULL CHECK (status IN ('confirmed','corrected','rejected')),
  reviewer_id       TEXT,
  corrected_verdict TEXT,
  note              TEXT,
  -- which clause the reviewer disagreed with, when they say so.
  -- This column is what makes per-clause override rate computable.
  disputed_clause   TEXT,
  reviewed_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS reviews_assessment_idx ON reviews (assessment_id, reviewed_at DESC);
CREATE INDEX IF NOT EXISTS reviews_clause_idx     ON reviews (disputed_clause);
