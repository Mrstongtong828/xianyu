"""
delivery 路由模块
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

@router.get("/delivery-rules")
def get_delivery_rules(current_user: Dict[str, Any] = Depends(get_current_user)):
    """获取发货规则列表"""
    try:
        from db_manager import db_manager
        user_id = current_user['user_id']
        rules = db_manager.get_all_delivery_rules(user_id)
        return rules
    except Exception as e:
        logger.error(f"get_delivery_rules异常: {e}")
        raise HTTPException(status_code=500, detail="内部服务器错误")


@router.post("/delivery-rules")
def create_delivery_rule(rule_data: dict, current_user: Dict[str, Any] = Depends(get_current_user)):
    """创建新发货规则"""
    try:
        from db_manager import db_manager
        user_id = current_user['user_id']
        rule_id = db_manager.create_delivery_rule(
            keyword=rule_data.get('keyword'),
            card_id=rule_data.get('card_id'),
            delivery_count=rule_data.get('delivery_count', 1),
            enabled=rule_data.get('enabled', True),
            description=rule_data.get('description'),
            user_id=user_id
        )
        return {"id": rule_id, "message": "发货规则创建成功"}
    except Exception as e:
        logger.error(f"create_delivery_rule异常: {e}")
        raise HTTPException(status_code=500, detail="内部服务器错误")


@router.get("/delivery-rules/{rule_id}")
def get_delivery_rule(rule_id: int, current_user: Dict[str, Any] = Depends(get_current_user)):
    """获取单个发货规则详情"""
    try:
        from db_manager import db_manager
        user_id = current_user['user_id']
        rule = db_manager.get_delivery_rule_by_id(rule_id, user_id)
        if rule:
            return rule
        else:
            raise HTTPException(status_code=404, detail="发货规则不存在")
    except Exception as e:
        logger.error(f"get_delivery_rule异常: {e}")
        raise HTTPException(status_code=500, detail="内部服务器错误")


@router.put("/delivery-rules/{rule_id}")
def update_delivery_rule(rule_id: int, rule_data: dict, current_user: Dict[str, Any] = Depends(get_current_user)):
    """更新发货规则"""
    try:
        from db_manager import db_manager
        user_id = current_user['user_id']
        success = db_manager.update_delivery_rule(
            rule_id=rule_id,
            keyword=rule_data.get('keyword'),
            card_id=rule_data.get('card_id'),
            delivery_count=rule_data.get('delivery_count', 1),
            enabled=rule_data.get('enabled', True),
            description=rule_data.get('description'),
            user_id=user_id
        )
        if success:
            return {"message": "发货规则更新成功"}
        else:
            raise HTTPException(status_code=404, detail="发货规则不存在")
    except Exception as e:
        logger.error(f"update_delivery_rule异常: {e}")
        raise HTTPException(status_code=500, detail="内部服务器错误")


@router.delete("/delivery-rules/{rule_id}")
def delete_delivery_rule(rule_id: int, current_user: Dict[str, Any] = Depends(get_current_user)):
    """删除发货规则"""
    try:
        from db_manager import db_manager
        user_id = current_user['user_id']
        success = db_manager.delete_delivery_rule(rule_id, user_id)
        if success:
            return {"message": "发货规则删除成功"}
        else:
            raise HTTPException(status_code=404, detail="发货规则不存在")
    except Exception as e:
        logger.error(f"delete_delivery_rule异常: {e}")
        raise HTTPException(status_code=500, detail="内部服务器错误")


# ==================== 备份和恢复 API ====================


@router.get("/api/delivery-retry-queue")
async def get_delivery_retry_queue(
    cookie_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """获取发货重试队列"""
    result = db_manager.get_delivery_retry_queue(cookie_id=cookie_id, page=page, page_size=page_size)
    return {"success": True, **result}


@router.post("/api/delivery-retry-queue/{retry_id}/retry")
async def retry_delivery(retry_id: int, current_user: Dict[str, Any] = Depends(get_current_user)):
    """手动重试发货"""
    db_manager.update_delivery_retry_status(
        retry_id, 'pending', '手动触发重试',
        increment_retry=False, delay_minutes=0
    )
    return {"success": True, "message": "已加入重试"}


@router.delete("/api/delivery-retry-queue/{retry_id}")
async def delete_delivery_retry(retry_id: int, current_user: Dict[str, Any] = Depends(get_current_user)):
    """删除发货重试记录"""
    success = db_manager.delete_delivery_retry(retry_id)
    if success:
        return {"success": True, "message": "已删除"}
    raise HTTPException(status_code=404, detail="记录不存在")


# ==================== 批量卡券导入 ====================
