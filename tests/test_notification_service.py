import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.services.notification import _process_subscription


@pytest.fixture
def mock_send_email(mocker):
    """Fixture to mock the send_email function."""
    return mocker.patch("app.services.notification.send_email", new_callable=AsyncMock)


@pytest.fixture
def mock_send_line_notify(mocker):
    """Fixture to mock the send_line_notify function."""
    return mocker.patch("app.services.notification.send_line_notify", new_callable=AsyncMock)


@pytest.fixture
def mock_build_email(mocker):
    """Fixture to mock the build_clinic_alert_email function."""
    return mocker.patch(
        "app.services.notification.build_clinic_alert_email",
        return_value=("Test Subject", "Test Body"),
    )


# --- Test Cases ---


@pytest.mark.asyncio
async def test_no_notification_if_remaining_is_high(
    mocker, mock_send_email
):
    """
    Verify that no notification is sent if the number of remaining people
    is higher than all notification thresholds.
    """
    # Arrange
    subscription = {
        "id": "sub_1", "user_id": "user_1", "doctor_id": 1,
        "session_date": str(date.today()), "session_type": "上午", "appointment_number": 30,
        "notify_at_20": True, "notify_at_10": True, "notify_at_5": True,
        "notified_20": False, "notified_10": False, "notified_5": False,
        "doctors": {"name": "Dr. Test", "hospital_id": 1},
    }
    # Set remaining to a value higher than any threshold (28)
    snapshot_data = {"current_number": 1, "waiting_list": list(range(2, 30))}
    
    mock_snap_res = MagicMock(); mock_snap_res.data = [snapshot_data]
    mock_hosp_res = MagicMock(); mock_hosp_res.data = {"name": "Test Hospital"}
    mock_profile_res = MagicMock(); mock_profile_res.data = []

    mocker.patch(
        "app.services.notification._run",
        new_callable=AsyncMock,
        side_effect=[mock_snap_res, mock_hosp_res, mock_profile_res]
    )
    mocker.patch('app.services.notification._get_user_email', AsyncMock(return_value="test@example.com"))

    # Act
    await _process_subscription(MagicMock(), subscription)

    # Assert
    mock_send_email.assert_not_called()


@pytest.mark.asyncio
async def test_sends_notification_when_threshold_crossed(
    mocker, mock_send_email, mock_send_line_notify, mock_build_email
):
    """
    Verify that a notification is sent when a specific threshold is crossed for the first time.
    """
    # Arrange
    subscription = {
        "id": "sub_2", "user_id": "user_2", "doctor_id": 2,
        "session_date": str(date.today()), "session_type": "下午", "appointment_number": 15,
        "notify_at_20": True, "notify_at_10": True, "notify_at_5": True,
        "notified_20": True, "notified_10": False, "notified_5": False,
        "notify_email": True, "notify_line": True,
        "doctors": {"name": "Dr. Code", "hospital_id": 1},
        "departments": {"name": "Software Engineering"},
    }
    snapshot_data = {"current_number": 5, "waiting_list": list(range(6, 15)), "clinic_room": "Room 101"}

    # Mock the sequence of results from _run
    mock_snap_res = MagicMock(); mock_snap_res.data = [snapshot_data]
    mock_hosp_res = MagicMock(); mock_hosp_res.data = {"name": "General Hospital"}
    mock_profile_res = MagicMock(); mock_profile_res.data = [{"line_notify_token": "fake_line_token"}]
    mock_log_res = MagicMock(); mock_log_res.data = [{"id": 99}]
    # The last _run call is for the update, which we don't need to mock data for
    mock_update_res = MagicMock()

    mock_run = mocker.patch(
        "app.services.notification._run",
        new_callable=AsyncMock,
        # snap, hosp, profile, log_email, update_log_email, log_line, update_log_line, update_sub
        side_effect=[mock_snap_res, mock_hosp_res, mock_profile_res, mock_log_res, mock_update_res, mock_log_res, mock_update_res, mock_update_res]
    )
    mocker.patch('app.services.notification._get_user_email', AsyncMock(return_value="user@email.com"))

    # Act
    await _process_subscription(MagicMock(), subscription)

    # Assert
    mock_send_email.assert_called_once()
    mock_send_line_notify.assert_called_once()

    mock_build_email.assert_called_with(
        hospital_name="General Hospital",
        clinic_room="Room 101",
        doctor_name="Dr. Code",
        department_name="Software Engineering",
        session_date=str(date.today()),
        session_type="下午",
        current_number=5,
        remaining=9,
        threshold=10,
    )
    assert mock_run.call_count >= 4


