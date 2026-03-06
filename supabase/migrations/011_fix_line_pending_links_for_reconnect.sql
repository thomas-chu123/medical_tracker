-- ============================================================
-- Migration 011: Fix line_pending_links for reconnect flow
-- 
-- Changes:
--   1. Make line_user_id nullable (code pending = no LINE user yet)
--   2. Drop UNIQUE constraint on line_user_id (allow retries)
--   3. Add user_id FK column (link code to an app user)
--   4. Add temp_code TEXT column (6-char bind code)
--   5. Change default expiry to 10 minutes
--   6. Add index on temp_code for fast webhook lookups
-- ============================================================

-- 1. Make line_user_id nullable
ALTER TABLE line_pending_links
    ALTER COLUMN line_user_id DROP NOT NULL;

-- 2. Drop UNIQUE constraint on line_user_id (if exists)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'line_pending_links'
          AND constraint_type = 'UNIQUE'
          AND constraint_name = 'line_pending_links_line_user_id_key'
    ) THEN
        ALTER TABLE line_pending_links
            DROP CONSTRAINT line_pending_links_line_user_id_key;
    END IF;
END;
$$;

-- 3. Add user_id column (FK to users_local) if not exists
ALTER TABLE line_pending_links
    ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users_local(id) ON DELETE CASCADE;

-- 4. Add temp_code column if not exists
ALTER TABLE line_pending_links
    ADD COLUMN IF NOT EXISTS temp_code TEXT;

-- 5. Change default expiry to 10 minutes
ALTER TABLE line_pending_links
    ALTER COLUMN expires_at SET DEFAULT (now() + INTERVAL '10 minutes');

-- 6. Index on temp_code for fast lookups in webhook handler
CREATE INDEX IF NOT EXISTS idx_line_pending_links_temp_code
    ON line_pending_links (temp_code);

-- 7. Index on user_id for cleanup queries
CREATE INDEX IF NOT EXISTS idx_line_pending_links_user_id_fk
    ON line_pending_links (user_id);
