-- ============================================================
-- Migration 009: Add clinic_speed_samples for doctor speed learning
-- Stores per-poll observations of call speed (號/分鐘) per doctor per session.
-- Used to estimate wait times for hospitals that don't provide queue lists (e.g. HMMH).
-- ============================================================

CREATE TABLE IF NOT EXISTS clinic_speed_samples (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doctor_id       UUID NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    session_date    DATE NOT NULL,
    session_type    TEXT NOT NULL,          -- '上午' / '下午' / '晚上'
    sample_at       TIMESTAMPTZ NOT NULL,   -- 本次 snapshot 的時間
    prev_at         TIMESTAMPTZ NOT NULL,   -- 上次 snapshot 的時間
    prev_number     INTEGER NOT NULL,       -- 上次的叫號
    curr_number     INTEGER NOT NULL,       -- 本次的叫號
    delta_calls     INTEGER NOT NULL,       -- curr_number - prev_number  (≥ 1)
    delta_minutes   NUMERIC(7, 3) NOT NULL, -- 時間差（分鐘）
    calls_per_min   NUMERIC(7, 4) NOT NULL  -- delta_calls / delta_minutes
        GENERATED ALWAYS AS (delta_calls::numeric / NULLIF(delta_minutes, 0)) STORED,
    hospital_code   TEXT NOT NULL           -- 快速過濾用 (e.g. 'HMMH')
);

-- Index for fast per-doctor lookups ordered by recency
CREATE INDEX IF NOT EXISTS idx_speed_doctor_date
    ON clinic_speed_samples (doctor_id, session_date, session_type, sample_at DESC);

-- Index for hospital-wide cleanup queries
CREATE INDEX IF NOT EXISTS idx_speed_hospital
    ON clinic_speed_samples (hospital_code, session_date);

-- Auto-expire rows older than 60 days via a cleanup function (called by scheduler)
-- We deliberately KEEP historical records so speed improves over time.
-- Use this view to get the effective average speed per doctor/session:
CREATE OR REPLACE VIEW v_doctor_avg_speed AS
SELECT
    doctor_id,
    session_type,
    ROUND(AVG(calls_per_min)::numeric, 4)   AS avg_calls_per_min,
    ROUND(1.0 / NULLIF(AVG(calls_per_min), 0), 2) AS avg_mins_per_call,
    COUNT(*)                                 AS sample_count,
    MAX(sample_at)                           AS last_sample_at
FROM clinic_speed_samples
WHERE sample_at > NOW() - INTERVAL '30 days'   -- Only use recent data
GROUP BY doctor_id, session_type;

-- RLS: public read (owned by service-role writes via backend)
ALTER TABLE clinic_speed_samples ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read speed samples"
    ON clinic_speed_samples FOR SELECT USING (TRUE);
