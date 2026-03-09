#!/usr/bin/env python3
"""
Supabase 讀寫工具 - 供 Copilot CLI 和 Copilot Chat 使用

使用方式：
  python tools/tool_supabase.py select <table> [--filter <key> <op> <value>]
  python tools/tool_supabase.py insert <table> --data <json>
  python tools/tool_supabase.py update <table> --filter <key> <op> <value> --data <json>
  python tools/tool_supabase.py upsert <table> --data <json> [--on_conflict <col1,col2>]
  python tools/tool_supabase.py delete <table> --filter <key> <op> <value>
  python tools/tool_supabase.py get_user <user_id>
  python tools/tool_supabase.py get_subscriptions <user_id>
  python tools/tool_supabase.py list_hospitals
  python tools/tool_supabase.py list_departments [--hospital_id <id>]
  python tools/tool_supabase.py list_doctors [--department_id <id>]

範例：
  # 查詢所有醫院
  python tools/tool_supabase.py list_hospitals
  
  # 查詢特定科室的醫生
  python tools/tool_supabase.py list_doctors --department_id DEPT001
  
  # 查詢使用者訂閱
  python tools/tool_supabase.py get_subscriptions user123
  
  # 插入新用戶
  python tools/tool_supabase.py insert users_local --data '{"email":"test@example.com","hashed_password":"...","is_admin":false}'
  
  # 查询特定條件的數據
  python tools/tool_supabase.py select appointment_snapshots --filter doctor_id eq DOC001 --filter session_date gte 2026-03-01
"""

import json
import sys
import argparse
from typing import Any, Dict, List, Optional
from datetime import datetime

# 配置
import os
from pathlib import Path

# 添加父目錄到 path 以支持 imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import get_settings
from app.database import get_supabase
from app.core.timezone import now_tw, today_tw_str, now_utc_str


def print_result(data: Any, format: str = "json") -> None:
    """列印結果"""
    if format == "json":
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    else:
        print(data)


