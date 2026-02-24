import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from app.services.notification import _process_subscription


@pytest.fixture
def mock_supabase():
    """
    Fixture to create a mock Supabase client with a robust side_effect for table selection.
    This prevents mock configurations from interfering with each other.
    """
    client = MagicMock(name="supabase_client")

    # Create distinct mock objects for each table
    snapshots_table = MagicMock(name="snapshots_table")
    hospitals_table = MagicMock(name="hospitals_table")
    profiles_table = MagicMock(name="profiles_table")
    logs_table = MagicMock(name="logs_table")
    subscriptions_table = MagicMock(name="subscriptions_table")

    # Use a side_effect to return the correct table mock based on the table name
    def table_side_effect(table_name):
        if table_name == "appointment_snapshots":
            return snapshots_table
        if table_name == "hospitals":
            return hospitals_table
        if table_name == "user_profiles":
            return profiles_table
        if table_name == "notification_logs":
            return logs_table
        if table_name == "tracking_subscriptions":
            return subscriptions_table
        return MagicMock(name=f"default_mock_for_{table_name}")

    client.table.side_effect = table_side_effect

    # Make async methods awaitable
    client.auth.admin.get_user_by_id = AsyncMock()
    return client


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


@pytest.fixture
def mock_build_line(mocker):
    """Fixture to mock the build_line_message function."""
    return mocker.patch(
        "app.services.notification.build_line_message",
        return_value="Test LINE Message",
    )


# --- Test Cases ---


@pytest.mark.asyncio
async def test_no_notification_if_remaining_is_high(
    mocker, mock_supabase, mock_send_email, mock_send_line_notify
):
    """
    Verify that no notification is sent if the number of remaining people
    is higher than all notification thresholds.
    """
    # Arrange
    subscription = {
        "id": "sub_1", "user_id": "user_1", "doctor_id": 1,
        "session_type": "上午", "session_date": str(date.today()), "appointment_number": 30,
        "notify_at_20": True, "notify_at_10": True, "notify_at_5": True,
        "notified_20": False, "notified_10": False, "notified_5": False,
        "notify_email": True, "notify_line": True,
        "doctors": {"name": "Dr. Test", "hospital_id": 1},
        "departments": {"name": "Testing"},
    }
    # Set remaining to a value higher than any threshold (28)
    snapshot_data = {
        "current_number": 1, "waiting_list": list(range(2, 30)),
    }

    # Mock database responses using the specific table mocks
    snapshots_table = mock_supabase.table("appointment_snapshots")
    snapshots_table.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [snapshot_data]

    # Mock _get_user_email
    mocker.patch('app.services.notification._get_user_email', AsyncMock(return_value="test@example.com"))

    # Act
    await _process_subscription(mock_supabase, subscription)

    # Assert
    mock_send_email.assert_not_called()
    mock_send_line_notify.assert_not_called()
    # Check that we didn't try to update the subscription status
    subscriptions_table = mock_supabase.table("tracking_subscriptions")
    assert not subscriptions_table.update.called


@pytest.mark.asyncio
async def test_sends_notification_when_threshold_crossed(
    mocker, mock_supabase, mock_send_email, mock_send_line_notify, mock_build_email, mock_build_line
):
    """
    Verify that a notification is sent when a specific threshold is crossed for the first time.
    """
    # Arrange
    subscription = {
        "id": "sub_2", "user_id": "user_2", "doctor_id": 2,
        "session_date": str(date.today()),
        "session_type": "下午", "appointment_number": 15,
        "notify_at_20": True, "notify_at_10": True, "notify_at_5": True,
        "notified_20": True,  # Already notified for 20
        "notified_10": False, # NOT notified for 10 yet
        "notified_5": False,
        "notify_email": True, "notify_line": True,
        "doctors": {"name": "Dr. Code", "hospital_id": 1, "doctor_no": "D2"},
        "departments": {"name": "Software Engineering"},
    }
    # 9 people remaining, which should trigger the "10" threshold
    snapshot_data = {
        "current_number": 5, "waiting_list": list(range(6, 15)),
        "clinic_room": "Room 101"
    }

    # Mock database responses
    snapshots_table = mock_supabase.table("appointment_snapshots")
    snapshots_table.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [snapshot_data]

    hospitals_table = mock_supabase.table("hospitals")
    hospitals_table.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {"name": "General Hospital"}

    profiles_table = mock_supabase.table("user_profiles")
    profiles_table.select.return_value.eq.return_value.execute.return_value.data = [{"line_notify_token": "fake_line_token"}]

    logs_table = mock_supabase.table("notification_logs")
    logs_table.insert.return_value.execute.return_value.data = [{"id": 99}]

    # Mock _get_user_email
    mocker.patch('app.services.notification._get_user_email', AsyncMock(return_value="user@email.com"))

    # Act
    await _process_subscription(mock_supabase, subscription)

    # Assert
    mock_send_email.assert_called_once()
    mock_send_line_notify.assert_called_once()

    # Verify the content passed to build functions
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
    # Verify the subscription was marked as notified for the correct threshold
    subscriptions_table = mock_supabase.table("tracking_subscriptions")
    subscriptions_table.update.assert_called_once_with({"notified_10": True})


