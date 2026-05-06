"""
orders 路由模块
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

@router.get('/api/orders')
def get_user_orders(
    current_user: Dict[str, Any] = Depends(get_current_user),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    cookie_id: Optional[str] = Query(None, description="筛选Cookie ID"),
    status: Optional[str] = Query(None, description="筛选状态")
):
    """获取当前用户的订单信息（支持分页）"""
    try:
        from db_manager import db_manager

        user_id = current_user['user_id']
        log_with_user('info', f"查询用户订单信息 (page={page}, page_size={page_size})", current_user)

        # 获取用户的所有Cookie
        user_cookies = db_manager.get_all_cookies(user_id)

        # 如果指定了cookie_id筛选
        if cookie_id and cookie_id in user_cookies:
            user_cookies = {cookie_id: user_cookies[cookie_id]}

        # 获取所有订单数据
        all_orders = []
        # 先获取所有商品的 item_id 到 item_title 的映射
        item_titles = {}
        with db_manager.lock:
            cursor = db_manager.conn.cursor()
            cursor.execute('SELECT item_id, item_title FROM item_info')
            for row in cursor.fetchall():
                item_titles[row[0]] = row[1]

        for cid in user_cookies.keys():
            orders = db_manager.get_orders_by_cookie(cid, limit=1000)
            for order in orders:
                order['cookie_id'] = cid
                # 添加 item_title 字段
                order['item_title'] = item_titles.get(order.get('item_id'), '')
                # 状态筛选
                if status and order.get('status') != status:
                    continue
                all_orders.append(order)

        # 按创建时间倒序排列
        all_orders.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        # 分页处理
        total = len(all_orders)
        total_pages = (total + page_size - 1) // page_size
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_orders = all_orders[start_idx:end_idx]

        log_with_user('info', f"用户订单查询成功，共 {total} 条记录，第 {page}/{total_pages} 页", current_user)
        return {
            "success": True,
            "data": paginated_orders,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages
        }

    except Exception as e:
        log_with_user('error', f"查询用户订单失败: {str(e)}", current_user)
        raise HTTPException(status_code=500, detail="查询订单失败")


@router.get('/api/orders/{order_id}')
def get_order_detail(order_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    """获取订单详情"""
    try:
        from db_manager import db_manager

        user_id = current_user['user_id']
        log_with_user('info', f"查询订单详情: {order_id}", current_user)

        # 获取用户的所有Cookie
        user_cookies = db_manager.get_all_cookies(user_id)

        # 在用户的订单中查找
        for cookie_id in user_cookies.keys():
            order = db_manager.get_order_by_id(order_id)
            if order and order.get('cookie_id') == cookie_id:
                log_with_user('info', f"订单详情查询成功: {order_id}", current_user)
                return {"success": True, "data": order}

        log_with_user('warning', f"订单不存在或无权访问: {order_id}", current_user)
        raise HTTPException(status_code=404, detail="订单不存在或无权访问")

    except HTTPException:
        raise
    except Exception as e:
        log_with_user('error', f"查询订单详情失败: {str(e)}", current_user)
        raise HTTPException(status_code=500, detail="查询订单详情失败")


@router.delete('/api/orders/{order_id}')
def delete_order(order_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    """删除订单"""
    try:
        from db_manager import db_manager

        user_id = current_user['user_id']
        log_with_user('info', f"删除订单: {order_id}", current_user)

        # 获取用户的所有Cookie
        user_cookies = db_manager.get_all_cookies(user_id)

        # 验证订单属于当前用户
        order = db_manager.get_order_by_id(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="订单不存在")

        if order.get('cookie_id') not in user_cookies:
            raise HTTPException(status_code=403, detail="无权删除此订单")

        # 删除订单
        success = db_manager.delete_order(order_id)
        if success:
            log_with_user('info', f"订单删除成功: {order_id}", current_user)
            return {"success": True, "message": "删除成功"}
        else:
            raise HTTPException(status_code=500, detail="删除失败")

    except HTTPException:
        raise
    except Exception as e:
        log_with_user('error', f"删除订单失败: {str(e)}", current_user)
        raise HTTPException(status_code=500, detail="删除订单失败")


@router.post('/api/orders/{order_id}/refresh')
async def refresh_single_order(
    order_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """刷新单条订单状态"""
    try:
        from db_manager import db_manager
        from utils.order_fetcher_optimized import process_orders_batch

        user_id = current_user['user_id']
        log_with_user('info', f"刷新单条订单: {order_id}", current_user)

        # 获取用户的所有Cookie
        user_cookies = db_manager.get_all_cookies(user_id)

        # 验证订单存在且属于当前用户
        order = db_manager.get_order_by_id(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="订单不存在")

        cookie_id = order.get('cookie_id')
        if not cookie_id or cookie_id not in user_cookies:
            raise HTTPException(status_code=403, detail="无权刷新此订单")

        cookies_str = user_cookies[cookie_id]
        if not cookies_str:
            raise HTTPException(status_code=400, detail="Cookie无效")

        # 调用批量刷新函数处理单条订单
        batch_results = await process_orders_batch(
            order_ids=[order_id],
            cookie_id=cookie_id,
            cookie_string=cookies_str,
            max_concurrent=1,
            timeout=30,
            headless=True,
            use_pool=True,
            force_refresh=True
        )

        if not batch_results or len(batch_results) == 0:
            raise HTTPException(status_code=500, detail="刷新失败")

        result = batch_results[0]
        if result.get('error'):
            raise HTTPException(status_code=500, detail=f"刷新失败: {result.get('error')}")

        # 状态码映射
        order_status = result.get('order_status', 'unknown')
        if order_status and str(order_status).isdigit():
            status_mapping = {
                '1': 'processing',
                '2': 'pending_ship',
                '3': 'shipped',
                '4': 'completed',
                '5': 'refunding',
                '6': 'cancelled',
                '7': 'refunding',
                '8': 'cancelled',
                '9': 'refunding',
                '10': 'cancelled',
                '11': 'completed',
                '12': 'cancelled',
            }
            order_status = status_mapping.get(str(order_status), order_status)

        # 更新数据库
        db_manager.insert_or_update_order(
            order_id=order_id,
            item_id=result.get('item_id') or None,
            buyer_id=result.get('buyer_id') or None,
            spec_name=result.get('spec_name') or None,
            spec_value=result.get('spec_value') or None,
            quantity=result.get('quantity') or None,
            amount=result.get('amount') or None,
            order_status=order_status,
            cookie_id=cookie_id,
            receiver_name=result.get('receiver_name') or None,
            receiver_phone=result.get('receiver_phone') or None,
            receiver_address=result.get('receiver_address') or None,
        )

        log_with_user('info', f"订单刷新成功: {order_id}, 新状态: {order_status}", current_user)
        return JSONResponse({
            "success": True,
            "message": "订单刷新成功",
            "data": {
                "order_id": order_id,
                "order_status": order_status,
            }
        })

    except HTTPException:
        raise
    except Exception as e:
        log_with_user('error', f"刷新订单失败: {str(e)}", current_user)
        raise HTTPException(status_code=500, detail="刷新订单失败")


@router.put('/api/orders/{order_id}')
async def update_order(
    order_id: str,
    update_data: dict,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    更新订单信息
    自动检查订单数据完整性，如数据不完整则通过 Playwright 从订单详情页获取最新完整数据
    获取完整信息包括：订单ID、商品ID、买家ID、规格、数量、金额、订单状态、收货人信息
    """
    try:
        from db_manager import db_manager
        from utils.order_fetcher_optimized import fetch_order_complete

        user_id = current_user['user_id']
        log_with_user('info', f"更新订单: {order_id}, 数据: {update_data}", current_user)

        # 获取用户的所有Cookie
        user_cookies = db_manager.get_all_cookies(user_id)

        # 验证订单属于当前用户
        order = db_manager.get_order_by_id(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="订单不存在")

        if order.get('cookie_id') not in user_cookies:
            raise HTTPException(status_code=403, detail="无权修改此订单")

        # 检查订单数据完整性
        is_complete = check_order_data_completeness(order)

        if not is_complete:
            log_with_user('info', f"订单 {order_id} 数据不完整，开始使用Playwright获取完整数据", current_user)

            # 获取该订单对应的Cookie字符串
            cookie_id = order.get('cookie_id')
            cookie_string = user_cookies.get(cookie_id)

            if cookie_string:

                try:
                    # 使用优化后的合并函数：一次浏览器访问获取所有数据
                    log_with_user('info', f"使用优化方法获取订单 {order_id} 的完整数据", current_user)

                    complete_result = await fetch_order_complete(
                        order_id=order_id,
                        cookie_id=cookie_id,
                        cookie_string=cookie_string,
                        timeout=30,
                        headless=True,
                        use_pool=True  # 使用浏览器池
                    )

                    if complete_result:
                        log_with_user('info', f"成功获取订单 {order_id} 的完整数据（一次浏览器调用）", current_user)

                        # 状态码映射（如果需要转换）
                        order_status = complete_result.get('order_status', 'unknown')
                        if order_status and isinstance(order_status, str) and order_status.isdigit():
                            status_mapping = {
                                '1': 'processing',
                                '2': 'pending_ship',
                                '3': 'shipped',
                                '4': 'completed',
                                '5': 'refunding',
                                '6': 'cancelled',
                                '7': 'refunding',
                                '8': 'cancelled',
                                '9': 'refunding',
                                '10': 'cancelled',
                            }
                            order_status = status_mapping.get(order_status, order_status)

                        # 构建要更新的完整数据
                        refresh_data = {
                            'order_id': order_id,
                            'item_id': complete_result.get('item_id') or order.get('item_id'),
                            'buyer_id': complete_result.get('buyer_id') or order.get('buyer_id'),
                            'order_status': order_status or order.get('order_status'),
                            'spec_name': complete_result.get('spec_name') or None,
                            'spec_value': complete_result.get('spec_value') or None,
                            'quantity': complete_result.get('quantity') or None,
                            'amount': complete_result.get('amount') or None,
                            'created_at': complete_result.get('order_time') or None,
                            'receiver_name': complete_result.get('receiver_name') or None,
                            'receiver_phone': complete_result.get('receiver_phone') or None,
                            'receiver_address': complete_result.get('receiver_address') or None
                        }

                        # 更新数据库
                        db_manager.insert_or_update_order(**refresh_data)
                        log_with_user('info', f"订单 {order_id} 完整数据已更新到数据库", current_user)
                    else:
                        log_with_user('warning', f"订单 {order_id} 详情获取失败，继续使用现有数据", current_user)

                except Exception as e:
                    log_with_user('error', f"获取订单 {order_id} 详情时出错: {str(e)}", current_user)
                    # 继续执行，即使刷新失败也允许用户手动更新
            else:
                log_with_user('warning', f"订单 {order_id} 的Cookie信息不完整，无法刷新", current_user)

        # 提取可更新的字段
        allowed_fields = {
            'item_id', 'buyer_id', 'spec_name', 'spec_value',
            'quantity', 'amount', 'order_status',
            'receiver_name', 'receiver_phone', 'receiver_address',
            'system_shipped', 'created_at'
        }

        # 只保留允许更新的字段
        filtered_data = {k: v for k, v in update_data.items() if k in allowed_fields}

        if not filtered_data:
            # 如果没有用户提供的更新数据
            if not is_complete:
                # 数据不完整，已经进行了自动刷新，返回刷新后的订单
                updated_order = db_manager.get_order_by_id(order_id)
                return {
                    "success": True,
                    "message": "订单数据已自动刷新",
                    "data": updated_order,
                    "refreshed": True
                }
            else:
                # 数据完整，直接返回当前订单信息
                updated_order = db_manager.get_order_by_id(order_id)
                return {
                    "success": True,
                    "message": "订单数据已是最新",
                    "data": updated_order,
                    "refreshed": False
                }

        # 应用用户提供的更新
        success = db_manager.insert_or_update_order(
            order_id=order_id,
            **filtered_data
        )

        if success:
            log_with_user('info', f"订单更新成功: {order_id}", current_user)
            # 返回更新后的订单
            updated_order = db_manager.get_order_by_id(order_id)
            return {
                "success": True,
                "message": "更新成功",
                "data": updated_order,
                "refreshed": not is_complete  # 标记是否进行了自动刷新
            }
        else:
            raise HTTPException(status_code=500, detail="更新失败")

    except HTTPException:
        raise
    except Exception as e:
        log_with_user('error', f"更新订单失败: {str(e)}", current_user)
        raise HTTPException(status_code=500, detail="更新订单失败")


