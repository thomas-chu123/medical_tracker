-- ============================================================
-- Migration: 添加 line_notify_token 列到 users_local 表
-- ============================================================

-- 添加 line_notify_token 列 (如果还未存在)
ALTER TABLE users_local ADD COLUMN IF NOT EXISTS line_notify_token TEXT;

-- 验证列已添加
-- SELECT column_name, data_type 
-- FROM information_schema.columns 
-- WHERE table_name = 'users_local' AND column_name = 'line_notify_token';