def select_table(
    table: str,
    filters: Optional[List[tuple]] = None,
    limit: int = 1000,
) -> Dict[str, Any]:
    """
    查詢資料表
    
    Args:
        table: 資料表名稱
        filters: [(key, operator, value), ...] 條件列表，operator 為 eq, gte, lte, gt, lt, like, in 等
        limit: 返回的最大行數
    """
    try:
        supabase = get_supabase()
        query = supabase.table(table).select("*")
        
        # 應用篩選條件
        if filters:
            for key, op, value in filters:
                if op == "eq":
                    query = query.eq(key, value)
                elif op == "gte":
                    query = query.gte(key, value)
                elif op == "lte":
                    query = query.lte(key, value)
                elif op == "gt":
                    query = query.gt(key, value)
                elif op == "lt":
                    query = query.lt(key, value)
                elif op == "like":
                    query = query.like(key, value)
                elif op == "in":
                    query = query.in_(key, value.split(","))
                elif op == "neq":
                    query = query.neq(key, value)
                else:
                    raise ValueError(f"不支持的操作符: {op}")
        
        query = query.limit(limit)
        result = query.execute()
        
        return {
            "status": "success",
            "count": len(result.data),
            "data": result.data
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


def insert_row(table: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    插入一筆資料
    
    Args:
        table: 資料表名稱
        data: 要插入的資料
    """
    try:
        supabase = get_supabase()
        result = supabase.table(table).insert(data).execute()
        return {
            "status": "success",
            "message": "成功插入",
            "data": result.data
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


def update_row(
    table: str,
    filters: List[tuple],
    data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    更新資料
    
    Args:
        table: 資料表名稱
        filters: [(key, operator, value), ...] 條件列表
        data: 要更新的資料
    """
    try:
        supabase = get_supabase()
        # 應用篩選條件
        if filters:
            for key, op, value in filters:
                if op == "eq":
                    query = query.eq(key, value)
                elif op == "gte":
                    query = query.gte(key, value)
                elif op == "lte":
                    query = query.lte(key, value)
                elif op == "gt":
                    query = query.gt(key, value)
                elif op == "lt":
                    query = query.lt(key, value)
                elif op == "like":
                    query = query.like(key, value)
                elif op == "neq":
                    query = query.neq(key, value)
        
        result = query.update(data).execute()
        
        return {
            "status": "success",
            "message": f"成功更新 {len(result.data)} 筆資料",
            "data": result.data
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


def upsert_row(
    table: str,
    data: Dict[str, Any],
    on_conflict: Optional[str] = None
) -> Dict[str, Any]:
    """
    Upsert 資料（插入或更新）
    
    Args:
        table: 資料表名稱
        data: 要 upsert 的資料
        on_conflict: 衝突時的依據欄位（逗號分隔），例如 "doctor_id,session_date,session_type"
    """
    try:
        supabase = get_supabase()
        opts = {}
        if on_conflict:
            opts["on_conflict"] = on_conflict
        
        result = supabase.table(table).upsert(data, **opts).execute()
        
        return {
            "status": "success",
            "message": "成功 upsert",
            "data": result.data
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


def delete_row(table: str, filters: List[tuple]) -> Dict[str, Any]:
    """
    刪除資料
    
    Args:
        table: 資料表名稱
        filters: [(key, operator, value), ...] 條件列表
    """
    try:
        supabase = get_supabase()
        # 應用篩選條件
        if filters:
            for key, op, value in filters:
                if op == "eq":
                    query = query.eq(key, value)
                elif op == "gte":
                    query = query.gte(key, value)
                elif op == "lte":
                    query = query.lte(key, value)
                elif op == "gt":
                    query = query.gt(key, value)
                elif op == "lt":
                    query = query.lt(key, value)
                elif op == "like":
                    query = query.like(key, value)
                elif op == "neq":
                    query = query.neq(key, value)
        
        result = query.delete().execute()
        
        return {
            "status": "success",
            "message": f"成功刪除 {len(result.data)} 筆資料",
            "data": result.data
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


# ============ Convenience Methods ============

def get_user(user_id: str) -> Dict[str, Any]:
    """獲取使用者資訊"""
    return select_table("users_local", filters=[("id", "eq", user_id)])


def get_subscriptions(user_id: str) -> Dict[str, Any]:
    """獲取使用者的所有訂閱"""
    return select_table("tracking_subscriptions", filters=[("user_id", "eq", user_id)])


def list_hospitals() -> Dict[str, Any]:
    """列出所有醫院"""
    return select_table("hospitals", limit=1000)


def list_departments(hospital_id: Optional[str] = None) -> Dict[str, Any]:
    """列出科室"""
    filters = None
    if hospital_id:
        filters = [("hospital_id", "eq", hospital_id)]
    return select_table("departments", filters=filters, limit=1000)


def list_doctors(department_id: Optional[str] = None) -> Dict[str, Any]:
    """列出醫生"""
    filters = None
    if department_id:
        filters = [("department_id", "eq", department_id)]
    return select_table("doctors", filters=filters, limit=1000)


def get_latest_snapshots(doctor_id: str, limit: int = 10) -> Dict[str, Any]:
    """獲取醫生的最新快照記錄"""
    try:
        supabase = get_supabase()
        result = (
            supabase.table("appointment_snapshots")
            .select("*")
            .eq("doctor_id", doctor_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return {
            "status": "success",
            "count": len(result.data),
            "data": result.data
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


def main():
    """CLI 主入口"""
    parser = argparse.ArgumentParser(description="Supabase 讀寫工具")
    subparsers = parser.add_subparsers(dest="command", help="操作命令")
    
    # select 命令
    select_parser = subparsers.add_parser("select", help="查詢資料")
    select_parser.add_argument("table", help="資料表名稱")
    select_parser.add_argument("--filter", nargs=3, action="append", metavar=("KEY", "OP", "VALUE"),
                             help="篩選條件 (可重複指定)")
    select_parser.add_argument("--limit", type=int, default=1000, help="返回的最大行數")
    
    # insert 命令
    insert_parser = subparsers.add_parser("insert", help="插入資料")
    insert_parser.add_argument("table", help="資料表名稱")
    insert_parser.add_argument("--data", required=True, help="JSON 格式的資料")
    
    # update 命令
    update_parser = subparsers.add_parser("update", help="更新資料")
    update_parser.add_argument("table", help="資料表名稱")
    update_parser.add_argument("--filter", nargs=3, action="append", metavar=("KEY", "OP", "VALUE"),
                             required=True, help="篩選條件")
    update_parser.add_argument("--data", required=True, help="JSON 格式的資料")
    
    # upsert 命令
    upsert_parser = subparsers.add_parser("upsert", help="插入或更新資料")
    upsert_parser.add_argument("table", help="資料表名稱")
    upsert_parser.add_argument("--data", required=True, help="JSON 格式的資料")
    upsert_parser.add_argument("--on_conflict", help="衝突欄位 (逗號分隔)")
    
    # delete 命令
    delete_parser = subparsers.add_parser("delete", help="刪除資料")
    delete_parser.add_argument("table", help="資料表名稱")
    delete_parser.add_argument("--filter", nargs=3, action="append", metavar=("KEY", "OP", "VALUE"),
                             required=True, help="篩選條件")
    
    # Convenience 命令
    subparsers.add_parser("list_hospitals", help="列出所有醫院")
    
    list_depts = subparsers.add_parser("list_departments", help="列出科室")
    list_depts.add_argument("--hospital_id", help="醫院 ID")
    
    list_docs = subparsers.add_parser("list_doctors", help="列出醫生")
    list_docs.add_argument("--department_id", help="科室 ID")
    
    get_user_parser = subparsers.add_parser("get_user", help="獲取使用者資訊")
    get_user_parser.add_argument("user_id", help="使用者 ID")
    
    get_subs = subparsers.add_parser("get_subscriptions", help="獲取使用者訂閱")
    get_subs.add_argument("user_id", help="使用者 ID")
    
    get_snapshots = subparsers.add_parser("get_latest_snapshots", help="獲取醫生的最新快照")
    get_snapshots.add_argument("doctor_id", help="醫生 ID")
    get_snapshots.add_argument("--limit", type=int, default=10, help="行數限制")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # 執行命令
    result = None
    
    if args.command == "select":
        filters = None
        if args.filter:
            filters = [(f[0], f[1], f[2]) for f in args.filter]
        result = select_table(args.table, filters=filters, limit=args.limit)
    
    elif args.command == "insert":
        data = json.loads(args.data)
        result = insert_row(args.table, data)
    
    elif args.command == "update":
        filters = [(f[0], f[1], f[2]) for f in args.filter]
        data = json.loads(args.data)
        result = update_row(args.table, filters, data)
    
    elif args.command == "upsert":
        data = json.loads(args.data)
        result = upsert_row(args.table, data, on_conflict=args.on_conflict)
    
    elif args.command == "delete":
        filters = [(f[0], f[1], f[2]) for f in args.filter]
        result = delete_row(args.table, filters)
    
    elif args.command == "list_hospitals":
        result = list_hospitals()
    
    elif args.command == "list_departments":
        result = list_departments(hospital_id=args.hospital_id)
    
    elif args.command == "list_doctors":
        result = list_doctors(department_id=args.department_id)
    
    elif args.command == "get_user":
        result = get_user(args.user_id)
    
    elif args.command == "get_subscriptions":
        result = get_subscriptions(args.user_id)
    
    elif args.command == "get_latest_snapshots":
        result = get_latest_snapshots(args.doctor_id, limit=args.limit)
    
    # 列印結果
    if result:
        print_result(result)
    
    # 返回適當的退出碼
    if result and result.get("status") == "error":
        sys.exit(1)


if __name__ == "__main__":
    main()
