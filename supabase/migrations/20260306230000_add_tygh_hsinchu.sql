-- Add TYGH_HSINCHU hospital entry
-- Path: supabase/migrations/20260306230000_add_tygh_hsinchu.sql

INSERT INTO public.hospitals (name, code, base_url, region, is_active)
VALUES (
    '東元綜合醫院',
    'TYGH_HSINCHU',
    'https://w3.tyh.com.tw',
    '新竹縣市',
    true
)
ON CONFLICT (code) DO UPDATE SET
    name = EXCLUDED.name,
    base_url = EXCLUDED.base_url,
    region = EXCLUDED.region,
    is_active = EXCLUDED.is_active,
    updated_at = now();
