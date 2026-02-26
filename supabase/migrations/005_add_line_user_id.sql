-- ============================================================
-- Migration: 添加 line_user_id 列到 users_local 表
-- ============================================================

-- 添加 line_user_id 列 (用於 LINE Message API)
ALTER TABLE users_local ADD COLUMN IF NOT EXISTS line_user_id TEXT;

-- 添加索引以提高查詢性能
CREATE INDEX IF NOT EXISTS idx_users_local_line_user_id ON users_local(line_user_id);

-- 驗證列已添加
-- SELECT column_name, data_type 
-- FROM information_schema.columns 
-- WHERE table_name = 'users_local' AND column_name = 'line_user_id';
