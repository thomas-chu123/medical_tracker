"""
Manual trigger for scraper master data collection.

Interactive test utility to:
1. List all available hospitals
2. Select a hospital by number
3. Trigger fetch_departments() for that hospital
4. Display and verify the results

Usage:
    # Run as pytest test (interactive)
    pytest tests/test_manual_scraper_trigger.py::test_manual_trigger_master_data -v -s
    
    # Or run as a script
    python tests/test_manual_scraper_trigger.py
"""

import asyncio
import sys
from typing import Optional
import pytest
import allure

from app.scrapers.hospital_registry import HOSPITAL_SCRAPERS, get_available_hospitals
from app.scrapers.base import DepartmentData


def display_menu() -> dict:
    """Display hospital selection menu and return user choice."""
    print("\n" + "=" * 70)
    print("🏥 醫院爬蟲 - 手動觸發工具")
    print("=" * 70)
    
    hospitals = get_available_hospitals()
    hospital_list = list(hospitals.items())
    
    print("\n可用的醫院爬蟲:\n")
    for idx, (code, scraper_name) in enumerate(hospital_list, 1):
        print(f"  [{idx}] {code}")
        print(f"      爬蟲類別: {scraper_name}")
    
    print(f"\n  [0] 退出")
    print("\n" + "-" * 70)
    
    while True:
        try:
            choice = input("\n請選擇醫院編號 (0-{}): ".format(len(hospital_list))).strip()
            choice_num = int(choice)
            
            if choice_num == 0:
                print("👋 退出程式")
                return {}
            
            if 1 <= choice_num <= len(hospital_list):
                code, scraper_name = hospital_list[choice_num - 1]
                return {
                    "index": choice_num,
                    "code": code,
                    "scraper_name": scraper_name,
                }
            else:
                print(f"❌ 請輸入 0-{len(hospital_list)} 之間的數字")
        except ValueError:
            print("❌ 請輸入有效的數字")


async def trigger_master_data(hospital_code: str) -> tuple[bool, list[DepartmentData]]:
    """
    Trigger fetch_departments() for a specific hospital.
    
    Args:
        hospital_code: Hospital code (e.g., 'CMUH_TAICHUNG')
        
    Returns:
        Tuple[bool, list[DepartmentData]]: (Success, departments)
    """
    if hospital_code not in HOSPITAL_SCRAPERS:
        print(f"❌ 醫院代碼 '{hospital_code}' 未找到")
        return False, []
    
    scraper_class = HOSPITAL_SCRAPERS[hospital_code]
    scraper = scraper_class()
    
    try:
        print(f"\n⏳ 正在從 {hospital_code} 爬取部門列表...")
        print(f"   爬蟲類別: {scraper_class.__name__}")
        print(f"   Base URL: {scraper.BASE_URL}")
        
        departments = await scraper.fetch_departments()
        
        print(f"\n✅ 成功爬取 {len(departments)} 個部門")
        return True, departments
        
    except Exception as e:
        print(f"\n❌ 爬取失敗: {e}")
        import traceback
        traceback.print_exc()
        return False, []
    finally:
        await scraper.close()


def display_results(hospital_code: str, departments: list[DepartmentData]):
    """Display the scraped departments."""
    print("\n" + "=" * 70)
    print(f"📊 爬取結果 - {hospital_code}")
    print("=" * 70)
    
    if not departments:
        print("❌ 未找到任何部門")
        return
    
    print(f"\n✅ 成功爬取 {len(departments)} 個部門:\n")
    
    # Group by category if available
    by_category = {}
    for dept in departments:
        cat = dept.category or "其他"
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(dept)
    
    # Display grouped departments
    for category in sorted(by_category.keys()):
        depts = by_category[category]
        if category != "其他":
            print(f"\n📂 {category} ({len(depts)} 個)")
        else:
            print(f"\n📂 其他分類 ({len(depts)} 個)")
        
        for dept in depts:
            sort_str = f" (排序: {dept.sort_order})" if dept.sort_order else ""
            print(f"   • {dept.code:15} → {dept.name}{sort_str}")
    
    print(f"\n📈 統計:")
    print(f"   • 總部門數: {len(departments)}")
    print(f"   • 分類數: {len(by_category)}")
    
    # Sample display
    if departments:
        print(f"\n📝 首個部門範例:")
        dept = departments[0]
        print(f"   Code: {dept.code}")
        print(f"   Name: {dept.name}")
        print(f"   Hospital: {dept.hospital_code}")
        print(f"   Category: {dept.category}")
        print(f"   Sort Order: {dept.sort_order}")