@router.post('/api/orders/refresh')
async def refresh_orders_status(
    cookie_id: Optional[str] = Form(None),
    status: Optional[str] = Form(None),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    智能刷新订单状态
    1. 从数据库获取订单列表（支持筛选）
    2. 对非'已发货'状态的订单，使用Playwright查询最新状态
    3. 更新数据库中有变化的订单
    """
    try:
        from db_manager import db_manager
        from utils.order_fetcher_optimized import process_orders_batch

        user_id = current_user['user_id']
        log_with_user('info', f"开始智能刷新订单状态（优化版：并发处理） (cookie_id={cookie_id}, status={status})", current_user)

        # 获取用户的所有Cookie
        user_cookies = db_manager.get_all_cookies(user_id)

        # 如果指定了cookie_id，只使用该Cookie
        if cookie_id:
            if cookie_id not in user_cookies:
                raise HTTPException(status_code=404, detail="Cookie不存在或无权访问")
            user_cookies = {cookie_id: user_cookies[cookie_id]}

        # 获取需要刷新的订单
        orders_to_refresh = []
        for cid in user_cookies.keys():
            # 获取该Cookie的所有订单
            orders = db_manager.get_orders_by_cookie(cid, limit=1000)

            # 筛选需要刷新的订单
            for order in orders:
                # 如果指定了状态筛选，只刷新该状态的订单
                if status and order.get('status') != status:
                    continue

                order_status = order.get('status', 'unknown')

                # 判断是否需要刷新：只根据状态判断
                # 稳定状态（已发货、交易成功、交易关闭）的订单不需要刷新
                needs_refresh = order_status not in ['shipped', 'completed', 'cancelled']

                if needs_refresh:
                    orders_to_refresh.append({
                        'order_id': order['order_id'],
                        'cookie_id': cid,
                        'current_status': order_status
                    })

        log_with_user('info', f"找到 {len(orders_to_refresh)} 个需要刷新的订单", current_user)

        if not orders_to_refresh:
            return JSONResponse({
                "success": True,
                "message": "没有需要刷新的订单",
                "summary": {
                    "total": 0,
                    "updated": 0,
                    "no_change": 0,
                    "failed": 0
                },
                "results": []
            })

        # 刷新订单信息（包括状态、买家ID、金额等）
        updated_count = 0
        failed_count = 0
        no_change_count = 0
        refresh_results = []

        # 按cookie_id分组订单（因为每个cookie需要单独的浏览器实例）
        orders_by_cookie = {}
        for order_info in orders_to_refresh:
            cid = order_info['cookie_id']
            if cid not in orders_by_cookie:
                orders_by_cookie[cid] = []
            orders_by_cookie[cid].append(order_info)

        # 对每个cookie的订单进行并发批量处理
        for cid, cookie_orders in orders_by_cookie.items():
            cookies_str = user_cookies[cid]
            if not cookies_str:
                log_with_user('warning', f"Cookie {cid} 的值为空，跳过", current_user)
                failed_count += len(cookie_orders)
                continue

            # 提取订单ID列表
            order_ids = [o['order_id'] for o in cookie_orders]
            log_with_user('info', f"使用并发处理Cookie {cid} 的 {len(order_ids)} 个订单", current_user)

            # 并发批量处理（一次浏览器调用获取所有数据）
            batch_results = await process_orders_batch(
                order_ids=order_ids,
                cookie_id=cid,
                cookie_string=cookies_str,
                max_concurrent=5,  # 并发5个
                timeout=30,
                headless=True,
                use_pool=True,  # 使用浏览器池
                force_refresh=True  # 强制刷新，跳过缓存检查
            )

            # 处理结果并更新数据库
            for i, result in enumerate(batch_results):
                order_info = cookie_orders[i]
                order_id = order_info['order_id']
                current_status = order_info['current_status']

                if result and not result.get('error'):
                    # 调试：打印API和DOM状态
                    api_status = result.get('api_status', 'N/A')
                    dom_status = result.get('dom_status', 'N/A')
                    log_with_user('debug', f"订单 {order_id} - API状态: {api_status}, DOM状态: {dom_status}", current_user)

                    # 状态码映射
                    order_status = result.get('order_status', 'unknown')
                    if order_status and str(order_status).isdigit():
                        status_mapping = {
                            '1': 'processing',
                            '2': 'pending_ship',
                            '3': 'shipped',
                            '4': 'completed',
                            '5': 'refunding',
                            '6': 'cancelled',
                            '7': 'refunding',
                            '8': 'cancelled',
                            '9': 'refunding',
                            '10': 'cancelled',
                            '11': 'completed',  # 交易完成
                            '12': 'cancelled',  # 交易关闭
                        }
                        order_status = status_mapping.get(str(order_status), order_status)

                    # 更新数据库
                    success = db_manager.insert_or_update_order(
                        order_id=order_id,
                        item_id=result.get('item_id') or None,
                        buyer_id=result.get('buyer_id') or None,
                        spec_name=result.get('spec_name') or None,
                        spec_value=result.get('spec_value') or None,
                        quantity=result.get('quantity') or None,
                        amount=result.get('amount') or None,
                        order_status=order_status if order_status != current_status else None,
                        cookie_id=cid,
                        created_at=result.get('order_time') or None,
                        receiver_name=result.get('receiver_name') or None,
                        receiver_phone=result.get('receiver_phone') or None,
                        receiver_address=result.get('receiver_address') or None
                    )

                    if success:
                        # 检查是否有更新
                        has_changes = (
                            order_status != current_status or
                            result.get('buyer_id') or
                            result.get('amount')
                        )

                        if has_changes:
                            updated_count += 1
                            refresh_results.append({
                                'order_id': order_id,
                                'old_status': current_status,
                                'new_status': order_status,
                                'status_text': result.get('status_text', '')
                            })
                            log_with_user('info', f"订单 {order_id} 已更新 | {current_status} -> {order_status}", current_user)
                        else:
                            no_change_count += 1
                    else:
                        failed_count += 1
                        log_with_user('error', f"订单 {order_id} 更新失败", current_user)
                else:
                    failed_count += 1
                    error_msg = result.get('error', '未知错误') if result else '未知错误'
                    log_with_user('warning', f"订单 {order_id} 获取失败: {error_msg}", current_user)

        # 由于我们已经处理完所有订单，跳过原来的循环
        # 下面的代码需要删除，所以我们需要找到循环结束的位置
        if False:  # 这个if永远不会执行，只是为了保持代码结构
            for order_info in orders_to_refresh:
                order_id = order_info['order_id']
                cookie_id = order_info['cookie_id']
                current_status = order_info['current_status']

                try:
                    # 获取Cookie (get_all_cookies返回的是 {cookie_id: cookie_value} 格式)
                    cookies_str = user_cookies[cookie_id]

                    if not cookies_str:
                        log_with_user('warning', f"Cookie {cookie_id} 的值为空，跳过订单 {order_id}", current_user)
                        failed_count += 1
                        continue

                    # 使用订单详情获取器获取完整信息（包括买家ID、金额、收货人信息）
                    # 注意：fetch_order_detail_simple 已经能获取所有需要的数据，无需再调用 OrderStatusQueryPlaywright
                    order_detail = await fetch_order_detail_simple(order_id, cookies_str, headless=True)

                    if order_detail:
                        # 提取订单详情（从页面获取）
                        spec_name = order_detail.get('spec_name', '')
                        spec_value = order_detail.get('spec_value', '')
                        quantity = order_detail.get('quantity', '')
                        amount = order_detail.get('amount', '')
                        receiver_name = order_detail.get('receiver_name', '')
                        receiver_phone = order_detail.get('receiver_phone', '')
                        receiver_address = order_detail.get('receiver_address', '')

                        # 只使用状态查询获取订单状态和买家ID（因为DOM解析无法获取这些）
                        query = OrderStatusQueryPlaywright(cookies_str, cookie_id, headless=True)
                        status_result = await query.query_order_status(order_id)

                        new_status = current_status
                        new_status_text = ''
                        buyer_id = ''
                        item_id = ''
                        is_bargain = None

                        if status_result.get('success'):
                            new_status_code = status_result.get('order_status')
                            new_status_text = status_result.get('status_text', '')

                            # 将状态码转换为数据库状态
                            # 完整的订单状态码映射（基于闲鱼API）
                            status_mapping = {
                                1: 'processing',      # 处理中
                                2: 'pending_ship',    # 待发货
                                3: 'shipped',         # 已发货
                                4: 'completed',       # 已完成/交易成功
                                5: 'refunding',       # 退款中
                                6: 'cancelled',       # 已取消/已关闭
                                7: 'refunding',       # 退款申请中
                                8: 'cancelled',       # 退款成功（订单关闭）
                                9: 'refunding',       # 退款协商中
                                10: 'cancelled',      # 退款关闭
                            }
                            new_status = status_mapping.get(new_status_code, 'unknown')

                            # 特殊处理：根据状态文本智能识别（优先检查最终状态）
                            if new_status == 'unknown':
                                # 优先级1: 检查"退款成功"（最终状态）
                                if '退款' in new_status_text and '成功' in new_status_text:
                                    new_status = 'cancelled'  # 退款成功=订单关闭
                                # 优先级2: 检查"关闭"或"取消"（最终状态）
                                elif '关闭' in new_status_text or '取消' in new_status_text or '超时' in new_status_text:
                                    new_status = 'cancelled'
                                # 优先级3: 检查"完成"或"交易成功"（最终状态）
                                elif '完成' in new_status_text or '交易成功' in new_status_text or '确认收货' in new_status_text:
                                    new_status = 'completed'
                                # 优先级4: 检查"退款"（中间状态）
                                elif '退款' in new_status_text:
                                    new_status = 'refunding'

                            log_with_user('debug', f"订单 {order_id}: 状态码={new_status_code}, 状态文本={new_status_text}, 映射结果={new_status}", current_user)

                            # 从 raw_data 中提取完整信息
                            raw_data = status_result.get('raw_data', {})

                            # 提取买家ID、商品ID、时间信息
                            created_at = None
                            try:
                                # 方法1: 从根级别提取 peerUserId (买家ID)
                                buyer_id = str(raw_data.get('peerUserId', ''))

                                # 方法2: 从根级别提取 itemId (商品ID)
                                item_id = str(raw_data.get('itemId', ''))

                                # 方法3: 从 orderStatusVO 组件中提取下单时间
                                if 'components' in raw_data:
                                    for component in raw_data['components']:
                                        if component.get('render') == 'orderStatusVO':
                                            order_status_data = component.get('data', {})
                                            # 从 orderStatusNodeList 中找到第一个时间节点（已拍下时间 = 创建时间）
                                            node_list = order_status_data.get('orderStatusNodeList', [])
                                            if node_list and len(node_list) > 0:
                                                created_at = node_list[0].get('time')  # 第一个是"已拍下"时间
                                            break

                                # 方法4: 从 orderInfoVO 组件中提取是否小刀（如果有 bargainInfo）
                                if 'components' in raw_data:
                                    for component in raw_data['components']:
                                        if component.get('render') == 'orderInfoVO':
                                            data = component.get('data', {})
                                            # 检查是否有小刀信息
                                            if 'bargainInfo' in data:
                                                bargain_info = data.get('bargainInfo', {})
                                                is_bargain = bargain_info.get('bargain', False)
                                            # 如果前面没找到商品ID，尝试从 jumpUrl 中提取
                                            if not item_id:
                                                item_info = data.get('itemInfo', {})
                                                jump_url = item_info.get('jumpUrl', '')
                                                if 'id=' in jump_url:
                                                    item_id = jump_url.split('id=')[1].split('&')[0]
                                            break

                                if created_at:
                                    log_with_user('debug', f"提取到订单创建时间: {created_at}", current_user)

                            except Exception as e:
                                log_with_user('warning', f"提取订单信息失败: {str(e)}", current_user)

                        # 更新数据库（包含所有字段）
                        success = db_manager.insert_or_update_order(
                            order_id=order_id,
                            item_id=item_id if item_id else None,
                            buyer_id=buyer_id if buyer_id else None,
                            spec_name=spec_name if spec_name else None,
                            spec_value=spec_value if spec_value else None,
                            quantity=quantity if quantity else None,
                            amount=amount if amount else None,
                            order_status=new_status if new_status != current_status else None,
                            is_bargain=is_bargain if is_bargain is not None else None,
                            cookie_id=cookie_id,
                            created_at=created_at,  # 添加创建时间（从API提取的北京时间）
                            receiver_name=receiver_name if receiver_name else None,
                            receiver_phone=receiver_phone if receiver_phone else None,
                            receiver_address=receiver_address if receiver_address else None
                        )

                        if success:
                            # 检查是否有任何更新
                            has_changes = (
                                new_status != current_status or
                                (buyer_id and buyer_id != 'unknown_user') or
                                amount
                            )

                            if has_changes:
                                updated_count += 1
                                refresh_results.append({
                                    'order_id': order_id,
                                    'old_status': current_status,
                                    'new_status': new_status,
                                    'status_text': new_status_text
                                })
                                log_with_user('info', f"订单 {order_id} 信息已更新 | 状态: {current_status} -> {new_status} | 买家: {buyer_id} | 金额: {amount}", current_user)
                            else:
                                no_change_count += 1
                                log_with_user('debug', f"订单 {order_id} 信息无变化", current_user)
                        else:
                            failed_count += 1
                            log_with_user('error', f"订单 {order_id} 信息更新失败", current_user)
                    else:
                        failed_count += 1
                        log_with_user('warning', f"订单 {order_id} 详情获取失败", current_user)

                except Exception as e:
                    failed_count += 1
                    log_with_user('error', f"刷新订单 {order_id} 时发生异常: {str(e)}", current_user)

        # 返回刷新结果
        log_with_user('info', f"订单刷新完成: 更新{updated_count}个, 无变化{no_change_count}个, 失败{failed_count}个", current_user)

        return JSONResponse({
            "success": True,
            "message": f"刷新完成: 更新{updated_count}个, 无变化{no_change_count}个, 失败{failed_count}个",
            "summary": {
                "total": len(orders_to_refresh),
                "updated": updated_count,
                "no_change": no_change_count,
                "failed": failed_count
            },
            "updated_orders": refresh_results
        })

    except HTTPException:
        raise
    except Exception as e:
        log_with_user('error', f"刷新订单状态失败: {str(e)}", current_user)
        raise HTTPException(status_code=500, detail="刷新订单状态失败")


# 已取消：全量核对订单数据功能
# 现在使用更新订单状态接口进行单个订单的数据核查
# @router.post('/api/orders/verify-all')
# async def verify_all_orders(current_user: Dict[str, Any] = Depends(get_current_user)):
#     """
#     全量核对所有订单数据
#     通过 Playwright 访问每个订单的详情页，更新时间、收货人信息等
#     """
#     pass


@router.post('/api/orders/manual-ship')
async def manual_ship_orders(
    order_ids: List[str] = Body(..., description="订单ID列表"),
    ship_mode: str = Body(..., description="发货模式: status_only（仅修改发货状态）或 full_delivery（完整发货流程）"),
    custom_content: Optional[str] = Body(None, description="自定义发货内容（保留兼容）"),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    手动发货

    发货模式：
    - status_only: 仅在闲鱼标记为已发货（不发送卡券给买家）
    - full_delivery: 完整发货流程（匹配卡券、发送卡券给买家、标记发货状态）
    """
    try:
        from db_manager import db_manager
        from XianyuAutoAsync import XianyuLive
        import asyncio

        user_id = current_user['user_id']
        log_with_user('info', f"开始手动发货: 订单数量={len(order_ids)}, 模式={ship_mode}", current_user)

        # 验证发货模式
        if ship_mode not in ['status_only', 'full_delivery']:
            raise HTTPException(status_code=400, detail="发货模式必须是 status_only 或 full_delivery")

        # 获取用户的所有Cookie
        user_cookies = db_manager.get_all_cookies(user_id)

        success_count = 0
        failed_count = 0
        results = []

        # 遍历每个订单
        for order_id in order_ids:
            try:
                # 获取订单信息
                order = db_manager.get_order_by_id(order_id)
                if not order:
                    results.append({
                        'order_id': order_id,
                        'success': False,
                        'message': '订单不存在'
                    })
                    failed_count += 1
                    continue

                # 验证订单属于当前用户
                cookie_id = order.get('cookie_id')
                if cookie_id not in user_cookies:
                    results.append({
                        'order_id': order_id,
                        'success': False,
                        'message': '无权操作此订单'
                    })
                    failed_count += 1
                    continue

                item_id = order.get('item_id')
                buyer_id = order.get('buyer_id')

                if ship_mode == 'status_only':
                    # ====== 仅修改闲鱼发货状态 ======
                    if not item_id:
                        results.append({
                            'order_id': order_id,
                            'success': False,
                            'message': '订单缺少商品ID'
                        })
                        failed_count += 1
                        continue

                    # 获取cookies_str用于创建独立session
                    cookies_str = user_cookies.get(cookie_id)
                    if not cookies_str:
                        results.append({
                            'order_id': order_id,
                            'success': False,
                            'message': '无法获取账号Cookie信息'
                        })
                        failed_count += 1
                        continue

                    # 创建独立的aiohttp session（避免跨异步上下文问题）
                    import aiohttp
                    from secure_confirm_decrypted import SecureConfirm

                    try:
                        async with aiohttp.ClientSession(
                            headers={'cookie': cookies_str},
                            timeout=aiohttp.ClientTimeout(total=30)
                        ) as session:
                            confirm = SecureConfirm(session, cookies_str, cookie_id, None)
                            confirm_result = await confirm.auto_confirm(order_id, item_id)

                        if confirm_result and confirm_result.get('success'):
                            # 更新本地数据库状态
                            db_manager.insert_or_update_order(
                                order_id=order_id,
                                order_status='shipped',
                                system_shipped=True
                            )
                            results.append({
                                'order_id': order_id,
                                'success': True,
                                'message': '已成功修改闲鱼发货状态'
                            })
                            success_count += 1
                        else:
                            error_msg = confirm_result.get('error', '未知错误') if confirm_result else '确认发货返回空结果'
                            results.append({
                                'order_id': order_id,
                                'success': False,
                                'message': f'修改发货状态失败: {error_msg}'
                            })
                            failed_count += 1
                    except Exception as e:
                        log_with_user('error', f"确认发货异常: {str(e)}", current_user)
                        results.append({
                            'order_id': order_id,
                            'success': False,
                            'message': '确认发货异常，请稍后重试'
                        })
                        failed_count += 1

                elif ship_mode == 'full_delivery':
                    # ====== 完整发货流程：匹配卡券 + 发送卡券 + 修改状态 ======
                    if not item_id:
                        results.append({
                            'order_id': order_id,
                            'success': False,
                            'message': '订单缺少商品ID，无法匹配发货规则'
                        })
                        failed_count += 1
                        continue

                    if not buyer_id:
                        results.append({
                            'order_id': order_id,
                            'success': False,
                            'message': '订单缺少买家ID，无法发送卡券'
                        })
                        failed_count += 1
                        continue

                    # 必须有运行中的实例（需要WebSocket发送消息）
                    live_instance = XianyuLive.get_instance(cookie_id)
                    if not live_instance:
                        results.append({
                            'order_id': order_id,
                            'success': False,
                            'message': '该账号未在线运行，无法执行完整发货。请先启动账号。'
                        })
                        failed_count += 1
                        continue

                    if not live_instance.ws or live_instance.ws.closed:
                        results.append({
                            'order_id': order_id,
                            'success': False,
                            'message': '该账号WebSocket连接已断开，无法发送消息。请等待重连后重试。'
                        })
                        failed_count += 1
                        continue

                    # 查找与买家的chat_id（优先从订单记录获取，回退到AI对话记录）
                    chat_id = order.get('chat_id') or ''
                    if not chat_id:
                        chat_id = db_manager.find_chat_id_by_buyer(cookie_id, buyer_id)
                    if not chat_id:
                        results.append({
                            'order_id': order_id,
                            'success': False,
                            'message': '未找到与该买家的聊天记录，无法发送卡券消息。请等待买家发送消息后重试。'
                        })
                        failed_count += 1
                        continue

                    # 检查多数量发货
                    quantity_to_send = 1
                    multi_quantity_delivery = db_manager.get_item_multi_quantity_delivery_status(cookie_id, item_id)
                    if multi_quantity_delivery:
                        try:
                            order_detail = await live_instance.fetch_order_detail_info(order_id, item_id, buyer_id)
                            if order_detail and isinstance(order_detail, dict):
                                qty = order_detail.get('quantity', 1)
                                if isinstance(qty, int) and qty > 1:
                                    quantity_to_send = qty
                        except Exception as e:
                            log_with_user('warning', f"获取订单数量失败，使用默认数量1: {str(e)}", current_user)

                    # 调用_auto_delivery获取卡券内容（内部会调用auto_confirm）
                    delivery_contents = []
                    for i in range(quantity_to_send):
                        try:
                            delivery_content = await live_instance._auto_delivery(
                                item_id, '', order_id, buyer_id
                            )
                            if delivery_content:
                                delivery_contents.append(delivery_content)
                        except Exception as e:
                            log_with_user('error', f"获取第{i+1}个卡券失败: {str(e)}", current_user)

                    if not delivery_contents:
                        results.append({
                            'order_id': order_id,
                            'success': False,
                            'message': '未匹配到发货规则或卡券获取失败'
                        })
                        failed_count += 1
                        continue

                    # 发送卡券内容给买家
                    send_success = True
                    for idx, content in enumerate(delivery_contents):
                        try:
                            if content.startswith("__IMAGE_SEND__"):
                                image_data = content.replace("__IMAGE_SEND__", "")
                                card_id = None
                                if "|" in image_data:
                                    card_id_str, image_url = image_data.split("|", 1)
                                    try:
                                        card_id = int(card_id_str)
                                    except ValueError:
                                        card_id = None
                                else:
                                    image_url = image_data
                                await live_instance.send_image_msg(
                                    live_instance.ws, chat_id, buyer_id,
                                    image_url, card_id=card_id
                                )
                            else:
                                await live_instance.send_msg(
                                    live_instance.ws, chat_id, buyer_id, content
                                )

                            # 多条消息之间间隔1秒
                            if len(delivery_contents) > 1 and idx < len(delivery_contents) - 1:
                                await asyncio.sleep(1)
                        except Exception as e:
                            log_with_user('error', f"发送第{idx+1}条卡券消息失败: {str(e)}", current_user)
                            send_success = False

                    # 更新本地数据库状态
                    db_manager.insert_or_update_order(
                        order_id=order_id,
                        order_status='shipped',
                        system_shipped=True
                    )

                    if send_success:
                        results.append({
                            'order_id': order_id,
                            'success': True,
                            'message': f'完整发货成功，已发送{len(delivery_contents)}条卡券信息给买家'
                        })
                        success_count += 1
                    else:
                        results.append({
                            'order_id': order_id,
                            'success': True,
                            'message': f'发货状态已更新，但部分卡券消息发送失败（共{len(delivery_contents)}条）'
                        })
                        success_count += 1

            except Exception as e:
                results.append({
                    'order_id': order_id,
                    'success': False,
                    'message': '系统错误，请稍后重试'
                })
                failed_count += 1
                log_with_user('error', f"发货订单 {order_id} 时发生异常: {str(e)}", current_user)

        log_with_user('info', f"手动发货完成: 成功{success_count}个, 失败{failed_count}个", current_user)

        return {
            "success": True,
            "message": f"发货完成: 成功{success_count}个, 失败{failed_count}个",
            "total": len(order_ids),
            "success_count": success_count,
            "failed_count": failed_count,
            "results": results
        }

    except HTTPException:
        raise
    except Exception as e:
        log_with_user('error', f"手动发货失败: {str(e)}", current_user)
        raise HTTPException(status_code=500, detail="手动发货失败")


@router.post('/api/orders/import')
async def import_orders(
    orders: List[Dict[str, Any]] = Body(..., description="订单列表"),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    导入订单
    支持批量导入自定义订单数据
    """
    try:
        from db_manager import db_manager

        user_id = current_user['user_id']
        log_with_user('info', f"开始导入订单: 订单数量={len(orders)}", current_user)

        # 获取用户的所有Cookie
        user_cookies = db_manager.get_all_cookies(user_id)

        success_count = 0
        failed_count = 0
        results = []

        # 必需字段验证
        required_fields = ['order_id', 'cookie_id']
        optional_fields = [
            'item_id', 'item_title', 'item_price', 'item_image',
            'buyer_id',
            'receiver_name', 'receiver_phone', 'receiver_address', 'receiver_city',
            'status', 'status_text', 'order_time', 'pay_time',
            'quantity', 'amount'
        ]

        for order_data in orders:
            try:
                # 验证必需字段
                missing_fields = [f for f in required_fields if not order_data.get(f)]
                if missing_fields:
                    results.append({
                        'order_id': order_data.get('order_id', 'unknown'),
                        'success': False,
                        'message': f'缺少必需字段: {", ".join(missing_fields)}'
                    })
                    failed_count += 1
                    continue

                order_id = str(order_data['order_id'])
                cookie_id = str(order_data['cookie_id'])

                # 验证Cookie属于当前用户
                if cookie_id not in user_cookies:
                    results.append({
                        'order_id': order_id,
                        'success': False,
                        'message': '无权操作此账号的订单'
                    })
                    failed_count += 1
                    continue

                # 检查订单是否已存在
                existing_order = db_manager.get_order_by_id(order_id)

                # 准备订单数据，直接使用 insert_or_update_order 的参数名
                # 构建参数字典，只传递非 None 的值
                insert_params = {
                    'order_id': order_id,
                    'cookie_id': cookie_id
                }

                # 前端字段名 -> 数据库参数名映射
                param_mapping = {
                    'item_id': 'item_id',
                    'buyer_id': 'buyer_id',
                    'receiver_name': 'receiver_name',
                    'receiver_phone': 'receiver_phone',
                    'receiver_address': 'receiver_address',
                    'receiver_city': 'receiver_city',
                    'status': 'order_status',  # 注意：前端用 status，后端用 order_status
                    'status_text': 'status_text',
                    'order_time': 'order_time',
                    'pay_time': 'pay_time',
                    'quantity': 'quantity',
                    'amount': 'amount',
                    'item_title': 'item_title',
                    'item_price': 'item_price',
                    'item_image': 'item_image'
                }

                # 遍历订单数据，添加到参数字典
                for field, value in order_data.items():
                    if value is not None and field in param_mapping:
                        param_name = param_mapping[field]
                        insert_params[param_name] = value

                # 使用 insert_or_update_order 统一处理
                db_manager.insert_or_update_order(**insert_params)

                results.append({
                    'order_id': order_id,
                    'success': True,
                    'message': '订单已更新' if existing_order else '订单已导入'
                })

                success_count += 1

            except Exception as e:
                results.append({
                    'order_id': order_data.get('order_id', 'unknown'),
                    'success': False,
                    'message': '系统错误，请稍后重试'
                })
                failed_count += 1
                log_with_user('error', f"导入订单时发生异常: {str(e)}", current_user)

        log_with_user('info', f"导入订单完成: 成功{success_count}个, 失败{failed_count}个", current_user)

        return {
            "success": True,
            "message": f"导入完成: 成功{success_count}个, 失败{failed_count}个",
            "total": len(orders),
            "success_count": success_count,
            "failed_count": failed_count,
            "results": results
        }

    except HTTPException:
        raise
    except Exception as e:
        log_with_user('error', f"导入订单失败: {str(e)}", current_user)
        raise HTTPException(status_code=500, detail="导入订单失败")


# ==================== 黑名单 API ====================
