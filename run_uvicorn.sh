#!/bin/bash
source venv/bin/activate

# 配置 IP 和 Port（可按需修改）
HOST=${HOST:-0.0.0.0}      # 0.0.0.0 = 接受所有网络接口，或改为 127.0.0.1/192.168.x.x
PORT=${PORT:-8000}          # 默认 8000，可改為 8001, 5000 等

# 确保不被全局環境變數污染，強制讀取 .env 中的設定
unset ENABLED_HOSPITALS

uvicorn app.main:app --host $HOST --port $PORT --reload
