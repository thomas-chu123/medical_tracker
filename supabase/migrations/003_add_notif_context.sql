-- Add context fields to notification_logs to preserve notification details
-- even if subscription is deleted or modified

ALTER TABLE notification_logs 
ADD COLUMN IF NOT EXISTS doctor_id UUID,
ADD COLUMN IF NOT EXISTS hospital_id UUID,
ADD COLUMN IF NOT EXISTS clinic_id UUID,
ADD COLUMN IF NOT EXISTS session_date DATE,
ADD COLUMN IF NOT EXISTS session_type TEXT,
ADD COLUMN IF NOT EXISTS current_number INT,
ADD COLUMN IF NOT EXISTS doctor_name TEXT,
ADD COLUMN IF NOT EXISTS hospital_name TEXT,
ADD COLUMN IF NOT EXISTS department_name TEXT,
ADD COLUMN IF NOT EXISTS clinic_room TEXT;

-- Create indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_notif_session_date ON notification_logs(session_date DESC);
CREATE INDEX IF NOT EXISTS idx_notif_doctor ON notification_logs(doctor_id);
