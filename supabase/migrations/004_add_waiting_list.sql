-- Add waiting_list column to appointment_snapshots
-- This stores the real-time queue numbers for each clinic room

ALTER TABLE appointment_snapshots
ADD COLUMN IF NOT EXISTS waiting_list INTEGER[] DEFAULT '{}';

-- Create index for faster queries
CREATE INDEX IF NOT EXISTS idx_snapshots_waiting ON appointment_snapshots(doctor_id, session_date)
WHERE waiting_list IS NOT NULL AND array_length(waiting_list, 1) > 0;
