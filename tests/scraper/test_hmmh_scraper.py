"""
Test script for HMMH scraper

Usage:
    python -m tests.test_hmmh_scraper
"""

import asyncio
from app.scrapers.hmmh import HMMHScraper


async def test_fetch_departments():
    """Test fetching department list"""
    print("=" * 60)
    print("Testing HMMH fetch_departments()")
    print("=" * 60)
    
    scraper = HMMHScraper()
    try:
        depts = await scraper.fetch_departments()
        print(f"\n✅ Found {len(depts)} departments\n")
        
        # Print first 10 departments
        for i, dept in enumerate(depts[:10], 1):
            print(f"{i:2d}. [{dept.code:3s}] {dept.name:20s} - {dept.category}")
        
        if len(depts) > 10:
            print(f"... and {len(depts) - 10} more departments")
        
        return depts
    finally:
        await scraper.close()


async def test_fetch_clinic_progress():
    """Test fetching clinic progress"""
    print("\n" + "=" * 60)
    print("Testing HMMH fetch_clinic_progress()")
    print("=" * 60)
    
    scraper = HMMHScraper()
    try:
        # Test with dept=14 (一般外科), period=1 (上午)
        dept_code = "14"
        period = "1"
        print(f"\nFetching progress for dept={dept_code}, period={period} (上午)")
        
        progress = await scraper.fetch_clinic_progress(dept_code, period)
        
        if progress:
            print(f"\n✅ Clinic Progress Retrieved:")
            print(f"  Clinic Room: {progress.clinic_room}")
            print(f"  Session Type: {progress.session_type}")
            print(f"  Current Number: {progress.current_number}")
            print(f"  Total Quota: {progress.total_quota}")
            print(f"  Registered Count: {progress.registered_count}")
            print(f"  Status: {progress.status}")
            print(f"  Waiting List: {len(progress.waiting_list)} patients")
            
            if progress.clinic_queue_details:
                print(f"\n  Queue Details (first 5):")
                for detail in progress.clinic_queue_details[:5]:
                    print(f"    #{detail['number']:3d} - {detail['status']}")
                if len(progress.clinic_queue_details) > 5:
                    print(f"    ... and {len(progress.clinic_queue_details) - 5} more")
        else:
            print("\n⚠️  No progress data available (might be outside clinic hours)")
        
        return progress
    finally:
        await scraper.close()


async def test_fetch_schedule():
    """Test fetching doctor schedule"""
    print("\n" + "=" * 60)
    print("Testing HMMH fetch_schedule()")
    print("=" * 60)
    
    scraper = HMMHScraper()
    try:
        # Test with dept=14 (一般外科)
        dept_code = "14"
        print(f"\nFetching schedule for dept={dept_code}")
        
        slots = await scraper.fetch_schedule(dept_code)
        
        if slots:
            print(f"\n✅ Found {len(slots)} doctor slots\n")
            for i, slot in enumerate(slots[:5], 1):
                print(f"{i}. Dr. {slot.doctor_name} - {slot.session_date} {slot.session_type}")
            if len(slots) > 5:
                print(f"... and {len(slots) - 5} more slots")
        else:
            print("\n⚠️  No schedule data (fetch_schedule not yet fully implemented)")
        
        return slots
    finally:
        await scraper.close()


async def main():
    """Run all tests"""
    print("\n🏥 馬偕紀念醫院新竹分院 (HMMH) Scraper Test\n")
    
    # Test 1: Fetch departments
    depts = await test_fetch_departments()
    
    # Test 2: Fetch clinic progress
    await test_fetch_clinic_progress()
    
    # Test 3: Fetch schedule (not yet implemented)
    await test_fetch_schedule()
    
    print("\n" + "=" * 60)
    print("✅ All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
