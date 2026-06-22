-- =============================================================================
-- Migration: Custom Phase Output Items
-- Run in Supabase SQL editor (Dashboard > SQL Editor)
-- =============================================================================

-- ── Table ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS custom_phase_output_items (
  id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id        UUID        NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  phase_id          TEXT        NOT NULL,
  source_run_id     UUID        NOT NULL REFERENCES phase_runs(id) ON DELETE CASCADE,
  source_item_id    TEXT        NOT NULL,
  source_item_label TEXT        NOT NULL,
  data              JSONB       NOT NULL DEFAULT '{}',
  created_by        UUID        REFERENCES auth.users(id),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_custom_outputs_run    ON custom_phase_output_items(source_run_id);
CREATE INDEX IF NOT EXISTS idx_custom_outputs_project ON custom_phase_output_items(project_id, phase_id);

-- ── Auto-update updated_at ────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION set_custom_output_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_custom_output_updated_at
BEFORE UPDATE ON custom_phase_output_items
FOR EACH ROW EXECUTE FUNCTION set_custom_output_updated_at();

-- ── RLS ───────────────────────────────────────────────────────────────────────
ALTER TABLE custom_phase_output_items ENABLE ROW LEVEL SECURITY;

-- Users can manage their own items
CREATE POLICY "Users manage own custom outputs"
  ON custom_phase_output_items
  FOR ALL
  USING (
    created_by = auth.uid()
    OR project_id IN (
      SELECT id FROM projects WHERE owner_id = auth.uid()
    )
  )
  WITH CHECK (
    created_by = auth.uid()
    OR project_id IN (
      SELECT id FROM projects WHERE owner_id = auth.uid()
    )
  );