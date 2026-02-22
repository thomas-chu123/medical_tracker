-- ============================================================
-- 醫療門診追蹤系統 - Supabase Database Schema
-- Run this in Supabase SQL Editor
-- ============================================================

-- Enable UUID extension (should already be enabled in Supabase)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- 1. 醫院 hospitals
-- ============================================================
CREATE TABLE IF NOT EXISTS hospitals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    code TEXT UNIQUE NOT NULL,
    base_url TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Insert CMUH as the first hospital
INSERT INTO hospitals (name, code, base_url) VALUES
    ('中國醫藥大學附設醫院', 'CMUH', 'https://www.cmuh.cmu.edu.tw')
ON CONFLICT (code) DO NOTHING;

-- ============================================================
-- 2. 科別 departments
-- ============================================================
CREATE TABLE IF NOT EXISTS departments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hospital_id UUID NOT NULL REFERENCES hospitals(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    code TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(hospital_id, code)
);

CREATE INDEX IF NOT EXISTS idx_departments_hospital ON departments(hospital_id);

-- ============================================================
-- 3. 醫師 doctors
-- ============================================================
CREATE TABLE IF NOT EXISTS doctors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hospital_id UUID NOT NULL REFERENCES hospitals(id) ON DELETE CASCADE,
    department_id UUID REFERENCES departments(id),
    doctor_no TEXT NOT NULL,
    name TEXT NOT NULL,
    specialty TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(hospital_id, doctor_no)
);

CREATE INDEX IF NOT EXISTS idx_doctors_hospital ON doctors(hospital_id);
CREATE INDEX IF NOT EXISTS idx_doctors_department ON doctors(department_id);

-- ============================================================
-- 4. 掛號快照 appointment_snapshots
-- ============================================================
CREATE TABLE IF NOT EXISTS appointment_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doctor_id UUID NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    department_id UUID REFERENCES departments(id),
    session_date DATE NOT NULL,
    session_type TEXT,              -- '上午' / '下午' / '晚上'
    clinic_room TEXT,               -- 診間號碼
    total_quota INTEGER,            -- 總掛號名額
    current_registered INTEGER,     -- 已掛號人數
    current_number INTEGER,         -- 目前叫號號碼 (門診進度)
    remaining INTEGER               -- 剩餘可掛號數
        GENERATED ALWAYS AS (
            CASE WHEN total_quota IS NOT NULL AND current_registered IS NOT NULL
                 THEN total_quota - current_registered
                 ELSE NULL
            END
        ) STORED,
    is_full BOOLEAN DEFAULT FALSE,
    status TEXT,                    -- '看診中' / '結束' / '未開診' etc.
    scraped_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_snapshots_doctor_date ON appointment_snapshots(doctor_id, session_date);
CREATE INDEX IF NOT EXISTS idx_snapshots_scraped ON appointment_snapshots(scraped_at DESC);

-- ============================================================
-- 5. 使用者設定檔 user_profiles (extends Supabase auth.users)
-- ============================================================
CREATE TABLE IF NOT EXISTS user_profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    display_name TEXT,
    line_notify_token TEXT,
    is_admin BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- 6. 使用者追蹤訂閱 tracking_subscriptions
-- ============================================================
CREATE TABLE IF NOT EXISTS tracking_subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    doctor_id UUID NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    department_id UUID REFERENCES departments(id),
    session_date DATE NOT NULL,
    session_type TEXT,
    -- 通知門檻設定
    notify_at_20 BOOLEAN DEFAULT TRUE,
    notify_at_10 BOOLEAN DEFAULT TRUE,
    notify_at_5  BOOLEAN DEFAULT TRUE,
    -- 通知管道
    notify_email BOOLEAN DEFAULT TRUE,
    notify_line  BOOLEAN DEFAULT FALSE,
    -- 已通知狀態 (防止重複發送)
    notified_20  BOOLEAN DEFAULT FALSE,
    notified_10  BOOLEAN DEFAULT FALSE,
    notified_5   BOOLEAN DEFAULT FALSE,
    is_active    BOOLEAN DEFAULT TRUE,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, doctor_id, session_date, session_type)
);

CREATE INDEX IF NOT EXISTS idx_subs_user ON tracking_subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_subs_doctor ON tracking_subscriptions(doctor_id, session_date);

-- ============================================================
-- 7. 通知紀錄 notification_logs
-- ============================================================
CREATE TABLE IF NOT EXISTS notification_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subscription_id UUID NOT NULL REFERENCES tracking_subscriptions(id) ON DELETE CASCADE,
    threshold INTEGER NOT NULL,     -- 20, 10, or 5
    channel TEXT NOT NULL,          -- 'email' or 'line'
    recipient TEXT,                 -- email address or LINE display name
    message TEXT,
    sent_at TIMESTAMPTZ DEFAULT NOW(),
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_notif_sub ON notification_logs(subscription_id);

-- ============================================================
-- 8. Row Level Security (RLS) Policies
-- ============================================================

-- Enable RLS on user tables
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE tracking_subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE notification_logs ENABLE ROW LEVEL SECURITY;

-- user_profiles: users can only read/write their own profile
CREATE POLICY "Users can view own profile"
    ON user_profiles FOR SELECT
    USING (auth.uid() = id);

CREATE POLICY "Users can update own profile"
    ON user_profiles FOR UPDATE
    USING (auth.uid() = id);

CREATE POLICY "Users can insert own profile"
    ON user_profiles FOR INSERT
    WITH CHECK (auth.uid() = id);

-- tracking_subscriptions: users manage their own
CREATE POLICY "Users manage own subscriptions"
    ON tracking_subscriptions FOR ALL
    USING (auth.uid() = user_id);

-- notification_logs: users can view their own
CREATE POLICY "Users view own notifications"
    ON notification_logs FOR SELECT
    USING (
        auth.uid() = (
            SELECT user_id FROM tracking_subscriptions
            WHERE id = notification_logs.subscription_id
        )
    );

-- Public read access for hospitals, departments, doctors, snapshots
ALTER TABLE hospitals ENABLE ROW LEVEL SECURITY;
ALTER TABLE departments ENABLE ROW LEVEL SECURITY;
ALTER TABLE doctors ENABLE ROW LEVEL SECURITY;
ALTER TABLE appointment_snapshots ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public read hospitals" ON hospitals FOR SELECT USING (TRUE);
CREATE POLICY "Public read departments" ON departments FOR SELECT USING (TRUE);
CREATE POLICY "Public read doctors" ON doctors FOR SELECT USING (TRUE);
CREATE POLICY "Public read snapshots" ON appointment_snapshots FOR SELECT USING (TRUE);

-- ============================================================
-- 9. Updated_at trigger function
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_hospitals_updated_at BEFORE UPDATE ON hospitals
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_doctors_updated_at BEFORE UPDATE ON doctors
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_user_profiles_updated_at BEFORE UPDATE ON user_profiles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_subs_updated_at BEFORE UPDATE ON tracking_subscriptions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
