-- =============================================================================
-- Migration: architecture_agent + passive_components pipeline phases
-- Run manually in Supabase SQL editor (Dashboard > SQL Editor)
--
-- ic_naming_agent is intentionally NOT deleted here — it stays in the table so
-- historical phase_runs rows that reference it keep a valid foreign key. It is
-- removed from the pipeline going forward by filtering on PHASE_ORDER in
-- routers/pipeline.py (list_pipeline_phases), not by deleting the row.
-- =============================================================================

-- TODO: fill in the real n8n_webhook_path for architecture_agent once the
-- workflow is confirmed. passive_components has no workflow yet (kept NULL,
-- same pattern already used for component_selection/netlist before they had one).
INSERT INTO pipeline_phases (id, name, description, order_index, n8n_webhook_path)
VALUES
  ('architecture_agent', 'Architecture Agent',
   'Generates the system block diagram from the selected IC design, for validation in the System Diagram App.',
   0, '/webhook/architecture-agent'),
  ('passive_components', 'Passive Components',
   'Selects passive components (R/C/L) per block from the approved architecture. Workflow still in development.',
   0, '/webhook/passive-components-agent')
ON CONFLICT (id) DO NOTHING;

-- Renumber the active phases into their new order. ic_naming_agent keeps
-- whatever order_index it already has — it no longer matters, since the phase
-- is excluded by id rather than by order_index.
WITH ordered AS (
  SELECT id, ROW_NUMBER() OVER (ORDER BY
    CASE id
      WHEN 'research' THEN 1
      WHEN 'ic_selection' THEN 2
      WHEN 'architecture_agent' THEN 3
      WHEN 'passive_components' THEN 4
      WHEN 'component_selection' THEN 5
      WHEN 'netlist' THEN 6
    END
  ) AS new_order
  FROM pipeline_phases
  WHERE id IN ('research', 'ic_selection', 'architecture_agent', 'passive_components', 'component_selection', 'netlist')
)
UPDATE pipeline_phases p
SET order_index = ordered.new_order
FROM ordered
WHERE p.id = ordered.id;
