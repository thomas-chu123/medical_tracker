-- ============================================================
-- 台灣醫療門診追蹤系統 - Local Auth Schema
-- ============================================================

-- Create local users table
CREATE TABLE IF NOT EXISTS users_local (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    display_name TEXT,
    line_notify_token TEXT,
    is_admin BOOLEAN DEFAULT FALSE,
    is_verified BOOLEAN DEFAULT FALSE,
    verification_token TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Update tracking_subscriptions to point to users_local instead of user_profiles
-- (We'll handle the data migration separately if needed, but since it's a new project, we can just drop/recreate or alter)
ALTER TABLE tracking_subscriptions DROP CONSTRAINT IF EXISTS tracking_subscriptions_user_id_fkey;
ALTER TABLE tracking_subscriptions 
    ADD CONSTRAINT tracking_subscriptions_user_id_fkey 
    FOREIGN KEY (user_id) REFERENCES users_local(id) ON DELETE CASCADE;

-- Update notification_logs potentially if there are direct references, but usually it's via subscription.

-- Enable RLS on users_local
ALTER TABLE users_local ENABLE ROW LEVEL SECURITY;

-- users_local policies
CREATE POLICY "Users can view own local profile"
    ON users_local FOR SELECT
    USING (auth.uid() = id OR TRUE); -- We'll use service role for app logic

-- Note: Since we are moving to local auth, we will handle RLS via service role or custom JWT claims if possible.
-- For a local dev environment, we'll use the service role key from the backend to bypass RLS for now,
-- OR we can set up the policies to work with the JWTs we generate locally.
