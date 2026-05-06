"""
system 路由模块
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
    API_SECRET_KEY, verify_api_key, API_PREFIXES,
    # Helpers
    serve_frontend, _execute_password_login, process_qr_login_cookies,
    _fallback_save_qr_cookie, _handle_feishu_command, load_keywords,
    check_order_data_completeness,
    # Utils
    qr_login_manager, trans_cookies, image_manager, rate_limit,
    get_file_log_collector,
)

router = APIRouter()

@router.get('/system-settings/public')
def get_public_system_settings():
    """获取公开的系统设置（无需认证）"""
    from db_manager import db_manager
    try:
        all_settings = db_manager.get_all_system_settings()
        # 只返回公开的配置项
        public_keys = {"registration_enabled", "show_default_login_info", "login_captcha_enabled"}
        return {k: v for k, v in all_settings.items() if k in public_keys}
    except Exception as e:
        logger.error(f"获取公开系统设置失败: {e}")
        # 返回默认值
        return {
            "registration_enabled": "true",
            "show_default_login_info": "true",
            "login_captcha_enabled": "true"
        }


@router.get('/system-settings')
def get_system_settings(_: None = Depends(require_auth)):
    """获取系统设置（排除敏感信息）"""
    from db_manager import db_manager
    try:
        settings = db_manager.get_all_system_settings()
        # 移除敏感信息
        if 'admin_password_hash' in settings:
            del settings['admin_password_hash']
        return settings
    except Exception as e:
        logger.error(f"get_system_settings异常: {e}")
        raise HTTPException(status_code=500, detail="内部服务器错误")


@router.put('/system-settings/{key}')
def update_system_setting(key: str, setting_data: SystemSettingIn, _: None = Depends(require_auth)):
    """更新系统设置"""
    from db_manager import db_manager
    try:
        # 禁止直接修改密码哈希
        if key == 'admin_password_hash':
            raise HTTPException(status_code=400, detail='请使用密码修改接口')

        success = db_manager.set_system_setting(key, setting_data.value, setting_data.description)
        if success:
            return {'msg': 'system setting updated'}
        else:
            raise HTTPException(status_code=400, detail='更新失败')
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"update_system_setting异常: {e}")
        raise HTTPException(status_code=500, detail="内部服务器错误")


# ------------------------- 注册设置接口 -------------------------


@router.get('/', response_class=HTMLResponse)
async def root():
    return await serve_frontend()


# 登录页面路由 - 重定向到 React 前端


@router.get('/{path:path}', response_class=HTMLResponse)
async def catch_all_route(path: str):
    """
    Catch-all 路由：处理所有未匹配的 GET 请求
    如果是 API 请求，返回 404；否则返回前端 index.html
    """
    # 检查是否是 API 请求
    full_path = f'/{path}'
    for prefix in API_PREFIXES:
        if full_path.startswith(prefix):
            raise HTTPException(status_code=404, detail="Not Found")
    
    # 返回前端页面
    return await serve_frontend()


# 移除自动启动，由Start.py或手动启动
# if __name__ == "__main__":
#     uvicorn.run(app, host="0.0.0.0", port=8080)
