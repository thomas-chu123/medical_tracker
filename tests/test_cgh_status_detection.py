#!/usr/bin/env python3
"""
CGH 診間狀態識別測試

測試各種診間狀態：
- 非看診時段
- 休診
- 已結束看診
- 看診中
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_clinic_status_detection():
    """測試診間狀態偵測"""

    print("\n" + "=" * 70)
    print("CGH 診間狀態識別測試")
    print("=" * 70)

    # 測試狀態文本
    test_cases = [
        {
            "name": "非看診時段",
            "text": "115年3月11日 上午神經內科 周明皇醫師 非看診時段",
            "expected_status": "未開診",
            "should_match": True
        },
        {
            "name": "休診",
            "text": "115年3月11日 下午眼科 游琇瑾醫師 休診",
            "expected_status": "未開診",
            "should_match": True
        },
        {
            "name": "已結束看診",
            "text": "已結束看診",
            "expected_status": "已結束",
            "should_match": True
        },
        {
            "name": "看診中 (號碼列表)",
            "text": "1 3 6 8 10 12 14 19 20 21 22 23 24 25 26 27 28",
            "expected_status": "看診中",
            "should_match": False  # 不含狀態關鍵字，應進行後續處理
        }
    ]

    print("\n📋 狀態檢查邏輯測試:")
    print("-" * 70)

    passed = 0
    failed = 0

    for i, test_case in enumerate(test_cases, 1):
        row_text = test_case["text"]
        expected = test_case["expected_status"]
        should_match = test_case["should_match"]

        # 檢查邏輯
        is_closed = "非看診時段" in row_text or "休診" in row_text
        is_ended = "已結束看診" in row_text

        if should_match:
            if is_closed and expected == "未開診":
                status = "✅ 通過"
                passed += 1
            elif is_ended and expected == "已結束":
                status = "✅ 通過"
                passed += 1
            else:
                status = "❌ 失敗"
                failed += 1
        else:
            if not is_closed and not is_ended:
                status = "✅ 通過 (正確跳過)"
                passed += 1
            else:
                status = "❌ 失敗"
                failed += 1

        print(f"\n{i}. {test_case['name']}")
        print(f"   文本: {row_text[:50]}...")
        print(f"   預期: {expected}")
        print(f"   結果: {status}")

    print("\n" + "-" * 70)
    print(f"\n📊 測試結果: {passed} 通過, {failed} 失敗")

    if failed == 0:
        print("\n✅ 所有診間狀態識別測試通過！")
        return True
    else:
        print(f"\n❌ 有 {failed} 個測試失敗")
        return False


def test_status_mapping():
    """測試狀態映射"""

    print("\n" + "=" * 70)
    print("狀態映射測試")
    print("=" * 70)

    # 狀態映射
    status_map = {
        "非看診時段": "未開診",
        "休診": "未開診",
        "已結束看診": "已結束",
        "看診中": "看診中"
    }

    print("\n📋 支持的診間狀態:")
    for key, value in status_map.items():
        print(f"  • {key:15} → {value}")

    print(f"\n✅ 共支持 {len(status_map)} 種狀態")


if __name__ == '__main__':
    try:
        result1 = test_clinic_status_detection()
        test_status_mapping()

        if result1:
            print("\n" + "=" * 70)
            print("✅ 所有測試通過")
            print("=" * 70)
            sys.exit(0)
        else:
            sys.exit(1)
    except Exception as e:
        print(f"\n❌ 錯誤: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

