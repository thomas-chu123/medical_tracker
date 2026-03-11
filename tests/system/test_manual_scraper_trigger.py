"""
Manual trigger tool for scraper data collection + Supabase persistence.

Interactive test utility to:
  1. Select a hospital
  2. Choose an action:
       [A] Fetch departments only (display, no DB write)
       [B] Fetch departments + write to Supabase
       [C] Full master data (departments + schedule + snapshots) → Supabase
       [D] Batch all hospitals → Full master data → Supabase

Usage (interactive):
    pytest tests/test_manual_scraper_trigger.py::test_manual_trigger_master_data -v -s
    pytest tests/test_manual_scraper_trigger.py::test_manual_trigger_with_supabase -v -s
    pytest tests/test_manual_scraper_trigger.py::test_trigger_all_hospitals_master_data -v -s

Usage (standalone script):
    python tests/test_manual_scraper_trigger.py
"""

import asyncio
import random
import sys
from typing import Optional
import pytest
import allure

from app.scrapers.hospital_registry import HOSPITAL_SCRAPERS, get_available_hospitals
from app.scrapers.base import DepartmentData, DoctorSlot
from app.services.data_writer import (
    get_hospital_id,
    upsert_department,
    upsert_doctor,
    batch_insert_snapshots,
)
from app.core.timezone import now_utc_str


# ─────────────────────────────────────────────────────────
# UI Helpers
# ─────────────────────────────────────────────────────────

def _divider(char="=", width=70):
    print(char * width)


def display_hospital_menu() -> dict:
    """Display hospital selection menu and return user choice."""
    _divider()
    print("🏥 醫院爬蟲 - 手動觸發工具")
    _divider()

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
            choice = input(f"\n請選擇醫院編號 (0-{len(hospital_list)}): ").strip()
        except (EOFError, OSError):
            pytest.skip("stdin 不是互動式終端，請使用 -s 旗標執行此測試")
            return {}  # unreachable, but keeps type checkers happy
        try:
            n = int(choice)
            if n == 0:
                print("👋 退出程式")
                return {}
            if 1 <= n <= len(hospital_list):
                code, scraper_name = hospital_list[n - 1]
                return {"index": n, "code": code, "scraper_name": scraper_name}
            print(f"❌ 請輸入 0-{len(hospital_list)} 之間的數字")
        except ValueError:
            print("❌ 請輸入有效的數字")


def display_action_menu() -> str:
    """Display action selection menu and return action code."""
    _divider("-")
    print("請選擇操作模式:\n")
    print("  [A] 僅爬取科室列表（不寫入 DB）")
    print("  [B] 爬取科室列表 + 寫入 Supabase")
    print("  [C] 完整主資料爬取（科室＋排班＋快照）→ 寫入 Supabase")
    print("  [0] 返回")
    _divider("-")

    while True:
        try:
            choice = input("\n請輸入選項 (A/B/C/0): ").strip().upper()
        except (EOFError, OSError):
            pytest.skip("stdin 不是互動式終端，請使用 -s 旗標執行此測試")
            return "0"  # unreachable
        if choice in ("A", "B", "C", "0"):
            return choice
        print("❌ 請輸入 A、B、C 或 0")


def display_departments(hospital_code: str, departments: list[DepartmentData]):
    """Pretty-print the scraped departments."""
    print("\n" + "=" * 70)
    print(f"📊 爬取結果 - {hospital_code}")
    print("=" * 70)

    if not departments:
        print("❌ 未找到任何部門")
        return

    print(f"\n✅ 成功爬取 {len(departments)} 個部門:\n")

    by_category: dict[str, list[DepartmentData]] = {}
    for dept in departments:
        cat = dept.category or "其他"
        by_category.setdefault(cat, []).append(dept)

    for category in sorted(by_category.keys()):
        depts = by_category[category]
        label = f"📂 {category}" if category != "其他" else "📂 其他分類"
        print(f"\n{label} ({len(depts)} 個)")
        for dept in depts:
            sort_str = f" (排序: {dept.sort_order})" if dept.sort_order else ""
            print(f"   • {dept.code:15} → {dept.name}{sort_str}")

    print(f"\n📈 統計:")
    print(f"   • 總部門數: {len(departments)}")
    print(f"   • 分類數:   {len(by_category)}")

    if departments:
        d = departments[0]
        print(f"\n📝 首個部門範例:")
        print(f"   Code:       {d.code}")
        print(f"   Name:       {d.name}")
        print(f"   Hospital:   {d.hospital_code}")
        print(f"   Category:   {d.category}")
        print(f"   Sort Order: {d.sort_order}")


