"""
Speed Estimator Service
=======================
Learns doctor call speed from historical appointment_snapshots,
and uses it to estimate wait times.

Usage:
    # After each progress poll, record a speed sample:
    await record_speed_sample(supabase, doctor_id, prev_snap, curr_snap, hospital_code)

    # To estimate wait time for a tracked subscription:
    minutes = await get_estimated_wait_minutes(supabase, doctor_id, session_type, waiting_count)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

from app.core.logger import logger

# ──────────────────────────────────────────────────────────────
# Tunable constants
# ──────────────────────────────────────────────────────────────
MIN_DELTA_MINUTES = 1.0        # ignore polls that are too close together
MAX_DELTA_MINUTES = 30.0       # ignore gaps > 30 min (lunch break / restart)
MIN_DELTA_CALLS = 1            # must have called at least one new number
MAX_SAMPLES_FOR_AVG = 20       # use at most the recent N samples for average
MIN_SAMPLES_REQUIRED = 3       # need at least this many samples to give an estimate

# Fallback speed (mins/號) by department category if no history yet
# These are conservative defaults based on common clinical observations
_CATEGORY_FALLBACK_MINS_PER_CALL: dict[str, float] = {
    "內科系": 7.0,
    "外科系": 8.0,
    "婦兒科系": 6.0,
    "其他專科": 5.0,
    "default": 6.0,
}


# ──────────────────────────────────────────────────────────────
# Record a speed observation from consecutive snapshots
# ──────────────────────────────────────────────────────────────
async def record_speed_sample(
    supabase,
    doctor_id: str,
    session_date: str,               # "YYYY-MM-DD"
    session_type: str,               # '上午' / '下午' / '晚上'
    prev_number: int,
    prev_at: datetime,
    curr_number: int,
    curr_at: datetime,
    hospital_code: str,
) -> bool:
    """
    Write one speed observation to clinic_speed_samples.

    Returns True if a sample was recorded, False if filtered out.

    Filters:
    - delta_calls < MIN_DELTA_CALLS  → no progress, skip
    - delta_minutes < MIN_DELTA_MINUTES → polls too close, skip
    - delta_minutes > MAX_DELTA_MINUTES → gap too large (break/restart), skip
    - curr_number < prev_number → session reset, skip
    """
    delta_calls = curr_number - prev_number
    if delta_calls < MIN_DELTA_CALLS:
        logger.debug(
            f"[SpeedEstimator] Skipping sample for {doctor_id}: "
            f"delta_calls={delta_calls} (no progress)"
        )
        return False

    # Ensure both datetimes are timezone-aware for subtraction
    if prev_at.tzinfo is None:
        prev_at = prev_at.replace(tzinfo=timezone.utc)
    if curr_at.tzinfo is None:
        curr_at = curr_at.replace(tzinfo=timezone.utc)

    delta_minutes = (curr_at - prev_at).total_seconds() / 60.0

    if delta_minutes < MIN_DELTA_MINUTES:
        logger.debug(
            f"[SpeedEstimator] Skipping sample for {doctor_id}: "
            f"delta_minutes={delta_minutes:.1f} (too short)"
        )
        return False

    if delta_minutes > MAX_DELTA_MINUTES:
        logger.debug(
            f"[SpeedEstimator] Skipping sample for {doctor_id}: "
            f"delta_minutes={delta_minutes:.1f} (gap too large)"
        )
        return False

    row = {
        "doctor_id": doctor_id,
        "session_date": session_date,
        "session_type": session_type,
        "sample_at": curr_at.isoformat(),
        "prev_at": prev_at.isoformat(),
        "prev_number": prev_number,
        "curr_number": curr_number,
        "delta_calls": delta_calls,
        "delta_minutes": round(delta_minutes, 3),
        "hospital_code": hospital_code,
    }

    try:
        await asyncio.to_thread(
            lambda: supabase.table("clinic_speed_samples").insert(row).execute()
        )
        speed = delta_calls / delta_minutes
        logger.info(
            f"[SpeedEstimator] Recorded speed sample: doctor={doctor_id} "
            f"delta={delta_calls}號/{delta_minutes:.1f}min = {speed:.3f}號/min"
        )
        return True
    except Exception as e:
        logger.error(f"[SpeedEstimator] Failed to record speed sample: {e}")
        return False


# ──────────────────────────────────────────────────────────────
# Estimate wait time from historical samples
# ──────────────────────────────────────────────────────────────
async def get_estimated_wait_minutes(
    supabase,
    doctor_id: str,
    session_type: str,
    waiting_count: int,
    dept_category: str = "default",
    use_fallback: bool = True,
) -> Optional[float]:
    """
    Estimate how many minutes until the user's number is called.

    Strategy:
    1. Query the most recent MIN_SAMPLES_REQUIRED..MAX_SAMPLES_FOR_AVG speed samples
       for this doctor + session_type from the last 30 days.
    2. Compute a recency-weighted average speed (calls/min).
       Recent samples get higher weight: weight = 1/(rank+1)
    3. Return estimated_minutes = waiting_count / avg_speed.
    4. If sample_count < MIN_SAMPLES_REQUIRED and use_fallback=True,
       return fallback estimate based on dept_category.
    5. If use_fallback=False and sample_count < MIN_SAMPLES_REQUIRED → return None.

    Args:
        supabase: Supabase client
        doctor_id: UUID of the doctor
        session_type: '上午' / '下午' / '晚上'
        waiting_count: Number of patients ahead (from progressstatus.php)
        dept_category: Department category string (for fallback speed)
        use_fallback: Whether to use default speed when samples are insufficient

    Returns:
        Estimated minutes as float, or None if insufficient data and no fallback.
    """
    if waiting_count <= 0:
        return 0.0

    try:
        res = await asyncio.to_thread(
            lambda: supabase.table("clinic_speed_samples")
            .select("calls_per_min, sample_at")
            .eq("doctor_id", doctor_id)
            .eq("session_type", session_type)
            .gt("sample_at", "NOW() - INTERVAL '30 days'")  # recent data only
            .order("sample_at", desc=True)
            .limit(MAX_SAMPLES_FOR_AVG)
            .execute()
        )
        samples = res.data or []
    except Exception as e:
        logger.error(f"[SpeedEstimator] Error querying speed samples: {e}")
        samples = []

    sample_count = len(samples)

    if sample_count < MIN_SAMPLES_REQUIRED:
        logger.info(
            f"[SpeedEstimator] Only {sample_count} samples for doctor={doctor_id} "
            f"session_type={session_type} (need {MIN_SAMPLES_REQUIRED})"
        )
        if use_fallback:
            fallback_mins = _CATEGORY_FALLBACK_MINS_PER_CALL.get(
                dept_category, _CATEGORY_FALLBACK_MINS_PER_CALL["default"]
            )
            est = waiting_count * fallback_mins
            logger.info(
                f"[SpeedEstimator] Using fallback {fallback_mins} min/號 "
                f"→ est={est:.1f} min (waiting={waiting_count})"
            )
            return round(est, 1)
        return None

    # Recency-weighted average: weight = 1/(rank+1), rank=0 is most recent
    total_weight = 0.0
    weighted_speed = 0.0
    for rank, sample in enumerate(samples):
        cpm = sample.get("calls_per_min") or 0
        if cpm <= 0:
            continue
        weight = 1.0 / (rank + 1)
        weighted_speed += cpm * weight
        total_weight += weight

    if total_weight == 0:
        return None

    avg_speed = weighted_speed / total_weight   # 號/分鐘
    if avg_speed <= 0:
        return None

    estimated_minutes = waiting_count / avg_speed
    logger.info(
        f"[SpeedEstimator] doctor={doctor_id} session={session_type}: "
        f"avg_speed={avg_speed:.3f}號/min, waiting={waiting_count} "
        f"→ est={estimated_minutes:.1f} min (from {sample_count} samples)"
    )
    return round(estimated_minutes, 1)


# ──────────────────────────────────────────────────────────────
# Helper: fetch previous snapshot for speed sample recording
# ──────────────────────────────────────────────────────────────
async def get_previous_snapshot(
    supabase,
    doctor_id: str,
    session_date: str,
    session_type: str,
) -> Optional[dict]:
    """
    Fetch the most recent previous appointment_snapshot for this doctor/session
    that has a valid current_number and scraped_at.
    Returns None if no previous snapshot found.
    """
    try:
        res = await asyncio.to_thread(
            lambda: supabase.table("appointment_snapshots")
            .select("current_number, scraped_at")
            .eq("doctor_id", doctor_id)
            .eq("session_date", session_date)
            .eq("session_type", session_type)
            .not_.is_("current_number", "null")
            .order("scraped_at", desc=True)
            .limit(2)     # limit=2: [0]=most recent (just written), [1]=previous
            .execute()
        )
        rows = res.data or []
        # We want the PREVIOUS one (index 1), since index 0 is the one we just wrote
        if len(rows) >= 2:
            return rows[1]
        return None
    except Exception as e:
        logger.error(f"[SpeedEstimator] Error fetching previous snapshot: {e}")
        return None
