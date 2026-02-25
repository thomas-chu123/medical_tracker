from datetime import datetime, timezone, timedelta

# Taiwan timezone (UTC+8)
TAIWAN_TZ = timezone(timedelta(hours=8))

def now_tw() -> datetime:
    """Return current datetime in Taiwan time (UTC+8)."""
    return datetime.now(TAIWAN_TZ)

def today_tw() -> datetime:
    """Return today's date in Taiwan time (UTC+8)."""
    return now_tw().date()

def today_tw_str() -> str:
    """Return today's date string in Taiwan time (UTC+8), e.g. '2026-02-24'."""
    return today_tw().isoformat()

def now_utc_str() -> str:
    """Return current datetime in UTC ISO format with 'Z' suffix for DB storage."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
