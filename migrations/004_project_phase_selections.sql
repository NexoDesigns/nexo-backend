-- =============================================================================
-- Migration: Project Phase Selections
-- Run in Supabase SQL editor (Dashboard > SQL Editor)
--
-- Persists which output items of a phase's active run the user has chosen to
-- send forward, e.g.:
--   phase_id = 'research'      → selected research solution ids  (→ IC Selection)
--   phase_id = 'ic_selection'  → [selected design id]            (→ Architecture Agent)
-- One row per (project, phase). The selection is only valid for source_run_id;
-- when the phase's active run changes the frontend falls back to its default.
-- =============================================================================

-- ── Table ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS project_phase_selections (
  project_id     UUID        NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  phase_id       TEXT        NOT NULL,
  source_run_id  UUID        NOT NULL REFERENCES phase_runs(id) ON DELETE CASCADE,
  selected_ids   JSONB       NOT NULL DEFAULT '[]',
  updated_by     UUID        REFERENCES auth.users(id),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (project_id, phase_id)
);

-- ── RLS ───────────────────────────────────────────────────────────────────────
-- The backend uses the service role (bypasses RLS). This policy mirrors the
-- current access model: every authenticated user can access every project.
ALTER TABLE project_phase_selections ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Authenticated users manage phase selections"
  ON project_phase_selections
  FOR ALL
  TO authenticated
  USING (true)
  WITH CHECK (true);
