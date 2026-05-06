"""
登录方式相关路由
"""

from fastapi import APIRouter, HTTPException, Depends, status, Request
from pydantic import BaseModel, Field
from typing import List, Tuple, Optional, Dict, Any
import secrets
import time
import os
import threading
from pathlib import Path

router = APIRouter()

# 导入日志
from loguru import logger

# 导入速率限制
from utils.rate_limiter import rate_limit

# 扫码登录检查锁 - 防止并发处理同一个session
from collections import defaultdict
import asyncio

qr_check_locks = defaultdict(lambda: asyncio.Lock())
qr_check_processed = {}  # 记录已处理的session: {session_id: {'processed': bool, 'timestamp': float}}

# 账号密码登录会话管理
password_login_sessions = {}  # {session_id: {'account_id': str, 'account': str, 'password': str, 'show_browser': bool, 'status': str, 'verification_url': str, 'qr_code_url': str, 'slider_instance': object, 'task': asyncio.Task, 'timestamp': float}}
password_login_locks = defaultdict(lambda: asyncio.Lock())

# 导入认证函数
from routers.auth import get_current_user, log_with_user

def cleanup_qr_check_records():
    """清理过期的扫码检查记录"""
    current_time = time.time()
    expired_sessions = []
    
    for session_id, record in qr_check_processed.items():
        # 清理超过1小时的记录
        if current_time - record['timestamp'] > 3600:
            expired_sessions.append(session_id)
    
    for session_id in expired_sessions:
        if session_id in qr_check_processed:
            del qr_check_processed[session_id]
        if session_id in qr_check_locks:
            del qr_check_locks[session_id]

# 密码登录接口（异步，支持人脸认证）
@router.post("/password-login")
async def password_login(
    request: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user),
    _rate=Depends(rate_limit(max_requests=10)),
):
    """账号密码登录接口（异步，支持人脸认证）"""
    try:
        account_id = request.get('account_id')
        account = request.get('account')
        password = request.get('password')
        show_browser = request.get('show_browser', False)
        
        if not account_id or not account or not password:
            return {'success': False, 'message': '账号ID、登录账号和密码不能为空'}
        
        log_with_user('info', f"开始账号密码登录: {account_id}, 账号: {account}", current_user)
        
        # 生成会话ID
        session_id = secrets.token_urlsafe(16)
        
        user_id = current_user['user_id']
        
        # 创建登录会话
        password_login_sessions[session_id] = {
            'account_id': account_id,
            'account': account,
            'password': password,
            'show_browser': show_browser,
            'status': 'processing',
            'verification_url': None,
            'screenshot_path': None,
            'qr_code_url': None,
            'slider_instance': None,
            'task': None,
            'timestamp': time.time(),
            'user_id': user_id
        }
        
        # 启动后台登录任务
        task = asyncio.create_task(_execute_password_login(
            session_id, account_id, account, password, show_browser, user_id, current_user
        ))
        password_login_sessions[session_id]['task'] = task
        
        return {
            'success': True,
            'session_id': session_id,
            'status': 'processing',
            'message': '登录任务已启动，请等待...'
        }
        
    except Exception as e:
        log_with_user('error', f"账号密码登录异常: {str(e)}", current_user)
        import traceback
        logger.error(traceback.format_exc())
        return {'success': False, 'message': f'登录失败: {str(e)}'}