def run_interactive():
    """Run the interactive menu."""
    while True:
        choice = display_menu()
        
        if not choice:
            break
        
        hospital_code = choice["code"]
        scraper_name = choice["scraper_name"]
        
        print(f"\n✨ 已選擇: [{choice['index']}] {hospital_code} ({scraper_name})")
        
        # Trigger scraper
        success, departments = asyncio.run(trigger_master_data(hospital_code))
        
        if success:
            display_results(hospital_code, departments)
        
        # Ask for next action
        print("\n" + "-" * 70)
        next_action = input("是否繼續? (y/n): ").strip().lower()
        if next_action != 'y':
            print("👋 感謝使用")
            break


# ─────────────────────────────────────────────────────────
# pytest Tests
# ─────────────────────────────────────────────────────────

@allure.feature("Manual Testing")
@allure.story("Trigger Master Data Scraper")
@pytest.mark.asyncio
async def test_manual_trigger_master_data():
    """
    Manual test to trigger master data scraper for selected hospital.
    
    This test is interactive and allows selecting a hospital via menu.
    Run with: pytest tests/test_manual_scraper_trigger.py::test_manual_trigger_master_data -v -s
    """
    print("\n\n" + "=" * 70)
    print("🧪 pytest 交互式爬蟲觸發工具")
    print("=" * 70)
    
    choice = display_menu()
    
    if not choice:
        pytest.skip("用戶選擇退出")
    
    hospital_code = choice["code"]
    scraper_name = choice["scraper_name"]
    
    print(f"\n✨ 已選擇: [{choice['index']}] {hospital_code} ({scraper_name})")
    
    # Trigger scraper
    success, departments = await trigger_master_data(hospital_code)
    
    # Verify results
    assert success, f"爬蟲執行失敗: {hospital_code}"
    assert isinstance(departments, list), "應回傳部門列表"
    
    # Display results
    display_results(hospital_code, departments)
    
    # Basic assertions
    assert len(departments) > 0, f"{hospital_code} 應至少有一個部門"
    
    # Verify department structure
    for dept in departments:
        assert isinstance(dept, DepartmentData), "應為 DepartmentData 實例"
        assert dept.code, "部門代碼不應為空"
        assert dept.name, "部門名稱不應為空"
        assert dept.hospital_code == hospital_code, "醫院代碼應匹配"
    
    print(f"\n✅ 測試通過: 成功爬取 {len(departments)} 個部門")


@allure.feature("Manual Testing")
@allure.story("Batch Trigger All Hospitals")
@pytest.mark.asyncio
async def test_trigger_all_hospitals_master_data():
    """
    Trigger master data scraper for all available hospitals.
    
    Non-interactive batch test that runs all hospitals.
    Run with: pytest tests/test_manual_scraper_trigger.py::test_trigger_all_hospitals_master_data -v -s
    """
    print("\n\n" + "=" * 70)
    print("🧪 批量爬取所有醫院主資料")
    print("=" * 70)
    
    hospitals = get_available_hospitals()
    results = {}
    
    for hospital_code, scraper_name in hospitals.items():
        print(f"\n[{hospital_code}] 正在爬取...")
        
        success, departments = await trigger_master_data(hospital_code)
        results[hospital_code] = {
            "success": success,
            "department_count": len(departments),
            "scraper": scraper_name,
        }
        
        if success:
            print(f"  ✅ 成功: {len(departments)} 個部門")
        else:
            print(f"  ❌ 失敗")
    
    # Display summary
    print("\n" + "=" * 70)
    print("📊 批量爬取結果摘要")
    print("=" * 70)
    
    total_success = 0
    total_departments = 0
    
    for code, result in results.items():
        status = "✅" if result["success"] else "❌"
        print(f"{status} {code:20} → {result['department_count']:3d} 個部門")
        if result["success"]:
            total_success += 1
            total_departments += result["department_count"]
    
    print(f"\n✨ 成功爬取: {total_success}/{len(hospitals)} 個醫院")
    print(f"📈 總部門數: {total_departments}")
    
    # Assertions
    assert total_success > 0, "至少應有一個醫院爬蟲成功"
    assert total_departments > 0, "至少應爬取到一個部門"


# ─────────────────────────────────────────────────────────
# CLI Entry Point
# ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    """
    Run as standalone script:
        python tests/test_manual_scraper_trigger.py
    """
    print("\n" + "=" * 70)
    print("🏥 醫院爬蟲 - 手動觸發工具")
    print("=" * 70)
    print("\n本程式可以手動觸發醫院爬蟲來測試和驗證爬蟲功能。\n")
    
    try:
        run_interactive()
    except KeyboardInterrupt:
        print("\n\n👋 程式已中斷")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 發生錯誤: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