@pytest.mark.asyncio
async def test_no_notification_if_already_notified(
    mocker, mock_supabase, mock_send_email, mock_send_line_notify
):
    """
    Verify that no notification is sent if the user has already been notified for a given threshold.
    """
    # Arrange
    subscription = {
        "id": "sub_3", "user_id": "user_3", "doctor_id": 3,
        "session_date": str(date.today()), "session_type": "上午", "appointment_number": 12,
        "notify_at_10": True, "notified_10": True, # Already notified
        "doctors": {"name": "Dr. Skip", "hospital_id": 1}, "departments": {"name": "Redundancy"},
    }
    snapshot_data = {"current_number": 3, "waiting_list": list(range(4, 12))} # 8 remaining

    snapshots_table = mock_supabase.table("appointment_snapshots")
    snapshots_table.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [snapshot_data]

    mocker.patch('app.services.notification._get_user_email', AsyncMock(return_value="user3@email.com"))

    # Act
    await _process_subscription(mock_supabase, subscription)

    # Assert
    mock_send_email.assert_not_called()
    mock_send_line_notify.assert_not_called()
    subscriptions_table = mock_supabase.table("tracking_subscriptions")
    assert not subscriptions_table.update.called

@pytest.mark.asyncio
async def test_no_notification_if_disabled_by_user(
    mocker, mock_supabase, mock_send_email, mock_send_line_notify
):
    """
    Verify that no notification is sent if the user has disabled a specific threshold.
    """
    # Arrange
    subscription = {
        "id": "sub_4", "user_id": "user_4", "doctor_id": 4,
        "session_date": str(date.today()), "session_type": "上午", "appointment_number": 20,
        "notify_at_10": False, # User disabled this threshold
        "notified_10": False,
        "doctors": {"name": "Dr. Opt-out", "hospital_id": 1}, "departments": {"name": "Preferences"},
    }
    snapshot_data = {"current_number": 11, "waiting_list": list(range(12, 20))} # 8 remaining

    snapshots_table = mock_supabase.table("appointment_snapshots")
    snapshots_table.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [snapshot_data]

    mocker.patch('app.services.notification._get_user_email', AsyncMock(return_value="user4@email.com"))

    # Act
    await _process_subscription(mock_supabase, subscription)

    # Assert
    mock_send_email.assert_not_called()
    mock_send_line_notify.assert_not_called()
    subscriptions_table = mock_supabase.table("tracking_subscriptions")
    assert not subscriptions_table.update.called

@pytest.mark.asyncio
async def test_multiple_thresholds_trigger_once(
    mocker, mock_supabase, mock_send_email, mock_send_line_notify
):
    """
    Verify that if the remaining count crosses multiple thresholds at once, only the highest one triggers.
    """
    # Arrange
    subscription = {
        "id": "sub_5", "user_id": "user_5", "doctor_id": 5,
        "session_date": str(date.today()), "session_type": "上午", "appointment_number": 10,
        "notify_at_20": True, "notify_at_10": True, "notify_at_5": True,
        "notified_20": False, "notified_10": False, "notified_5": False,
        "notify_email": True, "notify_line": False, # Only email
        "doctors": {"name": "Dr. Jump", "hospital_id": 1}, "departments": {"name": "Efficiency"},
    }
    # 4 people remaining, should cross 20, 10, and 5, but only trigger 20
    snapshot_data = {"current_number": 5, "waiting_list": list(range(6, 10))}

    snapshots_table = mock_supabase.table("appointment_snapshots")
    snapshots_table.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [snapshot_data]

    hospitals_table = mock_supabase.table("hospitals")
    hospitals_table.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {"name": "Test Hospital"}

    logs_table = mock_supabase.table("notification_logs")
    logs_table.insert.return_value.execute.return_value.data = [{"id": 100}]

    mocker.patch('app.services.notification._get_user_email', AsyncMock(return_value="user5@email.com"))

    # Act
    await _process_subscription(mock_supabase, subscription)

    # Assert
    mock_send_email.assert_called_once()
    mock_send_line_notify.assert_not_called()
    # Should only notify for the highest threshold crossed (20)
    subscriptions_table = mock_supabase.table("tracking_subscriptions")
    subscriptions_table.update.assert_called_once_with({"notified_20": True})
