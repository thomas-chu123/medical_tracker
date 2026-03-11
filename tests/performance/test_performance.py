"""
Performance tests for the Medical Tracker API.
This suite focuses on ensuring endpoints remain responsive under load or handle large datasets efficiently.
"""
import pytest
import time
import httpx

# Assuming local test environment for now
BASE_URL = "http://localhost:8000"


# @pytest.mark.skip(reason="Requires running server - run manually with: uvicorn app.main:app --reload && pytest tests/performance/test_performance.py -v")
@pytest.mark.asyncio
async def test_global_stats_performance():
    """
    Test that the global stats endpoint responds within an acceptable timeframe.
    Because this endpoint aggregrates data across the DB, it's a good performance indicator.
    """
    start_time = time.time()
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{BASE_URL}/api/stats/global")
        
    duration = time.time() - start_time
    
    # Assert successful retrieval
    assert response.status_code == 200, "Stats API should return 200 OK"
    
    # Performance assertion: The endpoint uses parallel queries and caching. 
    # Even on a cache miss, it should return reasonably fast.
    assert duration < 5.0, f"Global stats API took too long: {duration:.2f} seconds"


# @pytest.mark.skip(reason="Requires running server - run manually with: uvicorn app.main:app --reload && pytest tests/performance/test_performance.py -v")
@pytest.mark.asyncio
async def test_crowd_analysis_performance():
    """
    Test that the crowd analysis endpoint responds within an acceptable timeframe.
    """
    start_time = time.time()
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        # T4 is NTUH Hsinchu (known to have large data sets)
        response = await client.get(f"{BASE_URL}/api/stats/crowd-analysis?hospital_code=T4")
        
    duration = time.time() - start_time
    
    # Assert successful retrieval
    assert response.status_code == 200, "Crowd analysis API should return 200 OK"
    
    # Performance assertion
    assert duration < 5.0, f"Crowd analysis API took too long: {duration:.2f} seconds"
