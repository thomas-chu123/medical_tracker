#!/usr/bin/env python3
"""
Notion 讀寫工具 - 供 Copilot CLI 和 Copilot Chat 使用

使用方式：
  python tools/tool_notion.py list_projects [--database_id <id>]
  python tools/tool_notion.py get_project <page_id>
  python tools/tool_notion.py query_projects [--filter <property> <operator> <value>] [--database_id <id>]
  python tools/tool_notion.py create_project [--database_id <id>] --data <json>
  python tools/tool_notion.py update_project <page_id> --data <json>
  python tools/tool_notion.py get_databases
  python tools/tool_notion.py get_database_schema <database_id>

範例：
  # 列出所有項目（默認數據庫）
  python tools/tool_notion.py list_projects
  
  # 查詢特定狀態的項目
  python tools/tool_notion.py query_projects --filter Status is "進行中"
  
  # 獲取單個項目詳情
  python tools/tool_notion.py get_project 123e4567e89b12d3a456426614174000
  
  # 創建新項目
  python tools/tool_notion.py create_project --data '{"Name":"新項目","Status":"計劃中"}'
  
  # 更新項目
  python tools/tool_notion.py update_project 123e4567e89b12d3a456426614174000 --data '{"Status":"進行中"}'
  
  # 列出所有數據庫
  python tools/tool_notion.py get_databases
  
  # 獲取數據庫結構
  python tools/tool_notion.py get_database_schema 123e4567e89b12d3a456426614174000
"""

import json
import sys
import argparse
from typing import Any, Dict, List, Optional, Union
from datetime import datetime
from pathlib import Path

# 添加父目錄到 path 以支持 imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from notion_client import Client
except ImportError:
    print("錯誤: notion-client 未安裝")
    print("請執行: pip install notion-client")
    sys.exit(1)

from app.config import get_settings


def get_notion_client() -> Client:
    """取得 Notion 客戶端"""
    settings = get_settings()
    if not settings.notion_api:
        raise ValueError("NOTION_API 環境變數未設置")
    return Client(auth=settings.notion_api)


def print_result(data: Any, format: str = "json") -> None:
    """列印結果"""
    if format == "json":
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    else:
        print(data)


def _extract_properties(page: Dict[str, Any]) -> Dict[str, Any]:
    """
    從 Notion 頁面提取屬性
    
    Args:
        page: Notion 頁面對象
        
    Returns:
        簡化後的屬性字典
    """
    properties = {}
    if "properties" in page:
        for prop_name, prop_value in page["properties"].items():
            prop_type = prop_value.get("type")
            
            if prop_type == "title":
                titles = prop_value.get("title", [])
                properties[prop_name] = "".join(t.get("plain_text", "") for t in titles) if titles else ""
            
            elif prop_type == "rich_text":
                texts = prop_value.get("rich_text", [])
                properties[prop_name] = "".join(t.get("plain_text", "") for t in texts) if texts else ""
            
            elif prop_type == "checkbox":
                properties[prop_name] = prop_value.get("checkbox", False)
            
            elif prop_type == "select":
                select = prop_value.get("select")
                properties[prop_name] = select.get("name", "") if select else None
            
            elif prop_type == "multi_select":
                multi = prop_value.get("multi_select", [])
                properties[prop_name] = [m.get("name", "") for m in multi] if multi else []
            
            elif prop_type == "date":
                date = prop_value.get("date")
                properties[prop_name] = date.get("start", "") if date else None
            
            elif prop_type == "number":
                properties[prop_name] = prop_value.get("number")
            
            elif prop_type == "url":
                properties[prop_name] = prop_value.get("url", "")
            
            elif prop_type == "email":
                properties[prop_name] = prop_value.get("email", "")
            
            elif prop_type == "relation":
                relations = prop_value.get("relation", [])
                properties[prop_name] = [r.get("id", "") for r in relations] if relations else []
            
            else:
                # 其他類型默認提取值
                properties[prop_name] = prop_value.get(prop_type)
    
    return properties


