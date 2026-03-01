import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from datetime import date, timedelta
import uuid

# Use a single client for all tests in this file
client = TestClient(app)

@pytest.mark.integration
def test_get_doctor_schedules_filters_past_dates(mock_supabase):
    """
    Integration Test for GET /api/doctors/{doctor_id}/schedules
    - GIVEN a doctor with schedules in the past, present, and future
    - WHEN the API endpoint is called
    - THEN it should only return schedules from today onwards
    """
    # ARRANGE
    today = date.today()
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)
    doctor_id = str(uuid.uuid4())

    # This is what we expect the API to return after filtering in the DB query
    expected_api_return = [
        {"session_date": today.isoformat(), "session_type": "下午"},
        {"session_date": tomorrow.isoformat(), "session_type": "上午"},
    ]

    # The API logic now filters in the database query.
    # So, we set the final return value of the mocked query chain to be
    # what the DB would return *after* the .gte() filter is applied.
    with patch("app.api.hospitals.get_supabase", return_value=mock_supabase) as mock_get_db:
        # We prepare the mock response that the 'execute()' method will return.
        mock_execute = MagicMock()
        mock_execute.data = expected_api_return
        
        # We configure the chain of calls to end with our mocked 'execute'
        (
            mock_supabase.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.execute
        ).return_value = mock_execute

        # ACT
        response = client.get(f"/api/doctors/{doctor_id}/schedules")

        # ASSERT
        assert response.status_code == 200
        
        # Verify the API response matches our expectation
        response_data = response.json()
        assert response_data == expected_api_return
        assert len(response_data) == 2
        
        # Extra check: ensure no past dates are in the result
        for schedule in response_data:
            assert schedule["session_date"] != yesterday.isoformat()
            
        # Verify that the .gte() filter was called correctly in the code
        gte_mock = mock_supabase.table.return_value.select.return_value.eq.return_value.gte
        gte_mock.assert_called_once_with("session_date", today.isoformat())

@pytest.mark.integration
def test_list_all_doctors_with_search_query(mock_supabase):
    """
    Integration Test for GET /api/hospitals/{hospital_id}/doctors
    - GIVEN a list of doctors in the database
    - WHEN the API is called with a search query 'q'
    - THEN it should only return doctors whose name matches the query
    """
    # ARRANGE
    hospital_id = str(uuid.uuid4())
    dept_id = str(uuid.uuid4())
    mock_doctors = [
        {
            "id": str(uuid.uuid4()), "name": "張三豐", "specialty": "太極",
            "hospital_id": hospital_id, "department_id": dept_id, "doctor_no": "123", "is_active": True,
            "departments": {"name": "武當"}
        },
        {
            "id": str(uuid.uuid4()), "name": "李四", "specialty": "普通",
            "hospital_id": hospital_id, "department_id": dept_id, "doctor_no": "456", "is_active": True,
            "departments": {"name": "一般"}
        },
    ]

    with patch("app.api.hospitals.get_supabase", return_value=mock_supabase):
        # --- Scenario 1: Search with a query ---
        mock_execute_search = MagicMock()
        # The ilike filter is applied, so the DB would only return the matching doctor
        mock_execute_search.data = [mock_doctors[0]]
        
        query_chain = mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value
        query_chain.ilike.return_value.execute.return_value = mock_execute_search
        
        # ACT
        response_search = client.get(f"/api/hospitals/{hospital_id}/doctors?q=張三")

        # ASSERT
        assert response_search.status_code == 200
        data_search = response_search.json()
        assert len(data_search) == 1
        assert data_search[0]["name"] == "張三豐"
        
        # Verify the ilike filter was called
        query_chain.ilike.assert_called_once_with("name", f"%張三%")

        # --- Scenario 2: No search query ---
        mock_execute_all = MagicMock()
        mock_execute_all.data = mock_doctors
        # Since the ilike mock was chained, we need to mock the next call on the chain for the no-query case
        query_chain.execute.return_value = mock_execute_all
        
        # ACT
        response_all = client.get(f"/api/hospitals/{hospital_id}/doctors")
        
        # ASSERT
        assert response_all.status_code == 200
        data_all = response_all.json()
        assert len(data_all) == 2
        assert data_all[0]["name"] == "張三豐"
        assert data_all[1]["name"] == "李四"