-- Add clinic queue details to appointment_snapshots
-- This stores the complete patient queue with statuses

ALTER TABLE appointment_snapshots
ADD COLUMN IF NOT EXISTS clinic_queue_details JSONB DEFAULT '[]'::jsonb;

-- clinic_queue_details structure:
-- [
--   { "number": 1, "status": "完成" },
--   { "number": 2, "status": "完成" },
--   { "number": 4, "status": "保留待診" },
--   ...
-- ]

CREATE INDEX IF NOT EXISTS idx_snapshots_clinic_queue ON appointment_snapshots USING GIN(clinic_queue_details);
