"""
Tests for calculate_remaining_count method in scrapers.

This test suite verifies that each hospital's scraper correctly calculates
the remaining number of patients between current_number and target_number.
"""

import pytest
from app.scrapers.cmuh import CMUHScraper, CMUHHsinchuScraper
from app.scrapers.ntuh import NTUHHsinchuScraper


class TestCMUHScraperRemainingCount:
    """Test CMUH's calculate_remaining_count implementation."""

    def test_cmuh_excludes_completed_status(self):
        """CMUH should exclude patients with '完成' status."""
        scraper = CMUHScraper()
        
        # Sample queue: numbers 1-10, with some completed
        clinic_queue_details = [
            {"number": 1, "status": "完成"},
            {"number": 2, "status": "未看診"},
            {"number": 3, "status": "完成"},
            {"number": 4, "status": "未看診"},
            {"number": 5, "status": "完成"},
            {"number": 6, "status": "未看診"},
            {"number": 7, "status": "完成"},
            {"number": 8, "status": "未看診"},
            {"number": 9, "status": "完成"},
            {"number": 10, "status": "未看診"},
        ]
        
        # Current at 2, target at 8
        # Numbers between 2 and 8 (exclusive): 3, 4, 5, 6, 7
        # Excluding "完成": 4, 6 = 2 people
        remaining = scraper.calculate_remaining_count(
            current_number=2,
            target_number=8,
            clinic_queue_details=clinic_queue_details,
        )
        assert remaining == 2

    def test_cmuh_user_already_passed(self):
        """CMUH should return 0 if user's number is already called."""
        scraper = CMUHScraper()
        
        clinic_queue_details = [
            {"number": 1, "status": "完成"},
            {"number": 2, "status": "完成"},
            {"number": 3, "status": "未看診"},
        ]
        
        # Current at 5, target at 3 (user already passed)
        remaining = scraper.calculate_remaining_count(
            current_number=5,
            target_number=3,
            clinic_queue_details=clinic_queue_details,
        )
        assert remaining == 0

    def test_cmuh_empty_queue(self):
        """CMUH should return 0 for empty queue."""
        scraper = CMUHScraper()
        
        remaining = scraper.calculate_remaining_count(
            current_number=1,
            target_number=10,
            clinic_queue_details=[],
        )
        assert remaining == 0

    def test_cmuh_no_unfinished_patients(self):
        """CMUH should return 0 if all patients between current and target are completed."""
        scraper = CMUHScraper()
        
        clinic_queue_details = [
            {"number": 3, "status": "完成"},
            {"number": 4, "status": "完成"},
            {"number": 5, "status": "完成"},
        ]
        
        # Current at 2, target at 10, but all between are completed
        remaining = scraper.calculate_remaining_count(
            current_number=2,
            target_number=10,
            clinic_queue_details=clinic_queue_details,
        )
        assert remaining == 0

    def test_cmuh_mixed_status(self):
        """CMUH should handle mixed statuses correctly."""
        scraper = CMUHScraper()
        
        clinic_queue_details = [
            {"number": 5, "status": "未看診"},
            {"number": 6, "status": "完成"},
            {"number": 7, "status": "未看診"},
            {"number": 8, "status": "保留待診"},
            {"number": 9, "status": "完成"},
            {"number": 10, "status": "未看診"},
        ]
        
        # Current at 4, target at 11
        # Between 4 and 11, excluding "完成": 5, 7, 8, 10 = 4 people
        remaining = scraper.calculate_remaining_count(
            current_number=4,
            target_number=11,
            clinic_queue_details=clinic_queue_details,
        )
        assert remaining == 4


class TestCMUHHsinchuScraperRemainingCount:
    """Test CMUH Hsinchu's calculate_remaining_count implementation."""

    def test_cmuh_hsinchu_inherits_from_cmuh(self):
        """CMUH Hsinchu should inherit CMUH's calculation logic."""
        scraper = CMUHHsinchuScraper()
        
        clinic_queue_details = [
            {"number": 1, "status": "完成"},
            {"number": 2, "status": "未看診"},
            {"number": 3, "status": "完成"},
            {"number": 4, "status": "未看診"},
        ]
        
        # Should behave exactly like CMUH
        remaining = scraper.calculate_remaining_count(
            current_number=1,
            target_number=4,
            clinic_queue_details=clinic_queue_details,
        )
        assert remaining == 1  # Only number 2


