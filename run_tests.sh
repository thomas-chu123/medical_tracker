#!/bin/bash

# Selenium Test Runner Script
# 便捷運行 Selenium UI 測試的腳本

set -e

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 函數定義
print_header() {
    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ️  $1${NC}"
}

# 檢查 Python
check_python() {
    print_header "檢查 Python"
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 未找到"
        exit 1
    fi
    PYTHON_VERSION=$(python3 --version)
    print_success "Found: $PYTHON_VERSION"
}

# 檢查依賴
check_dependencies() {
    print_header "檢查依賴"
    if ! python3 -m pip show selenium &> /dev/null; then
        print_info "Installing Selenium dependencies..."
        python3 -m pip install -r requirements.txt -q
    fi
    print_success "All dependencies installed"
}

# 檢查 Chrome
check_chrome() {
    print_header "檢查 Chrome"
    if command -v google-chrome &> /dev/null; then
        CHROME_PATH="google-chrome"
    elif command -v 'google-chrome-stable' &> /dev/null; then
        CHROME_PATH="google-chrome-stable"
    elif command -v /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome &> /dev/null; then
        CHROME_PATH="/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome"
    else
        print_error "Chrome 未找到"
        exit 1
    fi
    CHROME_VERSION=$("$CHROME_PATH" --version)
    print_success "Found: $CHROME_VERSION"
}

# 檢查服務器
check_server() {
    print_header "檢查服務器"
    if curl -s http://localhost:8000/health &> /dev/null; then
        print_success "服務器運行中: http://localhost:8000"
        SERVER_RUNNING=true
    else
        print_error "服務器未運行"
        print_info "啟動服務器: python -m uvicorn app.main:app --reload"
        SERVER_RUNNING=false
    fi
}

# 運行數據驗證測試（無需服務器）
run_data_tests() {
    print_header "運行數據驗證測試（無需服務器）"
    
    python3 -m pytest tests/test_ui_e2e_minimal.py::TestE2EMinimal::test_07_notification_logs_exist \
                     tests/test_ui_e2e_minimal.py::TestE2EMinimal::test_08_tracking_subscriptions_exist \
                     tests/test_ui_e2e_minimal.py::TestE2EMinimal::test_09_line_notification_system \
                     tests/test_ui_e2e_minimal.py::TestE2EMinimal::test_10_email_notification_system \
                     -v --tb=short
}

# 運行最小 E2E 測試（無需服務器）
run_minimal_e2e() {
    print_header "運行最小 E2E 測試"
    
    python3 -m pytest tests/test_ui_e2e_minimal.py::TestE2EMinimal::test_01_navigate_to_home \
                     -v --tb=short
}

# 運行所有最小 E2E 測試（需要服務器）
run_all_minimal_e2e() {
    print_header "運行所有最小 E2E 測試"
    
    if [ "$SERVER_RUNNING" = false ]; then
        print_error "需要運行中的服務器"
        exit 1
    fi
    
    python3 -m pytest tests/test_ui_e2e_minimal.py -v -s --tb=short
}

# 運行完整 UI 測試（需要服務器）
run_full_ui() {
    print_header "運行完整 UI 功能測試"
    
    if [ "$SERVER_RUNNING" = false ]; then
        print_error "需要運行中的服務器"
        exit 1
    fi
    
    export SELENIUM_HEADLESS=false
    python3 -m pytest tests/test_ui_selenium.py -v -s --tb=short
}

# 運行所有單元測試
run_unit_tests() {
    print_header "運行所有單元和集成測試"
    
    python3 -m pytest tests/ \
                     --ignore=tests/test_ui_selenium.py \
                     --ignore=tests/test_ui_e2e_minimal.py \
                     -v --tb=short
}

# 啟動開發服務器
start_server() {
    print_header "啟動開發服務器"
    print_info "服務器將在 http://localhost:8000 啟動"
    print_info "按 Ctrl+C 停止服務器"
    python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
}

# 顯示菜單
show_menu() {
    echo ""
    echo -e "${BLUE}選擇要運行的測試:${NC}"
    echo "  1. 數據驗證測試 (無需服務器)"
    echo "  2. 最小 E2E 測試 (無需服務器)"
    echo "  3. 所有最小 E2E 測試 (需要服務器)"
    echo "  4. 完整 UI 功能測試 (需要服務器)"
    echo "  5. 所有單元和集成測試 (無需服務器)"
    echo "  6. 啟動開發服務器"
    echo "  0. 退出"
    echo ""
}

# 主函數
main() {
    print_header "Selenium UI 測試運行工具"
    
    check_python
    check_dependencies
    check_chrome
    check_server
    
    if [ $# -eq 0 ]; then
        # 交互模式
        while true; do
            show_menu
            read -p "選擇: " choice
            
            case $choice in
                1)
                    run_data_tests
                    ;;
                2)
                    run_minimal_e2e
                    ;;
                3)
                    check_server
                    run_all_minimal_e2e
                    ;;
                4)
                    check_server
                    run_full_ui
                    ;;
                5)
                    run_unit_tests
                    ;;
                6)
                    start_server
                    ;;
                0)
                    print_info "退出"
                    exit 0
                    ;;
                *)
                    print_error "無效選擇"
                    ;;
            esac
            
            echo ""
            read -p "按 Enter 鍵繼續..."
        done
    else
        # 命令行模式
        case $1 in
            data)
                run_data_tests
                ;;
            minimal)
                run_minimal_e2e
                ;;
            e2e)
                check_server
                run_all_minimal_e2e
                ;;
            full)
                check_server
                run_full_ui
                ;;
            unit)
                run_unit_tests
                ;;
            server)
                start_server
                ;;
            *)
                print_error "未知命令: $1"
                echo "用法: ./run_tests.sh [data|minimal|e2e|full|unit|server]"
                exit 1
                ;;
        esac
    fi
}

# 執行主函數
main "$@"
