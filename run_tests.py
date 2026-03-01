#!/usr/bin/env python3
"""
Medical Tracker Test Runner

This script provides a centralized entry point to run various categories of tests
in the test suite. It wraps pytest and automatically generates Allure reports.

Usage:
  # Run all tests
  python run_tests.py
  
  # Run a specific category (unit, api, e2e, data, scraper, notification, system, performance)
  python run_tests.py --category api
  
  # Generate and serve the Allure report after running
  python run_tests.py --serve-report

  # Run specific category and serve report
  python run_tests.py --category e2e --serve-report
"""

import argparse
import sys
import subprocess
import os

# Define available test categories and their corresponding directory paths
CATEGORIES = {
    "unit": "tests/unit",
    "api": "tests/api",
    "e2e": "tests/e2e",
    "data": "tests/data",
    "scraper": "tests/scraper",
    "notification": "tests/notification",
    "system": "tests/system",
    "performance": "tests/performance",
}

def main():
    parser = argparse.ArgumentParser(description="Medical Tracker Test Runner")
    parser.add_argument(
        "--category",
        "-c",
        choices=list(CATEGORIES.keys()) + ["all"],
        default="all",
        help="Run tests in a specific category (default: all)"
    )
    parser.add_argument(
        "--serve-report",
        "-s",
        action="store_true",
        help="Serve the Allure test report after running tests"
    )
    parser.add_argument(
        "--serve-only",
        action="store_true",
        help="Only serve existing Allure report without running tests"
    )
    parser.add_argument(
        "--extra-args",
        "-e",
        default="",
        help="Extra arguments to pass directly to pytest (e.g., '-v -s')"
    )

    args = parser.parse_args()

    # If --serve-only is specified, skip test execution and directly serve the report
    if args.serve_only:
        print("📊 Serving existing Allure report...")
        try:
            subprocess.run(["allure", "serve", "allure-results"])
        except FileNotFoundError:
            print("❌ Error: 'allure' command not found. Please install Allure commandline tools.")
            print("Instruction: brew install allure")
        sys.exit(0)

    # Determine target path
    if args.category == "all":
        target = "tests/"
    else:
        target = CATEGORIES[args.category]

    print(f"==================================================")
    print(f"🚀 Running Medical Tracker Tests: {args.category.upper()}")
    print(f"📁 Target: {target}")
    print(f"==================================================\n")

    # Ensure allure-results directory exists
    os.makedirs("allure-results", exist_ok=True)

    # Base pytest command
    pytest_cmd = [
        "pytest",
        target,
        "--alluredir=allure-results"
    ]

    # Add extra arguments if provided
    if args.extra_args:
        # Simple split by space; for complex args, use shlex
        pytest_cmd.extend(args.extra_args.split())

    # Execute pytest 
    # Use subprocess.run to allow pytest's rich output to flow to stdout/stderr
    try:
        result = subprocess.run(pytest_cmd, check=False)
        exit_code = result.returncode
    except FileNotFoundError:
        print("❌ Error: 'pytest' command not found. Are you in the virtual environment?")
        sys.exit(1)

    print(f"\n==================================================")
    print(f"✅ Test run completed with exit code: {exit_code}")
    print(f"📋 Allure results saved to 'allure-results/'")
    print(f"==================================================\n")

    if args.serve_report:
        print("📊 Spinning up Allure report server...")
        try:
            subprocess.run(["allure", "serve", "allure-results"])
        except FileNotFoundError:
            print("❌ Error: 'allure' command not found. Please install Allure commandline tools.")
            print("Instruction: brew install allure")
    else:
        print("💡 Tip: To view the visual report, run: python run_tests.py --serve-report")

    sys.exit(exit_code)

if __name__ == "__main__":
    main()
