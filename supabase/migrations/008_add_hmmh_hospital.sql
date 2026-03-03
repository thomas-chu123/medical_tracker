-- ============================================================
-- 新增馬偕紀念醫院新竹分院 (HMMH)
-- ============================================================

-- 插入馬偕紀念醫院新竹分院
INSERT INTO hospitals (name, code, base_url, region) VALUES
    ('馬偕紀念醫院新竹分院', 'HMMH', 'https://www.hc.mmh.org.tw', '新竹縣市')
ON CONFLICT (code) DO UPDATE 
SET 
    name = EXCLUDED.name,
    base_url = EXCLUDED.base_url,
    region = EXCLUDED.region,
    updated_at = NOW();