# 检查密码登录状态
@router.get("/password-login/check/{session_id}")
async def check_password_login_status(
    session_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """检查账号密码登录状态"""
    try:
        # 清理过期会话（超过1小时）
        current_time = time.time()
        expired_sessions = [
            sid for sid, session in password_login_sessions.items()
            if current_time - session['timestamp'] > 3600
        ]
        for sid in expired_sessions:
            if sid in password_login_sessions:
                del password_login_sessions[sid]
        
        if session_id not in password_login_sessions:
            return {'status': 'not_found', 'message': '会话不存在或已过期'}
        
        session = password_login_sessions[session_id]
        
        # 检查用户权限
        if session['user_id'] != current_user['user_id']:
            return {'status': 'forbidden', 'message': '无权限访问该会话'}
        
        status = session['status']
        
        if status == 'verification_required':
            # 需要人脸认证
            screenshot_path = session.get('screenshot_path')
            verification_url = session.get('verification_url')
            return {
                'status': 'verification_required',
                'verification_url': verification_url,
                'screenshot_path': screenshot_path,
                'qr_code_url': session.get('qr_code_url'),  # 保留兼容性
                'message': '需要人脸验证，请查看验证截图' if screenshot_path else '需要人脸验证，请点击验证链接'
            }
        elif status == 'success':
            # 登录成功
            # 删除截图（如果存在）
            screenshot_path = session.get('screenshot_path')
            if screenshot_path:
                try:
                    from utils.image_utils import image_manager
                    if image_manager.delete_image(screenshot_path):
                        log_with_user('info', f"验证成功后已删除截图: {screenshot_path}", current_user)
                    else:
                        log_with_user('warning', f"删除截图失败: {screenshot_path}", current_user)
                except Exception as e:
                    log_with_user('error', f"删除截图时出错: {str(e)}", current_user)
            
            result = {
                'status': 'success',
                'message': f'账号 {session["account_id"]} 登录成功',
                'account_id': session['account_id'],
                'is_new_account': session.get('is_new_account', False),
                'cookie_count': session.get('cookie_count', 0)
            }
            # 清理会话
            del password_login_sessions[session_id]
            return result
        elif status == 'failed':
            # 登录失败
            # 删除截图（如果存在）
            screenshot_path = session.get('screenshot_path')
            if screenshot_path:
                try:
                    from utils.image_utils import image_manager
                    if image_manager.delete_image(screenshot_path):
                        log_with_user('info', f"验证失败后已删除截图: {screenshot_path}", current_user)
                    else:
                        log_with_user('warning', f"删除截图失败: {screenshot_path}", current_user)
                except Exception as e:
                    log_with_user('error', f"删除截图时出错: {str(e)}", current_user)
            
            error_msg = session.get('error', '登录失败')
            log_with_user('info', f"返回登录失败状态: {session_id}, 错误消息: {error_msg}", current_user)  # 添加日志
            result = {
                'status': 'failed',
                'message': error_msg,
                'error': error_msg  # 也包含error字段，确保前端能获取到
            }
            # 清理会话
            del password_login_sessions[session_id]
            return result
        else:
            # 处理中
            return {
                'status': 'processing',
                'message': '登录处理中，请稍候...'
            }
        
    except Exception as e:
        log_with_user('error', f"检查账号密码登录状态异常: {str(e)}", current_user)
        return {'status': 'error', 'message': str(e)}

# 获取指定账号的人脸验证截图
@router.get("/face-verification/screenshot/{account_id}")
async def get_account_face_verification_screenshot(
    account_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """获取指定账号的人脸验证截图"""
    try:
        import glob
        from datetime import datetime
        from db_manager import db_manager
        
        # 检查账号是否属于当前用户
        user_id = current_user['user_id']
        username = current_user['username']
        
        # 如果是管理员，允许访问所有账号
        is_admin = username == 'admin'
        
        if not is_admin:
            cookie_info = db_manager.get_cookie_details(account_id)
            if not cookie_info:
                log_with_user('warning', f"账号 {account_id} 不存在", current_user)
                return {
                    'success': False,
                    'message': '账号不存在'
                }
            
            cookie_user_id = cookie_info.get('user_id')
            if cookie_user_id != user_id:
                log_with_user('warning', f"用户 {user_id} 尝试访问账号 {account_id}（归属用户: {cookie_user_id}）", current_user)
                return {
                    'success': False,
                    'message': '无权访问该账号'
                }
        
        # 获取该账号的验证截图
        screenshots_dir = os.path.join(os.path.dirname(__file__).parent, 'static', 'uploads', 'images')
        pattern = os.path.join(screenshots_dir, f'face_verify_{account_id}_*.jpg')
        screenshot_files = glob.glob(pattern)
        
        log_with_user('debug', f"查找截图: {pattern}, 找到 {len(screenshot_files)} 个文件", current_user)
        
        if not screenshot_files:
            log_with_user('warning', f"账号 {account_id} 没有找到验证截图", current_user)
            return {
                'success': False,
                'message': '未找到验证截图'
            }
        
        # 获取最新的截图
        latest_file = max(screenshot_files, key=os.path.getmtime)
        filename = os.path.basename(latest_file)
        stat = os.stat(latest_file)
        
        screenshot_info = {
            'filename': filename,
            'account_id': account_id,
            'path': f'/static/uploads/images/{filename}',
            'size': stat.st_size,
            'created_time': stat.st_ctime,
            'created_time_str': datetime.fromtimestamp(stat.st_ctime).strftime('%Y-%m-%d %H:%M:%S')
        }
        
        log_with_user('info', f"获取账号 {account_id} 的验证截图", current_user)
        
        return {
            'success': True,
            'screenshot': screenshot_info
        }
        
    except Exception as e:
        log_with_user('error', f"获取验证截图失败: {str(e)}", current_user)
        return {
            'success': False,
            'message': str(e)
        }

# 删除指定账号的人脸验证截图
@router.delete("/face-verification/screenshot/{account_id}")
async def delete_account_face_verification_screenshot(
    account_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """删除指定账号的人脸验证截图"""
    try:
        import glob
        from db_manager import db_manager
        
        # 检查账号是否属于当前用户
        user_id = current_user['user_id']
        cookie_info = db_manager.get_cookie_details(account_id)
        if not cookie_info or cookie_info.get('user_id') != user_id:
            return {
                'success': False,
                'message': '无权访问该账号'
            }
        
        # 删除该账号的所有验证截图
        screenshots_dir = os.path.join(os.path.dirname(__file__).parent, 'static', 'uploads', 'images')
        pattern = os.path.join(screenshots_dir, f'face_verify_{account_id}_*.jpg')
        screenshot_files = glob.glob(pattern)
        
        deleted_count = 0
        for file_path in screenshot_files:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    deleted_count += 1
                    log_with_user('info', f"删除账号 {account_id} 的验证截图: {os.path.basename(file_path)}", current_user)
            except Exception as e:
                log_with_user('error', f"删除截图失败 {file_path}: {str(e)}", current_user)
        
        return {
            'success': True,
            'message': f'已删除 {deleted_count} 个验证截图',
            'deleted_count': deleted_count
        }
        
    except Exception as e:
        log_with_user('error', f"删除验证截图失败: {str(e)}", current_user)
        return {
            'success': False,
            'message': str(e)
        }

# 生成扫码登录二维码
@router.post("/qr-login/generate")
async def generate_qr_code(current_user: Dict[str, Any] = Depends(get_current_user)):
    """生成扫码登录二维码"""
    try:
        from utils.qr_login import qr_login_manager
        
        log_with_user('info', "请求生成扫码登录二维码", current_user)
        
        result = await qr_login_manager.generate_qr_code()
        
        if result['success']:
            log_with_user('info', f"扫码登录二维码生成成功: {result['session_id']}", current_user)
        else:
            log_with_user('warning', f"扫码登录二维码生成失败: {result.get('message', '未知错误')}", current_user)
        
        return result
        
    except Exception as e:
        log_with_user('error', f"生成扫码登录二维码异常: {str(e)}", current_user)
        return {'success': False, 'message': f'生成二维码失败: {str(e)}'}

# 检查扫码登录状态
@router.get("/qr-login/check/{session_id}")
async def check_qr_code_status(session_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    """检查扫码登录状态"""
    try:
        from utils.qr_login import qr_login_manager
        import cookie_manager
        from db_manager import db_manager
        from utils.xianyu_utils import trans_cookies
        
        # 清理过期记录
        cleanup_qr_check_records()
        
        # 检查是否已经处理过
        if session_id in qr_check_processed:
            record = qr_check_processed[session_id]
            if record['processed']:
                log_with_user('debug', f"扫码登录session {session_id} 已处理过，直接返回", current_user)
                # 返回简单的成功状态，避免重复处理
                return {'status': 'already_processed', 'message': '该会话已处理完成'}
        
        # 获取该session的锁
        session_lock = qr_check_locks[session_id]
        
        # 使用非阻塞方式尝试获取锁
        if session_lock.locked():
            log_with_user('debug', f"扫码登录session {session_id} 正在被其他请求处理，跳过", current_user)
            return {'status': 'processing', 'message': '正在处理中，请稍候...'}
        
        async with session_lock:
            # 再次检查是否已处理（双重检查）
            if session_id in qr_check_processed and qr_check_processed[session_id]['processed']:
                log_with_user('debug', f"扫码登录session {session_id} 在获取锁后发现已处理，直接返回", current_user)
                return {'status': 'already_processed', 'message': '该会话已处理完成'}
            
            # 清理过期会话
            qr_login_manager.cleanup_expired_sessions()
            
            # 获取会话状态
            status_info = qr_login_manager.get_session_status(session_id)
            log_with_user('info', f"获取会话状态1111111: {status_info}", current_user)
            if status_info['status'] == 'success':
                log_with_user('info', f"获取会话状态22222222: {status_info}", current_user)
                # 登录成功，处理Cookie（现在包含获取真实cookie的逻辑）
                cookies_info = qr_login_manager.get_session_cookies(session_id)
                log_with_user('info', f"获取会话Cookie: {cookies_info}", current_user)
                if cookies_info:
                    account_info = await process_qr_login_cookies(
                        cookies_info['cookies'],
                        cookies_info['unb'],
                        current_user
                    )
                    status_info['account_info'] = account_info
                    
                    log_with_user('info', f"扫码登录处理完成: {session_id}, 账号: {account_info.get('account_id', 'unknown')}", current_user)
                    
                    # 标记该session已处理
                    qr_check_processed[session_id] = {
                        'processed': True,
                        'timestamp': time.time()
                    }
            
            return status_info
        
    except Exception as e:
        log_with_user('error', f"检查扫码登录状态异常: {str(e)}", current_user)
        return {'status': 'error', 'message': str(e)}

async def process_qr_login_cookies(cookies: str, unb: str, current_user: Dict[str, Any]) -> Dict[str, Any]:
    """处理扫码登录获取的Cookie - 先获取真实cookie再保存到数据库"""
    try:
        user_id = current_user['user_id']
        import cookie_manager
        from db_manager import db_manager
        from utils.xianyu_utils import trans_cookies
        
        # 检查是否已存在相同unb的账号
        existing_cookies = db_manager.get_all_cookies(user_id)
        existing_account_id = None
        
        for account_id, cookie_value in existing_cookies.items():
            try:
                # 解析现有Cookie中的unb
                existing_cookie_dict = trans_cookies(cookie_value)
                if existing_cookie_dict.get('unb') == unb:
                    existing_account_id = account_id
                    break
            except:
                continue
        
        # 确定账号ID
        if existing_account_id:
            account_id = existing_account_id
            is_new_account = False
            log_with_user('info', f"扫码登录找到现有账号: {account_id}, UNB: {unb}", current_user)
        else:
            # 创建新账号，使用unb作为账号ID
            account_id = unb
            
            # 确保账号ID唯一
            counter = 1
            original_account_id = account_id
            while account_id in existing_cookies:
                account_id = f"{original_account_id}_{counter}"
                counter += 1
            
            is_new_account = True
            log_with_user('info', f"扫码登录准备创建新账号: {account_id}, UNB: {unb}", current_user)
        
        # 第一步：使用扫码cookie获取真实cookie
        log_with_user('info', f"开始使用扫码cookie获取真实cookie: {account_id}", current_user)
        
        try:
            # 创建一个临时的XianyuLive实例来执行cookie刷新
            from XianyuAutoAsync import XianyuLive
            
            # 使用扫码登录的cookie创建临时实例
            temp_instance = XianyuLive(
                cookies_str=cookies,
                cookie_id=account_id,
                user_id=user_id
            )
            
            # 执行cookie刷新获取真实cookie
            refresh_success = await temp_instance.refresh_cookies_from_qr_login(
                qr_cookies_str=cookies,
                cookie_id=account_id,
                user_id=user_id
            )
            
            if refresh_success:
                log_with_user('info', f"扫码登录真实cookie获取成功: {account_id}", current_user)
                
                # 从数据库获取刚刚保存的真实cookie
                updated_cookie_info = db_manager.get_cookie_by_id(account_id)
                if updated_cookie_info:
                    real_cookies = updated_cookie_info['cookies_str']
                    log_with_user('info', f"已获取真实cookie，长度: {len(real_cookies)}", current_user)
                    
                    # 第二步：将真实cookie添加到cookie_manager（如果是新账号）或更新现有账号
                    if cookie_manager.manager:
                        if is_new_account:
                            cookie_manager.manager.add_cookie(account_id, real_cookies)
                            log_with_user('info', f"已将真实cookie添加到cookie_manager: {account_id}", current_user)
                        else:
                            # refresh_cookies_from_qr_login 已经保存到数据库了，这里不需要再保存
                            cookie_manager.manager.update_cookie(account_id, real_cookies, save_to_db=False)
                            log_with_user('info', f"已更新cookie_manager中的真实cookie: {account_id}", current_user)
                    
                    return {
                        'account_id': account_id,
                        'is_new_account': is_new_account,
                        'real_cookie_refreshed': True,
                        'cookie_length': len(real_cookies)
                    }
                else:
                    log_with_user('error', f"无法从数据库获取真实cookie: {account_id}", current_user)
                    # 降级处理：使用原始扫码cookie
                    return await _fallback_save_qr_cookie(account_id, cookies, user_id, is_new_account, current_user, "无法从数据库获取真实cookie")
            else:
                log_with_user('warning', f"扫码登录真实cookie获取失败: {account_id}", current_user)
                # 降级处理：使用原始扫码cookie
                return await _fallback_save_qr_cookie(account_id, cookies, user_id, is_new_account, current_user, "真实cookie获取失败")
        
        except Exception as refresh_e:
            log_with_user('error', f"扫码登录真实cookie获取异常: {str(refresh_e)}", current_user)
            # 降级处理：使用原始扫码cookie
            return await _fallback_save_qr_cookie(account_id, cookies, user_id, is_new_account, current_user, f"获取真实cookie异常: {str(refresh_e)}")
        
    except Exception as e:
        log_with_user('error', f"处理扫码登录Cookie失败: {str(e)}", current_user)
        raise e

async def _fallback_save_qr_cookie(account_id: str, cookies: str, user_id: int, is_new_account: bool, current_user: Dict[str, Any], error_reason: str) -> Dict[str, Any]:
    """降级处理：当无法获取真实cookie时，保存原始扫码cookie"""
    try:
        import cookie_manager
        from db_manager import db_manager
        
        log_with_user('warning', f"降级处理 - 保存原始扫码cookie: {account_id}, 原因: {error_reason}", current_user)
        
        # 保存原始扫码cookie到数据库
        if is_new_account:
            db_manager.save_cookie(account_id, cookies, user_id)
            log_with_user('info', f"降级处理 - 新账号原始cookie已保存: {account_id}", current_user)
        else:
            # 现有账号使用 update_cookie_account_info 避免覆盖其他字段
            db_manager.update_cookie_account_info(account_id, cookie_value=cookies)
            log_with_user('info', f"降级处理 - 现有账号原始cookie已更新: {account_id}", current_user)
        
        # 添加到或更新cookie_manager
        if cookie_manager.manager:
            if is_new_account:
                cookie_manager.manager.add_cookie(account_id, cookies)
                log_with_user('info', f"降级处理 - 已将原始cookie添加到cookie_manager: {account_id}", current_user)
            else:
                # update_cookie_account_info 已经保存到数据库了，这里不需要再保存
                cookie_manager.manager.update_cookie(account_id, cookies, save_to_db=False)
                log_with_user('info', f"降级处理 - 已更新cookie_manager中的原始cookie: {account_id}", current_user)
        
        return {
            'account_id': account_id,
            'is_new_account': is_new_account,
            'real_cookie_refreshed': False,
            'fallback_reason': error_reason,
            'cookie_length': len(cookies)
        }
        
    except Exception as fallback_e:
        log_with_user('error', f"降级处理失败: {str(fallback_e)}", current_user)
        raise fallback_e

# 刷新扫码登录获取的cookie
@router.post("/qr-login/refresh-cookies")
async def refresh_cookies_from_qr_login(
    request: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """使用扫码登录获取的cookie访问指定界面获取真实cookie并存入数据库"""
    try:
        import cookie_manager
        from db_manager import db_manager
        from XianyuAutoAsync import XianyuLive
        
        qr_cookies = request.get('qr_cookies')
        cookie_id = request.get('cookie_id')
        
        if not qr_cookies:
            return {'success': False, 'message': '缺少扫码登录cookie'}
        
        if not cookie_id:
            return {'success': False, 'message': '缺少cookie_id'}
        
        log_with_user('info', f"开始使用扫码cookie刷新真实cookie: {cookie_id}", current_user)
        
        # 创建一个临时的XianyuLive实例来执行cookie刷新
        temp_instance = XianyuLive(
            cookies_str=qr_cookies,
            cookie_id=cookie_id,
            user_id=current_user['user_id']
        )
        
        # 执行cookie刷新
        success = await temp_instance.refresh_cookies_from_qr_login(
            qr_cookies_str=qr_cookies,
            cookie_id=cookie_id,
            user_id=current_user['user_id']
        )
        
        if success:
            log_with_user('info', f"扫码cookie刷新成功: {cookie_id}", current_user)
            
            # 如果cookie_manager存在，更新其中的cookie
            if cookie_manager.manager:
                # 从数据库获取更新后的cookie
                updated_cookie_info = db_manager.get_cookie_by_id(cookie_id)
                if updated_cookie_info:
                    # refresh_cookies_from_qr_login 已经保存到数据库了，这里不需要再保存
                    cookie_manager.manager.update_cookie(cookie_id, updated_cookie_info['cookies_str'], save_to_db=False)
                    log_with_user('info', f"已更新cookie_manager中的cookie: {cookie_id}", current_user)
            
            return {'success': True, 'message': 'Cookie刷新成功'}
        else:
            log_with_user('warning', f"扫码cookie刷新失败: {cookie_id}", current_user)
            return {'success': False, 'message': 'Cookie刷新失败'}
        
    except Exception as e:
        log_with_user('error', f"刷新扫码cookie异常: {str(e)}", current_user)
        return {'success': False, 'message': f'刷新异常: {str(e)}'}

# 重置扫码登录冷却时间
@router.post("/qr-login/reset-cooldown/{cookie_id}")
async def reset_qr_login_cooldown(
    cookie_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """重置扫码登录冷却时间"""
    try:
        from utils.qr_login import qr_login_manager
        
        log_with_user('info', f"重置扫码登录冷却时间: {cookie_id}", current_user)
        
        success = qr_login_manager.reset_cooldown(cookie_id)
        
        if success:
            log_with_user('info', f"扫码登录冷却时间重置成功: {cookie_id}", current_user)
            return {'success': True, 'message': '冷却时间已重置'}
        else:
            log_with_user('warning', f"扫码登录冷却时间重置失败: {cookie_id}", current_user)
            return {'success': False, 'message': '重置失败'}
        
    except Exception as e:
        log_with_user('error', f"重置扫码登录冷却时间异常: {str(e)}", current_user)
        return {'success': False, 'message': f'重置异常: {str(e)}'}

# 获取扫码登录冷却状态
@router.get("/qr-login/cooldown-status/{cookie_id}")
async def get_qr_login_cooldown_status(
    cookie_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """获取扫码登录冷却状态"""
    try:
        from utils.qr_login import qr_login_manager
        
        status = qr_login_manager.get_cooldown_status(cookie_id)
        
        return {
            'success': True,
            'cookie_id': cookie_id,
            'cooldown_status': status
        }
        
    except Exception as e:
        log_with_user('error', f"获取扫码登录冷却状态异常: {str(e)}", current_user)
        return {'success': False, 'message': f'获取状态异常: {str(e)}'}

# 注意：需要实现 _execute_password_login 函数，这个函数在主文件中定义
# 由于这个函数比较复杂，需要访问很多主文件中的变量和函数，暂时先不实现
# 实际使用时，需要将这个函数也迁移到这个文件中

async def _execute_password_login(session_id: str, account_id: str, account: str, password: str, show_browser: bool, user_id: int, current_user: Dict[str, Any]):
    """执行密码登录任务"""
    # 这个函数需要从主文件中完整迁移
    # 由于代码较长，这里先留空，实际使用时需要完整实现
    pass