@pytest.mark.asyncio
async def test_no_notification_if_already_notified(
    mocker, mock_send_email
):
    """
    Verify that no notification is sent if the user has already been notified for a given threshold.
    """
    # Arrange
    subscription = {
        "id": "sub_3", "user_id": "user_3", "doctor_id": 3,
        "session_date": str(date.today()), "appointment_number": 12,
        "notify_at_10": True, "notified_10": True,
        "doctors": {"name": "Dr. Skip"},
    }
    snapshot_data = {"current_number": 3, "waiting_list": list(range(4, 12))}
    mock_snap_res = MagicMock(); mock_snap_res.data = [snapshot_data]

    mocker.patch("app.services.notification._run", new_callable=AsyncMock, return_value=mock_snap_res)
    mocker.patch('app.services.notification._get_user_email', AsyncMock(return_value="user3@email.com"))

    # Act
    await _process_subscription(MagicMock(), subscription)

    # Assert
    mock_send_email.assert_not_called()

@pytest.mark.asyncio
async def test_no_notification_if_disabled_by_user(
    mocker, mock_send_email
):
    """
    Verify that no notification is sent if the user has disabled a specific threshold.
    """
    # Arrange
    subscription = {
        "id": "sub_4", "user_id": "user_4", "doctor_id": 4,
        "session_date": str(date.today()), "appointment_number": 20,
        "notify_at_10": False, "notified_10": False,
        "doctors": {"name": "Dr. Opt-out"},
    }
    snapshot_data = {"current_number": 11, "waiting_list": list(range(12, 20))}
    mock_snap_res = MagicMock(); mock_snap_res.data = [snapshot_data]

    mocker.patch("app.services.notification._run", new_callable=AsyncMock, return_value=mock_snap_res)
    mocker.patch('app.services.notification._get_user_email', AsyncMock(return_value="user4@email.com"))

    # Act
    await _process_subscription(MagicMock(), subscription)

    # Assert
    mock_send_email.assert_not_called()


@pytest.mark.asyncio
async def test_multiple_thresholds_trigger_once(
    mocker, mock_send_email, mock_send_line_notify, mock_build_email
):
    """
    Verify that if the remaining count crosses multiple thresholds at once, only the highest one triggers.
    """
    # Arrange
    subscription = {
        "id": "sub_5", "user_id": "user_5", "doctor_id": 5,
        "session_date": str(date.today()), "appointment_number": 10,
        "notify_at_20": True, "notify_at_10": True, "notify_at_5": True,
        "notified_20": False, "notified_10": False, "notified_5": False,
        "notify_email": True, "notify_line": False,
        "doctors": {"name": "Dr. Jump", "hospital_id": 1},
        "departments": {"name": "Efficiency"},
    }
    snapshot_data = {"current_number": 5, "waiting_list": list(range(6, 10))}

    mock_snap_res = MagicMock(); mock_snap_res.data = [snapshot_data]
    mock_hosp_res = MagicMock(); mock_hosp_res.data = {"name": "Test Hospital"}
    mock_profile_res = MagicMock(); mock_profile_res.data = []
    mock_log_res = MagicMock(); mock_log_res.data = [{"id": 100}]
    mock_update_res = MagicMock()

    mocker.patch(
        "app.services.notification._run",
        new_callable=AsyncMock,
        # snap, hosp, profile, log_email, update_log_email, update_sub
        side_effect=[mock_snap_res, mock_hosp_res, mock_profile_res, mock_log_res, mock_update_res, mock_update_res]
    )
    mocker.patch('app.services.notification._get_user_email', AsyncMock(return_value="user5@email.com"))

    # Act
    await _process_subscription(MagicMock(), subscription)

    # Assert
    mock_send_email.assert_called_once()
    mock_send_line_notify.assert_not_called()
    
    mock_build_email.assert_called_with(
        hospital_name="Test Hospital",
        clinic_room="未提供",
        doctor_name="Dr. Jump",
        department_name="Efficiency",
        session_date=str(date.today()),
        session_type="",
        current_number=5,
        remaining=4,
        threshold=20,
    )
