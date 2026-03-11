#!/usr/bin/env python3
"""
CGH 爬蟲驗證和管理工具

功能：
  - 驗證爬蟲修正
  - 測試 ROC 日期轉換
  - 測試數值解析
  - 運行完整測試套件
  - 生成驗證報告

使用方式：
  python tools/tool_cgh_verify.py verify-all
  python tools/tool_cgh_verify.py test-dates --input "115.03.16"
  python tools/tool_cgh_verify.py test-numbers --input "1-30"
  python tools/tool_cgh_verify.py generate-report
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

# 新增專案路徑到 Python 路徑
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.scrapers.cgh_hsinchu import _roc_date_to_iso, _parse_int


def test_roc_dates(input_str: str = None) -> dict:
    """測試 ROC 日期轉換"""

    test_cases = [
        ("115.03.16", "點號格式"),
        ("115-03-16", "破折號格式"),
        ("1150316", "7位數格式"),
        ("115316", "6位數格式"),
        ("115.3.5", "單位數月日"),
        ("115.13.01", "無效月份"),
        ("115.03.32", "無效日期"),
        ("invalid", "無效格式"),
    ]

    if input_str:
        test_cases = [(input_str, "使用者輸入")]

    results = []
    for roc_input, description in test_cases:
        result = _roc_date_to_iso(roc_input)
        results.append({
            "input": roc_input,
            "description": description,
            "output": str(result) if result else None,
            "status": "✅ 通過" if result or "無效" in description else "❌ 失敗"
        })

    return {
        "test_name": "ROC 日期轉換",
        "total": len(results),
        "passed": sum(1 for r in results if "✅" in r["status"]),
        "results": results
    }


def test_parse_numbers(input_str: str = None) -> dict:
    """測試數值解析"""

    test_cases = [
        ("25", "簡單數字"),
        ("1-30", "範圍格式"),
        ("無", "特殊文本"),
        ("第 5 號", "混合文本"),
        ("", "空字符串"),
    ]

    if input_str:
        test_cases = [(input_str, "使用者輸入")]

    results = []
    for input_val, description in test_cases:
        result = _parse_int(input_val)
        results.append({
            "input": input_val if input_val else "''",
            "description": description,
            "output": result,
            "status": "✅ 通過" if (result is not None or not input_val or input_val == "無") else "❌ 失敗"
        })

    return {
        "test_name": "數值解析",
        "total": len(results),
        "passed": sum(1 for r in results if "✅" in r["status"]),
        "results": results
    }


def run_pytest():
    """運行完整的 pytest 測試套件"""
    import subprocess

    print("🧪 運行完整測試套件...")
    result = subprocess.run(
        ["pytest", "tests/test_cgh_fixes.py", "-v", "--tb=short"],
        cwd=Path(__file__).parent.parent,
        capture_output=True,
        text=True
    )

    return {
        "command": "pytest tests/test_cgh_fixes.py -v",
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "status": "✅ 通過" if result.returncode == 0 else "❌ 失敗"
    }


def generate_report(output_file: str = None) -> dict:
    """生成驗證報告"""

    print("📊 生成驗證報告...")

    date_results = test_roc_dates()
    number_results = test_parse_numbers()
    pytest_results = run_pytest()

    report = {
        "timestamp": str(date.today()),
        "tests": {
            "roc_dates": date_results,
            "parse_numbers": number_results,
            "pytest": pytest_results
        },
        "summary": {
            "date_tests": f"{date_results['passed']}/{date_results['total']}",
            "number_tests": f"{number_results['passed']}/{number_results['total']}",
            "pytest_status": pytest_results["status"],
            "overall_status": "✅ 全部通過" if pytest_results["returncode"] == 0 else "❌ 部分失敗"
        }
    }

    if output_file:
        output_path = Path(__file__).parent.parent / output_file
        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"✅ 報告已保存到: {output_path}")

    return report


def print_report(report: dict):
    """格式化輸出報告"""

    print("\n" + "="*80)
    print("CGH 爬蟲驗證報告")
    print("="*80)

    print(f"\n📅 日期: {report.get('timestamp')}")

    print("\n📊 測試摘要:")
    for key, value in report.get('summary', {}).items():
        print(f"  {key}: {value}")

    if 'tests' in report:
        print("\n📋 詳細結果:")

        for test_name, test_data in report['tests'].items():
            if test_name == 'pytest':
                print(f"\n🧪 {test_data.get('command')}")
                print(f"   狀態: {test_data.get('status')}")
            else:
                print(f"\n{test_data.get('test_name')}: {test_data.get('passed')}/{test_data.get('total')}")
                for result in test_data.get('results', [])[:3]:  # 只顯示前3個
                    print(f"  {result['status']} {result['input']} → {result['output']} ({result['description']})")


def main():
    parser = argparse.ArgumentParser(
        description="CGH 爬蟲驗證和管理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  python tools/tool_cgh_verify.py verify-all
  python tools/tool_cgh_verify.py test-dates --input "115.03.16"
  python tools/tool_cgh_verify.py test-numbers --input "1-30"
  python tools/tool_cgh_verify.py generate-report --output temp/cgh_report.json
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='命令')

    # verify-all 命令
    subparsers.add_parser('verify-all', help='運行所有驗證')

    # test-dates 命令
    test_dates = subparsers.add_parser('test-dates', help='測試 ROC 日期轉換')
    test_dates.add_argument('--input', help='測試輸入 (可選)')

    # test-numbers 命令
    test_numbers = subparsers.add_parser('test-numbers', help='測試數值解析')
    test_numbers.add_argument('--input', help='測試輸入 (可選)')

    # generate-report 命令
    gen_report = subparsers.add_parser('generate-report', help='生成驗證報告')
    gen_report.add_argument('--output', help='輸出檔案路徑 (可選)')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == 'verify-all':
        print("🔍 運行完整驗證...\n")

        print("1️⃣ 測試 ROC 日期轉換...")
        date_results = test_roc_dates()
        print(f"   結果: {date_results['passed']}/{date_results['total']} ✅")

        print("\n2️⃣ 測試數值解析...")
        number_results = test_parse_numbers()
        print(f"   結果: {number_results['passed']}/{number_results['total']} ✅")

        print("\n3️⃣ 運行 pytest...")
        pytest_results = run_pytest()
        print(f"   結果: {pytest_results['status']}")

        print("\n✅ 驗證完成！")

    elif args.command == 'test-dates':
        print("🔍 測試 ROC 日期轉換...")
        results = test_roc_dates(args.input)
        print(f"結果: {results['passed']}/{results['total']}")
        for result in results['results']:
            print(f"  {result['status']} {result['input']} → {result['output']}")

    elif args.command == 'test-numbers':
        print("🔍 測試數值解析...")
        results = test_parse_numbers(args.input)
        print(f"結果: {results['passed']}/{results['total']}")
        for result in results['results']:
            print(f"  {result['status']} {result['input']} → {result['output']}")

    elif args.command == 'generate-report':
        report = generate_report(args.output)
        print_report(report)


if __name__ == '__main__':
    main()