# ─────────────────────────────────────────────────────────
# Core scrape actions
# ─────────────────────────────────────────────────────────

async def action_fetch_departments(hospital_code: str) -> tuple[bool, list[DepartmentData]]:
    """Fetch departments only, no DB write."""
    scraper_class = HOSPITAL_SCRAPERS.get(hospital_code)
    if not scraper_class:
        print(f"❌ 醫院代碼 '{hospital_code}' 未找到")
        return False, []

    scraper = scraper_class()
    try:
        print(f"\n⏳ 正在從 {hospital_code} 爬取科室列表...")
        print(f"   爬蟲類別: {scraper_class.__name__}")
        print(f"   Base URL:  {scraper.BASE_URL}")

        departments = await scraper.fetch_departments()
        print(f"\n✅ 成功爬取 {len(departments)} 個部門")
        return True, departments

    except Exception as e:
        print(f"\n❌ 爬取失敗: {e}")
        import traceback; traceback.print_exc()
        return False, []
    finally:
        await scraper.close()


async def action_write_departments(hospital_code: str) -> tuple[bool, list[DepartmentData], int]:
    """
    Fetch departments and upsert to Supabase.

    Returns:
        (success, departments, written_count)
    """
    scraper_class = HOSPITAL_SCRAPERS.get(hospital_code)
    if not scraper_class:
        print(f"❌ 醫院代碼 '{hospital_code}' 未找到")
        return False, [], 0

    scraper = scraper_class()
    try:
        print(f"\n⏳ 正在從 {hospital_code} 爬取科室列表...")
        departments = await scraper.fetch_departments()
        print(f"\n✅ 成功爬取 {len(departments)} 個部門")

        # Resolve hospital UUID
        hosp_id = await get_hospital_id(hospital_code)
        if not hosp_id:
            print(f"❌ 在 Supabase 中找不到醫院代碼: {hospital_code}")
            print("   請確認 hospitals 資料表中存在此醫院記錄。")
            return False, departments, 0

        print(f"\n💾 正在寫入 Supabase（hosp_id={hosp_id}）...")
        written = 0
        for dept in departments:
            try:
                await upsert_department(hosp_id, dept)
                written += 1
                print(f"   ✅ [{written:3d}/{len(departments)}] {dept.code:15} {dept.name}")
            except Exception as e:
                print(f"   ❌ 寫入失敗 {dept.code}: {e}")

        print(f"\n💾 寫入完成: {written}/{len(departments)} 個部門已寫入 Supabase")
        return True, departments, written

    except Exception as e:
        print(f"\n❌ 失敗: {e}")
        import traceback; traceback.print_exc()
        return False, [], 0
    finally:
        await scraper.close()


