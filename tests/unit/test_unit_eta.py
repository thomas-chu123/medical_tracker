
import pytest
from datetime import datetime, date
from app.api.hospitals import calculate_eta
from app.core.timezone import TAIWAN_TZ

# --- Test Data ---

SESSION_DATE_TODAY_OBJ = date.today()
SESSION_DATE_TODAY_STR = SESSION_DATE_TODAY_OBJ.strftime("%Y-%m-%d")
SESSION_DATE_PAST_STR = "2022-01-01"


# --- Test Cases for calculate_eta ---

@pytest.mark.unit
@pytest.mark.parametrize("mock_now_str, session_date, session_type, current_number, registered, waiting, target, expected", [
    # Story: Past clinic session should always be "已結束"
    ("09:00", SESSION_DATE_PAST_STR, "上午", 20, 50, [], 40, "已結束"),
    
    # Story: Clinic number has already passed
    ("09:00", SESSION_DATE_TODAY_STR, "上午", 25, 50, [], 10, "已過號"),

    # Story: Target number is in the waiting list (current_number should be ignored)
    # mock_now=9:00, start=8:30 -> base=now. ahead=14. eta=9:00 + 14*5m = 10:10
    ("09:00", SESSION_DATE_TODAY_STR, "上午", 5, 50, list(range(1, 21)), 15, "10:10"),

    # Story: Target number not in waiting list, estimate based on current progress
    # mock_now=14:00, start=13:30 -> base=now. ahead=15. eta=14:00 + 15*5m = 15:15
    ("14:00", SESSION_DATE_TODAY_STR, "下午", 25, 50, [], 40, "15:15"),

    # Story: Evening session with shorter time per patient
    # mock_now=18:30, start=18:00 -> base=now. ahead=20. eta=18:30 + 20*3m = 19:30
    ("18:30", SESSION_DATE_TODAY_STR, "晚上", 10, 60, [], 30, "19:30"),

    # Story: No target number provided, calculate current doctor progress
    # mock_now=9:00, start=8:30 -> base=now. registered=50, waiting=10 -> done=40. eta=9:00 + 40*5m = 12:20
    ("09:00", SESSION_DATE_TODAY_STR, "上午", 25, 50, list(range(41, 51)), None, "12:20"),

    # Story: Invalid inputs should return None
    ("09:00", None, "上午", 20, 50, [], 40, None),
    ("09:00", SESSION_DATE_TODAY_STR, "深夜", 20, 50, [], 40, None),
])
def test_calculate_eta_scenarios(mock_now_str, session_date, session_type, current_number, registered, waiting, target, expected, mocker):
    """Unit test for various scenarios of the calculate_eta function."""
    mock_now_dt = datetime.strptime(f"{SESSION_DATE_TODAY_STR} {mock_now_str}", "%Y-%m-%d %H:%M").replace(tzinfo=TAIWAN_TZ)
    mocker.patch("app.api.hospitals.now_tw", return_value=mock_now_dt)
    mocker.patch("app.api.hospitals.today_tw", return_value=SESSION_DATE_TODAY_OBJ)
    
    result = calculate_eta(
        session_date_str=session_date,
        session_type=session_type,
        current_number=current_number,
        registered_count=registered,
        waiting_list=waiting,
        target_number=target
    )
    assert result == expected

@pytest.mark.unit
def test_calculate_eta_clinic_not_started_yet(mocker):
    """Test that ETA is calculated from start time if clinic hasn't opened."""
    mock_now_dt = datetime.strptime(f"{SESSION_DATE_TODAY_STR} 13:00", "%Y-%m-%d %H:%M").replace(tzinfo=TAIWAN_TZ)
    mocker.patch("app.api.hospitals.now_tw", return_value=mock_now_dt)
    mocker.patch("app.api.hospitals.today_tw", return_value=SESSION_DATE_TODAY_OBJ)

    # 5 people are ahead of me.
    # Base time should be 13:30 (start time), not 13:00 (now)
    # 13:30 + 5*5 mins = 13:55
    eta = calculate_eta(SESSION_DATE_TODAY_STR, "下午", 10, 20, [], 15)
    assert eta == "13:55"

@pytest.mark.unit
def test_calculate_eta_clinic_already_started(mocker):
    """Test that ETA is calculated from 'now' if clinic is in progress."""
    mock_now_dt = datetime.strptime(f"{SESSION_DATE_TODAY_STR} 14:00", "%Y-%m-%d %H:%M").replace(tzinfo=TAIWAN_TZ)
    mocker.patch("app.api.hospitals.now_tw", return_value=mock_now_dt)
    mocker.patch("app.api.hospitals.today_tw", return_value=SESSION_DATE_TODAY_OBJ)
    
    # 5 people are ahead of me.
    # Base time should be 14:00 (now), not 13:30 (start time)
    # 14:00 + 5*5 mins = 14:25
    eta = calculate_eta(SESSION_DATE_TODAY_STR, "下午", 10, 20, [], 15)
    assert eta == "14:25"

@pytest.mark.unit
def test_calculate_eta_with_queue_details(mocker):
    """Test that ETA filters out '未報到' when clinic_queue_details is provided."""
    mock_now_dt = datetime.strptime(f"{SESSION_DATE_TODAY_STR} 09:00", "%Y-%m-%d %H:%M").replace(tzinfo=TAIWAN_TZ)
    mocker.patch("app.api.hospitals.now_tw", return_value=mock_now_dt)
    mocker.patch("app.api.hospitals.today_tw", return_value=SESSION_DATE_TODAY_OBJ)

    # Current: 5, Target: 20
    # Queue details from 5 to 20: 15 numbers
    # If 10 are "未報到", only 5 are ahead.
    # 09:00 + 5*5 mins = 09:25
    queue_details = []
    for i in range(1, 25):
        status = "已報到"
        if 10 <= i <= 19: # 10 patients between 5 and 20 are "未報到"
            status = "未報到"
        queue_details.append({"number": i, "status": status})

    eta = calculate_eta(
        session_date_str=SESSION_DATE_TODAY_STR,
        session_type="上午",
        current_number=5,
        registered_count=30,
        waiting_list=[], # ignored when clinic_queue_details is present
        target_number=20,
        clinic_queue_details=queue_details
    )
    # Total people ahead should be: numbers 6, 7, 8, 9 (4 people) 
    # (Numbers 10-19 are "未報到", which are 10 people)
    # Wait, 20 is my number. Between 5 and 20 are 6,7,8,9,10,11,12,13,14,15,16,17,18,19 (14 numbers)
    # Numbers 10-19 are "未報到" (10 numbers)
    # Remaining are 6,7,8,9 (4 numbers)
    # 09:00 + 4*5 mins = 09:20
    assert eta == "09:20"
