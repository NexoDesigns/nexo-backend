-- =============================================================================
-- Migration: Normativas Module
-- Run in Supabase SQL editor (Dashboard > SQL Editor)
-- =============================================================================

-- ── Task 1: Add normative context columns to projects ─────────────────────────
ALTER TABLE projects
  ADD COLUMN IF NOT EXISTS normative_industry         TEXT,
  ADD COLUMN IF NOT EXISTS normative_client_type      TEXT,
  ADD COLUMN IF NOT EXISTS normative_user_age_range   TEXT,
  ADD COLUMN IF NOT EXISTS normative_target_countries TEXT[],
  ADD COLUMN IF NOT EXISTS normative_extra_context    TEXT;

-- ── Task 2: Create project_normatives join table ──────────────────────────────
CREATE TABLE IF NOT EXISTS project_normatives (
  project_id       UUID        NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  document_id      UUID        NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  selection_source TEXT        NOT NULL DEFAULT 'manual',
  selected_by      UUID        REFERENCES auth.users(id),
  selected_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (project_id, document_id)
);

CREATE INDEX IF NOT EXISTS idx_project_normatives_project  ON project_normatives(project_id);
CREATE INDEX IF NOT EXISTS idx_project_normatives_document ON project_normatives(document_id);

-- ── Task 4: Create normative_runs table ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS normative_runs (
  id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id        UUID        NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  run_number        INT         NOT NULL,
  status            TEXT        NOT NULL DEFAULT 'running',
  custom_prompt     TEXT,
  output_data       JSONB,
  n8n_execution_id  TEXT,
  error_message     TEXT,
  created_by        UUID        REFERENCES auth.users(id),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at      TIMESTAMPTZ,
  duration_seconds  FLOAT
);

CREATE INDEX IF NOT EXISTS idx_normative_runs_project ON normative_runs(project_id);

-- ── Task 3: Update search_documents RPC ──────────────────────────────────────
-- ⚠️  IMPORTANT: Before running this block, go to:
--    Supabase Dashboard > Database > Functions > search_documents > Edit
-- Copy the full existing CREATE OR REPLACE FUNCTION body and paste it here,
-- then add the two changes marked with -- NEW below.
--
-- Changes to make:
--   1. Add parameter: filter_document_ids uuid[] DEFAULT NULL
--   2. Add to WHERE clause: AND (filter_document_ids IS NULL OR d.id = ANY(filter_document_ids))
--      (replace 'd' with the actual alias used for the documents table in your function)
--
-- Example skeleton (adapt to your actual function body):
--
CREATE OR REPLACE FUNCTION search_documents(
  query_embedding    vector(1536),
  match_count        int,
  filter_project_id  uuid  DEFAULT NULL,
  filter_type        text  DEFAULT NULL,
  filter_document_ids uuid[] DEFAULT NULL   -- NEW
)
RETURNS TABLE (...)
LANGUAGE plpgsql AS $$
BEGIN
  RETURN QUERY
  SELECT ...
  FROM document_chunks dc
  JOIN documents d ON d.id = dc.document_id
  WHERE
    (filter_project_id IS NULL OR ...)
    AND (filter_type IS NULL OR d.type = filter_type)
    AND (filter_document_ids IS NULL OR d.id = ANY(filter_document_ids))  -- NEW
  ORDER BY dc.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
