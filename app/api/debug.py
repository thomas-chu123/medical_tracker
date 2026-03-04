"""
Debug logging API for frontend operations.
"""

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from app.auth import get_current_user
from app.config import get_settings

router = APIRouter(prefix="/api/debug", tags=["Debug"])
DEBUG_LOG_FILE = Path(__file__).parent.parent.parent / "debug.log"


class StepperLogEntry(BaseModel):
    timestamp: str
    action: str
    stepper: dict[str, Any]
    metadata: dict[str, Any] = {}


class StepperLogsRequest(BaseModel):
    logs: list[StepperLogEntry]


@router.get("/config")
async def get_debug_config():
    """Get debug configuration from backend."""
    settings = get_settings()
    return {
        "debug_enabled": bool(settings.debug)
    }


@router.post("/stepper-logs", status_code=201)
async def log_stepper_debug(request: StepperLogsRequest):
    """Receive and log stepper operation debug logs from frontend.
    
    Only logs if DEBUG=1 is set in environment.
    """
    settings = get_settings()
    if not settings.debug:
        # Debug is disabled, silently ignore
        return {
            "status": "ignored",
            "reason": "Debug mode is disabled",
            "logged_count": 0
        }
    
    try:
        # Ensure debug.log file exists
        DEBUG_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        # Append logs to debug.log
        with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
            for entry in request.logs:
                log_line = json.dumps({
                    "timestamp": entry.timestamp,
                    "action": entry.action,
                    "stepper": entry.stepper,
                    "metadata": entry.metadata,
                }, ensure_ascii=False)
                f.write(log_line + "\n")
        
        return {
            "status": "success",
            "logged_count": len(request.logs),
            "log_file": str(DEBUG_LOG_FILE)
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "logged_count": 0
        }


@router.get("/stepper-logs")
async def get_stepper_debug_logs(current_user: dict = Depends(get_current_user)):
    """Retrieve stepper debug logs from debug.log file."""
    try:
        if not DEBUG_LOG_FILE.exists():
            return {"logs": [], "message": "No debug logs yet"}
        
        logs = []
        with open(DEBUG_LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    log_entry = json.loads(line.strip())
                    logs.append(log_entry)
                except json.JSONDecodeError:
                    pass
        
        # Return latest 100 logs
        return {
            "logs": logs[-100:] if len(logs) > 100 else logs,
            "total_count": len(logs),
            "file": str(DEBUG_LOG_FILE)
        }
    except Exception as e:
        return {
            "error": str(e),
            "logs": []
        }


@router.delete("/stepper-logs")
async def clear_stepper_debug_logs(current_user: dict = Depends(get_current_user)):
    """Clear stepper debug logs."""
    try:
        if DEBUG_LOG_FILE.exists():
            DEBUG_LOG_FILE.unlink()
        return {"status": "success", "message": "Debug logs cleared"}
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }
