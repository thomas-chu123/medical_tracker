-- Add TVGH_HSINCHU hospital entry
-- Path: supabase/migrations/20260306185000_add_tvgh_hsinchu.sql

INSERT INTO public.hospitals (name, code, base_url, region, is_active)
VALUES (
    '臺北榮民總醫院新竹分院',
    'TVGH_HSINCHU',
    'https://webreg.vhct.gov.tw',
    '新竹縣市',
    true
)
ON CONFLICT (code) DO UPDATE SET
    name = EXCLUDED.name,
    base_url = EXCLUDED.base_url,
    region = EXCLUDED.region,
    is_active = EXCLUDED.is_active,
    updated_at = now();
