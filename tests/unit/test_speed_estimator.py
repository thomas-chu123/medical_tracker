"""
Unit tests for app/services/speed_estimator.py

Tests cover:
- record_speed_sample: filtering logic
- get_estimated_wait_minutes: weighted average and fallback
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch


# ─── Helpers ───

def _make_supabase_mock(query_data: list):
    """Create a minimal Supabase mock that returns query_data on .execute()."""
    mock = MagicMock()
    result = MagicMock()
    result.data = query_data
    mock.table.return_value.insert.return_value.execute.return_value = result
    mock.table.return_value.select.return_value.eq.return_value.eq.return_value \
        .not_.return_value.is_.return_value.order.return_value.limit.return_value \
        .execute.return_value = result
    # For chained selects in get_estimated_wait_minutes
    chain = mock.table.return_value.select.return_value
    for attr in ["eq", "gt", "order", "limit", "not_"]:
        chain = getattr(chain, attr).return_value = chain
    chain.execute.return_value = result
    return mock, result


def _ts(year=2026, month=3, day=4, hour=14, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


# ─── Tests for record_speed_sample ───

class TestRecordSpeedSample:

    @pytest.mark.asyncio
    async def test_records_valid_sample(self):
        from app.services.speed_estimator import record_speed_sample

        mock_sb = MagicMock()
        mock_sb.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{}])

        result = await record_speed_sample(
            supabase=mock_sb,
            doctor_id="doc-1",
            session_date="2026-03-04",
            session_type="下午",
            prev_number=10,
            prev_at=_ts(hour=13, minute=0),
            curr_number=15,
            curr_at=_ts(hour=13, minute=20),
            hospital_code="HMMH",
        )
        assert result is True
        mock_sb.table.assert_called_once_with("clinic_speed_samples")

    @pytest.mark.asyncio
    async def test_filters_no_progress(self):
        from app.services.speed_estimator import record_speed_sample

        mock_sb = MagicMock()
        # Same number → delta_calls = 0
        result = await record_speed_sample(
            supabase=mock_sb, doctor_id="doc-1", session_date="2026-03-04",
            session_type="下午", prev_number=10,
            prev_at=_ts(hour=13), curr_number=10,  # no change
            curr_at=_ts(hour=13, minute=5), hospital_code="HMMH",
        )
        assert result is False
        mock_sb.table.assert_not_called()

    @pytest.mark.asyncio
    async def test_filters_too_short_interval(self):
        from app.services.speed_estimator import record_speed_sample

        mock_sb = MagicMock()
        result = await record_speed_sample(
            supabase=mock_sb, doctor_id="doc-1", session_date="2026-03-04",
            session_type="下午", prev_number=10,
            prev_at=_ts(hour=13, minute=0), curr_number=12,
            curr_at=_ts(hour=13, minute=0),  # 0 min gap
            hospital_code="HMMH",
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_filters_large_gap(self):
        from app.services.speed_estimator import record_speed_sample

        mock_sb = MagicMock()
        result = await record_speed_sample(
            supabase=mock_sb, doctor_id="doc-1", session_date="2026-03-04",
            session_type="下午", prev_number=10,
            prev_at=_ts(hour=12, minute=0), curr_number=15,
            curr_at=_ts(hour=13, minute=0),  # 60 min gap → filtered
            hospital_code="HMMH",
        )
        assert result is False


# ─── Tests for get_estimated_wait_minutes ───

class TestGetEstimatedWaitMinutes:

    def _make_samples(self, calls_per_min_values: list):
        return [{"calls_per_min": v, "sample_at": "2026-03-04T14:00:00+00:00"} for v in calls_per_min_values]

    @pytest.mark.asyncio
    async def test_returns_none_when_insufficient_samples(self):
        from app.services.speed_estimator import get_estimated_wait_minutes

        mock_sb = MagicMock()
        # Only 1 sample (< MIN_SAMPLES_REQUIRED=3), use_fallback=False
        res_mock = MagicMock()
        res_mock.data = self._make_samples([0.2])
        # Build chain
        mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value \
            .gt.return_value.order.return_value.limit.return_value.execute.return_value = res_mock

        result = await get_estimated_wait_minutes(
            mock_sb, "doc-1", "下午", waiting_count=5, use_fallback=False
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_fallback_when_insufficient_samples(self):
        from app.services.speed_estimator import get_estimated_wait_minutes

        mock_sb = MagicMock()
        res_mock = MagicMock()
        res_mock.data = []  # no samples
        mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value \
            .gt.return_value.order.return_value.limit.return_value.execute.return_value = res_mock

        result = await get_estimated_wait_minutes(
            mock_sb, "doc-1", "下午", waiting_count=5,
            dept_category="default", use_fallback=True
        )
        # waiting_count=5 * fallback_mins=6.0 = 30.0
        assert result == 30.0

    @pytest.mark.asyncio
    async def test_weighted_average_calculation(self):
        from app.services.speed_estimator import get_estimated_wait_minutes

        mock_sb = MagicMock()
        res_mock = MagicMock()
        # 3 samples: most recent=0.5, then 0.3, then 0.2
        res_mock.data = self._make_samples([0.5, 0.3, 0.2])
        mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value \
            .gt.return_value.order.return_value.limit.return_value.execute.return_value = res_mock

        result = await get_estimated_wait_minutes(
            mock_sb, "doc-1", "下午", waiting_count=10, use_fallback=False
        )
        # Weighted: w0=1, w1=0.5, w2=0.333
        # avg = (0.5*1 + 0.3*0.5 + 0.2*0.333) / (1+0.5+0.333)
        total_w = 1 + 0.5 + 1/3
        num = 0.5*1 + 0.3*0.5 + 0.2*(1/3)
        expected_speed = num / total_w
        expected_wait = round(10 / expected_speed, 1)
        assert result == expected_wait

    @pytest.mark.asyncio
    async def test_zero_waiting_returns_zero(self):
        from app.services.speed_estimator import get_estimated_wait_minutes

        mock_sb = MagicMock()
        result = await get_estimated_wait_minutes(mock_sb, "doc-1", "下午", waiting_count=0)
        assert result == 0.0
