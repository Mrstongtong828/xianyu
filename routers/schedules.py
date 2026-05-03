"""
schedules 路由模块
"""
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Body, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict, Any, List
import json
import time
import os
import secrets
import hashlib
import asyncio
import io
import pandas as pd
from pathlib import Path

from shared import *
from shared import (
    db_manager, cookie_manager, logger, ai_reply_engine,
    verify_token, verify_admin_token, require_auth, get_current_user,
    get_current_user_optional, require_admin, log_with_user,
    generate_token, match_reply, KEYWORDS_MAPPING,
    SESSION_TOKENS, TOKEN_EXPIRE_TIME, security, qr_check_locks,
    qr_check_processed, password_login_sessions, password_login_locks,
    cleanup_qr_check_records, DEFAULT_ADMIN_PASSWORD, ADMIN_USERNAME,
    CAPTCHA_ROUTER_AVAILABLE,
    # Geetest
    geetest_status_store, set_geetest_status, get_geetest_status,
    # API
    API_SECRET_KEY, verify_api_key,
    # Helpers
    serve_frontend, _execute_password_login, process_qr_login_cookies,
    _fallback_save_qr_cookie, _handle_feishu_command, load_keywords,
    check_order_data_completeness,
    # Utils
    qr_login_manager, trans_cookies, image_manager, rate_limit,
    get_file_log_collector,
)

router = APIRouter()

@router.get("/api/item-schedules")
async def get_item_schedules(
    cookie_id: Optional[str] = None,
    schedule_type: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    schedules = db_manager.get_item_schedules(cookie_id=cookie_id, schedule_type=schedule_type)
    return {"success": True, "data": schedules}


@router.post("/api/item-schedules")
async def add_item_schedule(
    data: ItemScheduleRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    schedule_id = db_manager.add_item_schedule(
        data.cookie_id, data.item_id, data.item_title,
        data.schedule_type, data.schedule_time, data.cron_expression
    )
    if schedule_id:
        return {"success": True, "message": "计划已添加", "id": schedule_id}
    raise HTTPException(status_code=500, detail="添加失败")


@router.put("/api/item-schedules/{schedule_id}")
async def update_item_schedule(
    schedule_id: int,
    data: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    success = db_manager.update_item_schedule(schedule_id, data)
    if success:
        return {"success": True, "message": "已更新"}
    raise HTTPException(status_code=404, detail="记录不存在")


@router.delete("/api/item-schedules/{schedule_id}")
async def delete_item_schedule(
    schedule_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    success = db_manager.delete_item_schedule(schedule_id)
    if success:
        return {"success": True, "message": "已删除"}
    raise HTTPException(status_code=404, detail="记录不存在")



# 登录接口
