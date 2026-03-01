-- Add NTUH Hsinchu (National Taiwan University Hospital Hsinchu Branch) hospital record
-- Hospital Code: NTUH_HSINCHU
-- API Code: T4

INSERT INTO hospitals (name, code, base_url, region) VALUES
    ('國立臺灣大學醫學院附設醫院新竹分院', 'NTUH_HSINCHU', 'https://reg.ntuh.gov.tw/WebReg', '新竹')
ON CONFLICT (code) DO NOTHING;
