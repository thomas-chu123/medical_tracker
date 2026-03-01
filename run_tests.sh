#!/bin/bash

# Medical Tracker Test Runner Wrapper
# 這是 python run_tests.py 的互動式封裝腳本

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

# 檢查環境變量和虛擬環境
check_env() {
    if [ -z "$VIRTUAL_ENV" ]; then
        if [ -d "venv" ]; then
            print_info "自動激活虛擬環境 (venv)..."
            source venv/bin/activate
        else
            print_error "未檢測到虛擬環境，請確保已激活或存在 venv 目錄"
        fi
    fi
}

# 檢查依賴
check_dependencies() {
    print_header "檢查依賴"
    if ! python3 -m pip show pytest &> /dev/null; then
        print_info "Installing dependencies..."
        python3 -m pip install -r requirements.txt -q
    fi
    print_success "All dependencies installed"
}

# 檢查 Chrome (用於 UI 測試)
check_chrome() {
    print_header "檢查 Chrome"
    if [ -x "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ]; then
        export CHROME_BIN="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        CHROME_PATH="$CHROME_BIN"
    elif command -v google-chrome &> /dev/null; then
        CHROME_PATH="google-chrome"
    elif command -v 'google-chrome-stable' &> /dev/null; then
        CHROME_PATH="google-chrome-stable"
    else
        print_info "Chrome 未找到 (非 UI 測試可忽略)"
        return
    fi
    
    CHROME_VERSION=$("$CHROME_PATH" --version)
    print_success "Found: $CHROME_VERSION"
}

# 檢查服務器
check_server() {
    print_header "檢查服務器狀態"
    if curl -s http://localhost:8000/health &> /dev/null; then
        print_success "服務器運行中: http://localhost:8000"
        SERVER_RUNNING=true
    else
        print_error "服務器未運行"
        print_info "請確保在需要時先選擇 [A] 啟動服務器"
        SERVER_RUNNING=false
    fi
}

# 運行特定測試類別
run_category() {
    local category=$1
    local requires_server=$2
    
    print_header "運行 $category 測試"
    
    if [ "$requires_server" = true ] && [ "$SERVER_RUNNING" = false ]; then
        print_error "此測試類別需要運行中的服務器 (E2E 或 Performance)"
        print_info "正在取消測試"
        return 1
    fi
    
    python3 run_tests.py --category "$category"
}

# 運行所有測試
run_all() {
    print_header "運行所有測試 (完整測試套件)"
    
    if [ "$SERVER_RUNNING" = false ]; then
        print_error "此操作包含 E2E 和 Performance 測試，需要運行中的服務器"
        print_info "正在取消測試"
        return 1
    fi
    
    python3 run_tests.py
}

# 啟動開發服務器
start_server() {
    print_header "啟動開發服務器"
    print_info "服務器將在 http://localhost:8000 啟動"
    print_info "按 Ctrl+C 停止服務器"
    python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
}

# 生成並伺服 Allure 報告
serve_report() {
    print_header "開啟 Allure 測試報告"
    python3 run_tests.py --serve-only
}

# 顯示菜單
show_menu() {
    echo ""
    echo -e "${BLUE}======================== Medical Tracker 測試運行工具 ========================${NC}"
    echo -e "${YELLOW}選擇要運行的測試類別:${NC}"
    echo "  1. 單元測試 (Unit Tests)                 [無需服務器]"
    echo "  2. API 測試 (API Tests)                  [無需服務器]"
    echo "  3. E2E UI 測試 (E2E Tests)               [需要服務器]"
    echo "  4. 數據驗證測試 (Data Tests)             [無需服務器]"
    echo "  5. 爬蟲測試 (Scraper Tests)              [無需服務器]"
    echo "  6. 通知系統測試 (Notification Tests)     [無需服務器]"
    echo "  7. 系統集成測試 (System Tests)           [無需服務器]"
    echo "  8. 性能測試 (Performance Tests)          [需要服務器]"
    echo "  9. 運行所有測試 (All Categories)         [需要服務器]"
    echo -e "${YELLOW}其他操作:${NC}"
    echo "  A. 啟動開發服務器 (Start Local Server)"
    echo "  S. 查看測試報告 (Serve Allure Report)"
    echo "  0. 退出 (Exit)"
    echo -e "${BLUE}==============================================================================${NC}"
    echo ""
}

# 主函數
main() {
    print_header "初始化 Medical Tracker 測試運行環境"
    
    check_env
    check_python
    check_dependencies
    check_chrome
    
    # 交互模式
    if [ -t 0 ] || [ -p /dev/stdin ]; then
        while true; do
            check_server
            show_menu
            read -p "選擇 (0-9, A, S): " choice
            
            case $choice in
                1) run_category "unit" false ;;
                2) run_category "api" false ;;
                3) run_category "e2e" true ;;
                4) run_category "data" false ;;
                5) run_category "scraper" false ;;
                6) run_category "notification" false ;;
                7) run_category "system" false ;;
                8) run_category "performance" true ;;
                9) run_all ;;
                A|a) start_server ;;
                S|s) serve_report ;;
                0) print_info "退出"; exit 0 ;;
                *) print_error "無效選擇" ;;
            esac
            
            echo ""
            read -p "按 Enter 鍵返回主選單..."
        done
    else
        # 非交互模式
        case $1 in
            unit) run_category "unit" false ;;
            api) run_category "api" false ;;
            e2e) run_category "e2e" true ;;
            data) run_category "data" false ;;
            scraper) run_category "scraper" false ;;
            notification) run_category "notification" false ;;
            system) run_category "system" false ;;
            performance) run_category "performance" true ;;
            all) run_all ;;
            server) start_server ;;
            report) serve_report ;;
            *)
                echo "用法: ./run_tests.sh [category|all|server|report]"
                echo "Categories: unit, api, e2e, data, scraper, notification, system, performance"
                exit 1
                ;;
        esac
    fi
}

# 執行主函數
main "$@"