async def action_full_master_data(hospital_code: str) -> dict:
    """
    Full master data pipeline:
      departments → upsert → fetch_schedule per dept → upsert doctors → batch_insert snapshots.

    Mirrors the scheduler's _scrape_hospital_master_data() logic.

    Returns:
        dict with keys: success, dept_count, doctor_count, snapshot_count, errors
    """
    scraper_class = HOSPITAL_SCRAPERS.get(hospital_code)
    if not scraper_class:
        print(f"❌ 醫院代碼 '{hospital_code}' 未找到")
        return {"success": False, "dept_count": 0, "doctor_count": 0, "snapshot_count": 0, "errors": []}

    scraper = scraper_class()
    errors: list[str] = []

    try:
        # ── 1. Hospital UUID ─────────────────────────────────
        hosp_id = await get_hospital_id(hospital_code)
        if not hosp_id:
            print(f"❌ 在 Supabase 中找不到醫院代碼: {hospital_code}")
            print("   請先在 hospitals 資料表中建立此醫院記錄。")
            return {"success": False, "dept_count": 0, "doctor_count": 0, "snapshot_count": 0, "errors": ["醫院不存在"]}

        print(f"\n⏳ [{hospital_code}] 開始完整主資料爬取 (hosp_id={hosp_id})...")

        # ── 2. Departments ───────────────────────────────────
        departments = await scraper.fetch_departments()
        print(f"   📂 爬取到 {len(departments)} 個部門")

        dept_count = 0
        doctor_count = 0
        snapshot_rows: list[dict] = []

        # ── 3. Per-department schedule ───────────────────────
        for dept in departments:
            if "_" in dept.code:   # skip compound codes
                continue

            try:
                dept_id = await upsert_department(hosp_id, dept)
                dept_count += 1
            except Exception as e:
                err = f"upsert_department {dept.code}: {e}"
                print(f"   ❌ {err}")
                errors.append(err)
                continue

            # Small delay between departments (polite scraping)
            await asyncio.sleep(random.uniform(0.5, 1.5))

            try:
                slots = await scraper.fetch_schedule(dept.code)
                print(f"   🩺 {dept.name:20} ({dept.code}): {len(slots)} 個時段")
            except Exception as e:
                err = f"fetch_schedule {dept.code}: {e}"
                print(f"   ⚠️  {err}")
                errors.append(err)
                continue

            # ── 4. Doctors ───────────────────────────────────
            doc_map: dict[str, str] = {}
            for slot in slots:
                if slot.doctor_no in doc_map:
                    doctor_id = doc_map[slot.doctor_no]
                else:
                    try:
                        doctor_id = await upsert_doctor(hosp_id, dept_id, slot)
                        doc_map[slot.doctor_no] = doctor_id
                        doctor_count += 1
                    except Exception as e:
                        err = f"upsert_doctor {slot.doctor_name}: {e}"
                        errors.append(err)
                        continue

                # ── 5. Build snapshot row ─────────────────────
                snapshot_rows.append({
                    "doctor_id": doctor_id,
                    "department_id": dept_id,
                    "session_date": str(slot.session_date),
                    "session_type": slot.session_type,
                    "clinic_room": slot.clinic_room or "",
                    "total_quota": slot.total_quota,
                    "current_registered": slot.registered,
                    "current_number": slot.current_number,
                    "is_full": slot.is_full,
                    "status": slot.status,
                    "scraped_at": now_utc_str(),
                })

        # ── 6. Batch upsert snapshots ────────────────────────
        snapshot_count = len(snapshot_rows)
        if snapshot_rows:
            print(f"\n💾 正在批次寫入 {snapshot_count} 筆快照資料到 Supabase...")
            try:
                await batch_insert_snapshots(snapshot_rows)
                print(f"   ✅ 成功寫入 {snapshot_count} 筆快照")
            except Exception as e:
                err = f"batch_insert_snapshots: {e}"
                print(f"   ❌ {err}")
                errors.append(err)

        return {
            "success": True,
            "dept_count": dept_count,
            "doctor_count": doctor_count,
            "snapshot_count": snapshot_count,
            "errors": errors,
        }

    except Exception as e:
        import traceback; traceback.print_exc()
        return {"success": False, "dept_count": 0, "doctor_count": 0, "snapshot_count": 0, "errors": [str(e)]}
    finally:
        await scraper.close()


# ─────────────────────────────────────────────────────────
# Interactive runner
# ─────────────────────────────────────────────────────────