def get_databases() -> Dict[str, Any]:
    """
    獲取所有可用的數據庫
    
    Returns:
        包含數據庫列表的字典
    """
    try:
        client = get_notion_client()
        response = client.search(filter={"value": "data_source", "property": "object"})
        
        databases = []
        for result in response.get("results", []):
            db_info = {
                "id": result.get("id"),
                "title": result.get("title", ""),
                "icon": result.get("icon"),
                "created_time": result.get("created_time"),
            }
            
            # 提取標題（支援 database 與 data_source object 類型）
            if "title" in result:
                titles = result["title"]
                if titles and isinstance(titles, list):
                    db_info["title"] = "".join(t.get("plain_text", "") for t in titles)
            
            databases.append(db_info)
        
        return {
            "status": "success",
            "count": len(databases),
            "data": databases
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


def get_database_schema(database_id: str) -> Dict[str, Any]:
    """
    獲取數據庫的結構信息
    
    Args:
        database_id: 數據庫 ID
        
    Returns:
        包含數據庫屬性/列信息的字典
    """
    try:
        client = get_notion_client()
        database = client.databases.retrieve(database_id)
        
        schema = {}
        for prop_name, prop_config in database.get("properties", {}).items():
            prop_type = prop_config.get("type")
            schema[prop_name] = {
                "type": prop_type,
                "id": prop_config.get("id"),
            }
            
            # 對於 select/multi_select 類型，列出可用選項
            if prop_type == "select":
                options = prop_config.get("select", {}).get("options", [])
                schema[prop_name]["options"] = [o.get("name") for o in options]
            
            elif prop_type == "multi_select":
                options = prop_config.get("multi_select", {}).get("options", [])
                schema[prop_name]["options"] = [o.get("name") for o in options]
        
        return {
            "status": "success",
            "title": "".join(t.get("plain_text", "") for t in database.get("title", [])),
            "properties": schema
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


def list_projects(database_id: Optional[str] = None) -> Dict[str, Any]:
    """
    列出數據庫中的所有項目
    
    Args:
        database_id: 數據庫 ID（如果為 None，將使用配置中的默認數據庫）
        
    Returns:
        包含項目列表的字典
    """
    try:
        client = get_notion_client()
        
        # 如果沒有指定數據庫，嘗試獲取第一個可用的數據庫
        if not database_id:
            databases = get_databases()
            if databases["status"] == "success" and databases["data"]:
                database_id = databases["data"][0]["id"]
            else:
                return {
                    "status": "error",
                    "message": "未找到可用的數據庫。請指定 --database_id 參數"
                }
        
        response = client.data_sources.query(database_id)
        
        projects = []
        for page in response.get("results", []):
            project = {
                "id": page.get("id"),
                "created_time": page.get("created_time"),
                "last_edited_time": page.get("last_edited_time"),
                "properties": _extract_properties(page)
            }
            projects.append(project)
        
        return {
            "status": "success",
            "count": len(projects),
            "database_id": database_id,
            "data": projects
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


def get_project(page_id: str) -> Dict[str, Any]:
    """
    獲取單個項目的詳細信息
    
    Args:
        page_id: 頁面 ID
        
    Returns:
        包含項目詳情的字典
    """
    try:
        client = get_notion_client()
        page = client.pages.retrieve(page_id)
        
        return {
            "status": "success",
            "id": page.get("id"),
            "created_time": page.get("created_time"),
            "last_edited_time": page.get("last_edited_time"),
            "properties": _extract_properties(page),
            "url": page.get("url")
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


def query_projects(
    filters: Optional[List[tuple]] = None,
    database_id: Optional[str] = None,
    sort_property: Optional[str] = None,
    sort_direction: str = "ascending"
) -> Dict[str, Any]:
    """
    查詢數據庫中的項目，可帶篩選條件
    
    Args:
        filters: [(property, operator, value), ...] 篩選條件列表
                 operator 可為: is, is_not, contains, does_not_contain, starts_with, ends_with 等
        database_id: 數據庫 ID
        sort_property: 排序屬性名稱
        sort_direction: 排序方向 (ascending 或 descending)
        
    Returns:
        包含查詢結果的字典
    """
    try:
        client = get_notion_client()
        
        # 如果沒有指定數據庫，嘗試獲取第一個可用的數據庫
        if not database_id:
            databases = get_databases()
            if databases["status"] == "success" and databases["data"]:
                database_id = databases["data"][0]["id"]
            else:
                return {
                    "status": "error",
                    "message": "未找到可用的數據庫。請指定 --database_id 參數"
                }
        
        # 構建查詢參數
        query_params = {"database_id": database_id}
        
        # 構建篩選條件
        if filters:
            filter_list = []
            for prop_name, operator, value in filters:
                # 簡單的篩選條件構建
                condition = {
                    "property": prop_name,
                    operator: {
                        "equals" if operator == "is" else "does_not_equal" if operator == "is_not" 
                        else operator: value
                    }
                }
                filter_list.append(condition)
            
            if len(filter_list) == 1:
                query_params["filter"] = filter_list[0]
            else:
                query_params["filter"] = {
                    "and": filter_list
                }
        
        # 添加排序
        if sort_property:
            query_params["sorts"] = [
                {
                    "property": sort_property,
                    "direction": sort_direction
                }
            ]
        
        response = client.data_sources.query(**query_params)
        
        projects = []
        for page in response.get("results", []):
            project = {
                "id": page.get("id"),
                "created_time": page.get("created_time"),
                "last_edited_time": page.get("last_edited_time"),
                "properties": _extract_properties(page)
            }
            projects.append(project)
        
        return {
            "status": "success",
            "count": len(projects),
            "database_id": database_id,
            "data": projects
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


def create_project(data: Dict[str, Any], database_id: Optional[str] = None) -> Dict[str, Any]:
    """
    創建新項目（頁面）
    
    Args:
        data: 項目屬性字典
        database_id: 數據庫 ID
        
    Returns:
        包含新創建項目信息的字典
    """
    try:
        client = get_notion_client()
        
        # 如果沒有指定數據庫，嘗試獲取第一個可用的數據庫
        if not database_id:
            databases = get_databases()
            if databases["status"] == "success" and databases["data"]:
                database_id = databases["data"][0]["id"]
            else:
                return {
                    "status": "error",
                    "message": "未找到可用的數據庫。請指定 --database_id 參數"
                }
        
        # 構建 Notion 屬性格式
        properties = {}
        for key, value in data.items():
            if isinstance(value, str):
                properties[key] = {
                    "title": [{"text": {"content": value}}] if key.lower() in ["name", "title"] else 
                             [{"text": {"content": value}}]
                }
            elif isinstance(value, bool):
                properties[key] = {"checkbox": value}
            elif isinstance(value, (int, float)):
                properties[key] = {"number": value}
            elif isinstance(value, list):
                properties[key] = {
                    "multi_select": [{"name": str(v)} for v in value]
                }
            else:
                properties[key] = {"rich_text": [{"text": {"content": str(value)}}]}
        
        # 簡化：使用更靈活的屬性設置
        properties = {}
        for key, value in data.items():
            properties[key] = {"title": [{"text": {"content": str(value)}}]}
        
        page = client.pages.create(
            parent={"database_id": database_id},
            properties=properties
        )
        
        return {
            "status": "success",
            "message": "成功創建項目",
            "id": page.get("id"),
            "url": page.get("url"),
            "properties": _extract_properties(page)
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


def update_project(page_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    更新項目
    
    Args:
        page_id: 頁面 ID
        data: 要更新的屬性字典
        
    Returns:
        包含更新結果的字典
    """
    try:
        client = get_notion_client()
        
        # 構建 Notion 屬性格式
        properties = {}
        for key, value in data.items():
            properties[key] = {"title": [{"text": {"content": str(value)}}]}
        
        page = client.pages.update(
            page_id=page_id,
            properties=properties
        )
        
        return {
            "status": "success",
            "message": "成功更新項目",
            "id": page.get("id"),
            "properties": _extract_properties(page)
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


def main():
    """CLI 主入口"""
    parser = argparse.ArgumentParser(description="Notion 讀寫工具")
    subparsers = parser.add_subparsers(dest="command", help="操作命令")
    
    # list_projects 命令
    list_parser = subparsers.add_parser("list_projects", help="列出所有項目")
    list_parser.add_argument("--database_id", help="數據庫 ID")
    
    # get_project 命令
    get_parser = subparsers.add_parser("get_project", help="獲取項目詳情")
    get_parser.add_argument("page_id", help="頁面 ID")
    
    # query_projects 命令
    query_parser = subparsers.add_parser("query_projects", help="查詢項目")
    query_parser.add_argument("--filter", nargs=3, action="append", metavar=("PROPERTY", "OPERATOR", "VALUE"),
                            help="篩選條件 (可重複指定)")
    query_parser.add_argument("--database_id", help="數據庫 ID")
    query_parser.add_argument("--sort_property", help="排序屬性")
    query_parser.add_argument("--sort_direction", choices=["ascending", "descending"], 
                            default="ascending", help="排序方向")
    
    # create_project 命令
    create_parser = subparsers.add_parser("create_project", help="創建項目")
    create_parser.add_argument("--data", required=True, help="JSON 格式的項目屬性")
    create_parser.add_argument("--database_id", help="數據庫 ID")
    
    # update_project 命令
    update_parser = subparsers.add_parser("update_project", help="更新項目")
    update_parser.add_argument("page_id", help="頁面 ID")
    update_parser.add_argument("--data", required=True, help="JSON 格式的項目屬性")
    
    # get_databases 命令
    subparsers.add_parser("get_databases", help="列出所有數據庫")
    
    # get_database_schema 命令
    schema_parser = subparsers.add_parser("get_database_schema", help="獲取數據庫結構")
    schema_parser.add_argument("database_id", help="數據庫 ID")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # 執行命令
    result = None
    
    if args.command == "list_projects":
        result = list_projects(database_id=args.database_id)
    
    elif args.command == "get_project":
        result = get_project(args.page_id)
    
    elif args.command == "query_projects":
        filters = None
        if args.filter:
            filters = [(f[0], f[1], f[2]) for f in args.filter]
        result = query_projects(
            filters=filters,
            database_id=args.database_id,
            sort_property=args.sort_property,
            sort_direction=args.sort_direction
        )
    
    elif args.command == "create_project":
        data = json.loads(args.data)
        result = create_project(data, database_id=args.database_id)
    
    elif args.command == "update_project":
        data = json.loads(args.data)
        result = update_project(args.page_id, data)
    
    elif args.command == "get_databases":
        result = get_databases()
    
    elif args.command == "get_database_schema":
        result = get_database_schema(args.database_id)
    
    # 列印結果
    if result:
        print_result(result)
    
    # 返回適當的退出碼
    if result and result.get("status") == "error":
        sys.exit(1)


if __name__ == "__main__":
    main()
