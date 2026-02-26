-- ============================================================
-- Migration: 創建 line_pending_links 表用於暫存待配對的 LINE User IDs
-- ============================================================

-- 創建待配對 LINE 連接表
CREATE TABLE IF NOT EXISTS line_pending_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    line_user_id TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    expires_at TIMESTAMP WITH TIME ZONE DEFAULT (now() + INTERVAL '1 hour'),
    
    CONSTRAINT line_user_id_not_empty CHECK (line_user_id <> '')
);

-- 添加索引用於快速查詢和過期清理
CREATE INDEX IF NOT EXISTS idx_line_pending_links_user_id ON line_pending_links(line_user_id);
CREATE INDEX IF NOT EXISTS idx_line_pending_links_expires_at ON line_pending_links(expires_at);