def run_interactive():
    while True:
        print("\n")
        hospital_choice = display_hospital_menu()
        if not hospital_choice:
            break

        hospital_code = hospital_choice["code"]
        scraper_name = hospital_choice["scraper_name"]
        print(f"\n✨ 已選擇: [{hospital_choice['index']}] {hospital_code} ({scraper_name})")

        action = display_action_menu()
        if action == "0":
            continue

        # ── Action A: fetch only ──────────────────────────
        if action == "A":
            success, departments = asyncio.run(action_fetch_departments(hospital_code))
            if success:
                display_departments(hospital_code, departments)

        # ── Action B: fetch + write departments ──────────
        elif action == "B":
            success, departments, written = asyncio.run(action_write_departments(hospital_code))
            if success:
                display_departments(hospital_code, departments)
                print(f"\n🗄️  已寫入 Supabase: {written}/{len(departments)} 個部門")

        # ── Action C: full master data ────────────────────
        elif action == "C":
            result = asyncio.run(action_full_master_data(hospital_code))
            print("\n" + "=" * 70)
            print(f"📊 完整主資料爬取結果 - {hospital_code}")
            print("=" * 70)
            status_icon = "✅" if result["success"] else "❌"
            print(f"\n{status_icon} 狀態：{'成功' if result['success'] else '失敗'}")
            print(f"   📂 部門：{result['dept_count']} 個")
            print(f"   🩺 醫師：{result['doctor_count']} 位")
            print(f"   📋 快照：{result['snapshot_count']} 筆")
            if result["errors"]:
                print(f"\n⚠️  警告/錯誤 ({len(result['errors'])} 項):")
                for err in result["errors"][:10]:
                    print(f"   • {err}")

        print("\n" + "-" * 70)
        cont = input("是否繼續? (y/n): ").strip().lower()
        if cont != "y":
            print("👋 感謝使用")
            break


# ─────────────────────────────────────────────────────────
# pytest Tests
# ─────────────────────────────────────────────────────────

@allure.feature("Manual Testing")
@allure.story("Trigger Master Data Scraper")

# @pytest.mark.skip(reason="Covered by test_manual_trigger_with_supabase option A — run directly if needed: pytest tests/test_manual_scraper_trigger.py::test_manual_trigger_master_data -v -s")
@pytest.mark.asyncio
async def test_manual_trigger_master_data():
    """
    Interactive test: select hospital → fetch departments → display (no DB write).

    Run with: pytest tests/test_manual_scraper_trigger.py::test_manual_trigger_master_data -v -s
    """
    print("\n\n" + "=" * 70)
    print("🧪 pytest 交互式爬蟲觸發工具")
    print("=" * 70)

    hospital_choice = display_hospital_menu()
    if not hospital_choice:
        pytest.skip("用戶選擇退出")

    hospital_code = hospital_choice["code"]
    print(f"\n✨ 已選擇: [{hospital_choice['index']}] {hospital_code} ({hospital_choice['scraper_name']})")

    success, departments = await action_fetch_departments(hospital_code)

    assert success, f"爬蟲執行失敗: {hospital_code}"
    assert isinstance(departments, list)

    display_departments(hospital_code, departments)

    assert len(departments) > 0, f"{hospital_code} 應至少有一個部門"
    for dept in departments:
        assert isinstance(dept, DepartmentData)
        assert dept.code
        assert dept.name
        assert dept.hospital_code == hospital_code

    print(f"\n✅ 測試通過: 成功爬取 {len(departments)} 個部門")