class TestNTUHScraperRemainingCount:
    """Test NTUH's calculate_remaining_count implementation."""

    def test_ntuh_filters_not_arrived(self):
        """NTUH should filter out patients with '未報到' status."""
        scraper = NTUHHsinchuScraper()
        
        # Sample queue with different statuses
        clinic_queue_details = [
            {"number": 1, "status": "未報到"},
            {"number": 2, "status": "已報到"},
            {"number": 3, "status": "看診中"},
            {"number": 4, "status": "未報到"}, # Filtered
            {"number": 5, "status": "初診"},
            {"number": 6, "status": "已報到"},
        ]
        
        # Current at 2, target at 6
        # Between 2 and 6: 3, 4, 5
        # Statuses: 3:看診中, 4:未報到, 5:初診
        # Remaining (exclude "未報到"): 3, 5 = 2 people
        remaining = scraper.calculate_remaining_count(
            current_number=2,
            target_number=6,
            clinic_queue_details=clinic_queue_details,
        )
        assert remaining == 2

    def test_ntuh_mixed_statuses_filtered(self):
        """NTUH should count only arrived patients."""
        scraper = NTUHHsinchuScraper()
        
        clinic_queue_details = [
            {"number": 3, "status": "未報到"}, # Filtered
            {"number": 4, "status": "已報到"},
            {"number": 5, "status": "看診中"},
            {"number": 6, "status": "初診"},
            {"number": 7, "status": "已報到"},
            {"number": 8, "status": "未報到"}, # Not in range
        ]
        
        # Current at 2, target at 8
        # All between: 3, 4, 5, 6, 7
        # Statuses: 3:未報到, 4:已報到, 5:看診中, 6:初診, 7:已報到
        # Remaining: 4, 5, 6, 7 = 4 people
        remaining = scraper.calculate_remaining_count(
            current_number=2,
            target_number=8,
            clinic_queue_details=clinic_queue_details,
        )
        assert remaining == 4

    def test_ntuh_empty_queue(self):
        """NTUH should return 0 for empty queue."""
        scraper = NTUHHsinchuScraper()
        
        remaining = scraper.calculate_remaining_count(
            current_number=1,
            target_number=10,
            clinic_queue_details=[],
        )
        assert remaining == 0

    def test_ntuh_user_already_passed(self):
        """NTUH should return 0 if user's number is already called."""
        scraper = NTUHHsinchuScraper()
        
        clinic_queue_details = [
            {"number": 1, "status": "已報到"},
            {"number": 2, "status": "已報到"},
            {"number": 3, "status": "已報到"},
        ]
        
        # Current at 5, target at 3 (user already passed)
        remaining = scraper.calculate_remaining_count(
            current_number=5,
            target_number=3,
            clinic_queue_details=clinic_queue_details,
        )
        assert remaining == 0


class TestRealWorldScenarios:
    """Test real-world scenarios mentioned in the issue."""

    def test_ntuh_issue_scenario_with_filtering(self):
        """
        Test the real-world scenario from the issue with status filtering:
        Current: 3, Target: 44
        Queue shows numbers 3-44 with various statuses
        Expected remaining: count between 3 (exclusive) and 44 (exclusive),
        but EXCLUDING "未報到" status.
        """
        scraper = NTUHHsinchuScraper()
        
        # Simulate the scenario: only numbers 4-13 are "已報到"
        clinic_queue_details = []
        for num in range(3, 14):
            clinic_queue_details.append({"number": num, "status": "已報到"})
        
        # Numbers 14 to 44 are "未報到"
        for num in range(14, 45):
            clinic_queue_details.append({"number": num, "status": "未報到"})
        
        # Current at 3, target at 44
        # Between 3 (exclusive) and 44 (exclusive): 4, 5, ... 43
        # Arrived: 4, 5, 6, 7, 8, 9, 10, 11, 12, 13 (10 people)
        # Not arrived: 14 to 43 (Filtered)
        remaining = scraper.calculate_remaining_count(
            current_number=3,
            target_number=44,
            clinic_queue_details=clinic_queue_details,
        )
        assert remaining == 10  # Only arrived patients are counted

    def test_cmuh_realistic_scenario(self):
        """Test realistic CMUH scenario with completed patients."""
        scraper = CMUHScraper()
        
        # Many completed patients
        clinic_queue_details = []
        for num in range(1, 101):
            if num % 2 == 0:
                clinic_queue_details.append({"number": num, "status": "完成"})
            else:
                clinic_queue_details.append({"number": num, "status": "未看診"})
        
        # Current at 10, target at 30
        # Between 10 and 30, excluding "完成": 11, 13, 15, 17, 19, 21, 23, 25, 27, 29 = 10 people
        remaining = scraper.calculate_remaining_count(
            current_number=10,
            target_number=30,
            clinic_queue_details=clinic_queue_details,
        )
        assert remaining == 10
