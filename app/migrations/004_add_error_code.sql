-- Migration: Add error_code column to notification_logs for better debugging
-- Date: 2026-02-27
-- Purpose: Track HTTP status codes and error codes for failed notifications

ALTER TABLE notification_logs
ADD COLUMN IF NOT EXISTS error_code INTEGER,
ADD COLUMN IF NOT EXISTS http_status_code INTEGER;

-- Add comment for documentation
COMMENT ON COLUMN notification_logs.error_code IS 'Application-level error code (e.g., LINE API error code)';
COMMENT ON COLUMN notification_logs.http_status_code IS 'HTTP status code from external API (e.g., 400, 401, 500)';