@allure.feature("Manual Testing")
@allure.story("Trigger Scraper with Supabase Write")
@pytest.mark.asyncio
async def test_manual_trigger_with_supabase():
    """
    Interactive test: select hospital and action → optionally write to Supabase.

    Actions:
      [A] Fetch departments only
      [B] Fetch departments + write to Supabase
      [C] Full master data (departments + schedule + snapshots) → Supabase

    Run with: pytest tests/test_manual_scraper_trigger.py::test_manual_trigger_with_supabase -v -s
    """
    print("\n\n" + "=" * 70)
    print("🧪 pytest 交互式爬蟲與 Supabase 寫入工具")
    print("=" * 70)

    hospital_choice = display_hospital_menu()
    if not hospital_choice:
        pytest.skip("用戶選擇退出")

    hospital_code = hospital_choice["code"]
    print(f"\n✨ 已選擇: [{hospital_choice['index']}] {hospital_code} ({hospital_choice['scraper_name']})")

    action = display_action_menu()
    if action == "0":
        pytest.skip("用戶選擇返回")

    # ── Action A ──────────────────────────────────────────
    if action == "A":
        success, departments = await action_fetch_departments(hospital_code)
        assert success, "爬取失敗"
        display_departments(hospital_code, departments)
        assert len(departments) > 0
        print(f"\n✅ 測試通過（僅爬取，未寫入）: {len(departments)} 個部門")

    # ── Action B ──────────────────────────────────────────
    elif action == "B":
        success, departments, written = await action_write_departments(hospital_code)
        assert success, "爬取或寫入失敗"
        display_departments(hospital_code, departments)
        assert len(departments) > 0
        assert written > 0, f"應至少寫入一個部門，實際寫入: {written}"
        print(f"\n✅ 測試通過: {len(departments)} 個部門爬取，{written} 個寫入 Supabase")

    # ── Action C ──────────────────────────────────────────
    elif action == "C":
        result = await action_full_master_data(hospital_code)
        print("\n" + "=" * 70)
        print(f"📊 完整主資料爬取結果 - {hospital_code}")
        print("=" * 70)
        status_icon = "✅" if result["success"] else "❌"
        print(f"\n{status_icon} 狀態：{'成功' if result['success'] else '失敗'}")
        print(f"   📂 部門：{result['dept_count']} 個")
        print(f"   🩺 醫師：{result['doctor_count']} 位")
        print(f"   📋 快照：{result['snapshot_count']} 筆")
        if result["errors"]:
            print(f"\n⚠️  警告/錯誤 ({len(result['errors'])} 項):")
            for err in result["errors"][:10]:
                print(f"   • {err}")

        assert result["success"], "完整主資料爬取失敗"
        assert result["dept_count"] > 0, "應至少寫入一個部門"
        print(f"\n✅ 測試通過: 完整主資料已寫入 Supabase")


@allure.feature("Manual Testing")
@allure.story("Batch Trigger All Hospitals")
@pytest.mark.asyncio
async def test_trigger_all_hospitals_master_data():
    """
    Non-interactive batch test: fetch departments for all hospitals, display summary.
    Does NOT write to Supabase.

    Run with: pytest tests/test_manual_scraper_trigger.py::test_trigger_all_hospitals_master_data -v -s
    """
    print("\n\n" + "=" * 70)
    print("🧪 批量爬取所有醫院主資料")
    print("=" * 70)

    hospitals = get_available_hospitals()
    results: dict[str, dict] = {}

    for hospital_code, scraper_name in hospitals.items():
        print(f"\n[{hospital_code}] 正在爬取...")
        success, departments = await action_fetch_departments(hospital_code)
        results[hospital_code] = {
            "success": success,
            "department_count": len(departments),
            "scraper": scraper_name,
        }
        if success:
            print(f"  ✅ 成功: {len(departments)} 個部門")
        else:
            print(f"  ❌ 失敗")

    # Summary
    print("\n" + "=" * 70)
    print("📊 批量爬取結果摘要")
    print("=" * 70)

    total_success = 0
    total_departments = 0

    for code, r in results.items():
        icon = "✅" if r["success"] else "❌"
        print(f"{icon} {code:20} → {r['department_count']:3d} 個部門")
        if r["success"]:
            total_success += 1
            total_departments += r["department_count"]

    print(f"\n✨ 成功爬取: {total_success}/{len(hospitals)} 個醫院")
    print(f"📈 總部門數: {total_departments}")

    assert total_success > 0, "至少應有一個醫院爬蟲成功"
    assert total_departments > 0, "至少應爬取到一個部門"


# ─────────────────────────────────────────────────────────
# CLI Entry Point
# ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("🏥 醫院爬蟲 - 手動觸發工具")
    print("=" * 70)
    print("\n本程式可以手動觸發醫院爬蟲，支援將資料寫入 Supabase。\n")
    try:
        run_interactive()
    except KeyboardInterrupt:
        print("\n\n👋 程式已中斷")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 發生錯誤: {e}")
        import traceback; traceback.print_exc()
        sys.exit(1)
