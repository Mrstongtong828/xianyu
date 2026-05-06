"""
analytics 路由模块
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
from typing import Optional, Dict, Any

from shared import db_manager, get_current_user, log_with_user

router = APIRouter()


@router.get('/analytics/orders')
def get_order_analytics(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    try:
        log_with_user('info', f"查询订单分析数据: {start_date} ~ {end_date}", current_user)
        result = db_manager.get_order_analytics(
            start_date=start_date,
            end_date=end_date,
            user_id=current_user.get('user_id')
        )
        return result
    except Exception as e:
        log_with_user('error', f"查询订单分析数据失败: {e}", current_user)
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/analytics/orders/valid')
def get_valid_orders(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    try:
        log_with_user('info', f"查询有效订单列表: {start_date} ~ {end_date}", current_user)
        orders = db_manager.get_orders_for_analytics(
            start_date=start_date,
            end_date=end_date,
            user_id=current_user.get('user_id')
        )
        return {'orders': orders}
    except Exception as e:
        log_with_user('error', f"查询有效订单列表失败: {e}", current_user)
        raise HTTPException(status_code=500, detail=str(e))
