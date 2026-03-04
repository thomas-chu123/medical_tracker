-- Add estimated_wait_minutes to appointment_snapshots
-- This stores the estimated wait time in minutes, computed from speed samples.
-- NULL means "not estimated yet" (insufficient data or hospital provides queue list directly).

ALTER TABLE appointment_snapshots
ADD COLUMN IF NOT EXISTS estimated_wait_minutes NUMERIC(6, 1) DEFAULT NULL;

COMMENT ON COLUMN appointment_snapshots.estimated_wait_minutes IS
    'Estimated minutes until the next appointment, computed from clinic_speed_samples. '
    'NULL if insufficient data or hospital provides a full queue list (e.g. CMUH).';
