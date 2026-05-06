# -*- coding: utf-8 -*-
"""
STATS DAO Mixin
"""

from loguru import logger
import sqlite3
import time
from typing import List, Tuple, Dict, Optional, Any


class StatsDAOMixin:
    """STATS related database operations"""

    def get_order_analytics(self, start_date: str = None, end_date: str = None, user_id: int = None, include_statuses: list = None):
        """
        获取订单分析数据

        Args:
            start_date: 开始日期 (格式: YYYY-MM-DD)
            end_date: 结束日期 (格式: YYYY-MM-DD)
            user_id: 用户ID (可选)
            include_statuses: 要包含的订单状态列表 (可选，如果指定则只统计这些状态)

        Returns:
            包含订单分析数据的字典
        """
        with self.lock:
            try:
                cursor = self.conn.cursor()

                # 构建WHERE条件
                where_conditions = []
                params = []

                if start_date:
                    where_conditions.append("DATE(created_at) >= ?")
                    params.append(start_date)

                if end_date:
                    where_conditions.append("DATE(created_at) <= ?")
                    params.append(end_date)

                # 关联cookies表以过滤user_id
                if user_id is not None:
                    where_conditions.append("EXISTS (SELECT 1 FROM cookies WHERE cookies.id = orders.cookie_id AND cookies.user_id = ?)")
                    params.append(user_id)

                # 只包含指定状态（小写形式）
                if include_statuses:
                    placeholders = ','.join(['?' for _ in include_statuses])
                    where_conditions.append(f"order_status IN ({placeholders})")
                    params.extend(include_statuses)

                where_clause = f"WHERE {' AND '.join(where_conditions)}" if where_conditions else ""

                # 1. 总收益统计（估值，实际会扣税等）
                cursor.execute(f"""
                    SELECT
                        COUNT(DISTINCT order_id) as total_orders,
                        SUM(CAST(REPLACE(REPLACE(amount, '¥', ''), ',', '') AS REAL)) as total_amount,
                        AVG(CAST(REPLACE(REPLACE(amount, '¥', ''), ',', '') AS REAL)) as avg_amount,
                        COUNT(DISTINCT buyer_id) as unique_buyers,
                        COUNT(DISTINCT item_id) as unique_items
                    FROM orders
                    {where_clause}
                    AND amount IS NOT NULL AND amount != '' AND amount != 'N/A'
                """, params)

                row = cursor.fetchone()
                revenue_stats = {
                    'total_orders': row[0] or 0,
                    'total_amount': round(row[1] or 0, 2),
                    'avg_amount': round(row[2] or 0, 2),
                    'unique_buyers': row[3] or 0,
                    'unique_items': row[4] or 0
                } if row else {}

                # 2. 按日期统计订单量和收益
                cursor.execute(f"""
                    SELECT
                        DATE(created_at) as date,
                        COUNT(DISTINCT order_id) as order_count,
                        SUM(CAST(REPLACE(REPLACE(amount, '¥', ''), ',', '') AS REAL)) as daily_amount
                    FROM orders
                    {where_clause}
                    AND amount IS NOT NULL AND amount != '' AND amount != 'N/A'
                    GROUP BY DATE(created_at)
                    ORDER BY date DESC
                    LIMIT 30
                """, params)

                daily_stats = []
                for row in cursor.fetchall():
                    daily_stats.append({
                        'date': row[0],
                        'order_count': row[1],
                        'amount': round(row[2] or 0, 2)
                    })

                # 3. 按状态统计订单
                cursor.execute(f"""
                    SELECT
                        order_status,
                        COUNT(DISTINCT order_id) as count,
                        SUM(CAST(REPLACE(REPLACE(amount, '¥', ''), ',', '') AS REAL)) as amount
                    FROM orders
                    {where_clause}
                    AND amount IS NOT NULL AND amount != '' AND amount != 'N/A'
                    GROUP BY order_status
                    ORDER BY count DESC
                """, params)

                status_stats = []
                for row in cursor.fetchall():
                    status_stats.append({
                        'status': row[0] or 'unknown',
                        'count': row[1],
                        'amount': round(row[2] or 0, 2)
                    })

                # 4. 按城市统计地区分布（如果有收货城市数据）
                cursor.execute(f"""
                    SELECT
                        receiver_city,
                        COUNT(DISTINCT order_id) as order_count,
                        SUM(CAST(REPLACE(REPLACE(amount, '¥', ''), ',', '') AS REAL)) as total_amount
                    FROM orders
                    {where_clause}
                    AND receiver_city IS NOT NULL AND receiver_city != ''
                    AND amount IS NOT NULL AND amount != '' AND amount != 'N/A'
                    GROUP BY receiver_city
                    ORDER BY order_count DESC
                    LIMIT 50
                """, params)

                city_stats = []
                for row in cursor.fetchall():
                    city_stats.append({
                        'city': row[0],
                        'order_count': row[1],
                        'total_amount': round(row[2] or 0, 2)
                    })

                # 5. 商品排行（按订单量）
                cursor.execute(f"""
                    SELECT
                        item_id,
                        COUNT(DISTINCT order_id) as order_count,
                        SUM(CAST(REPLACE(REPLACE(amount, '¥', ''), ',', '') AS REAL)) as total_amount,
                        AVG(CAST(REPLACE(REPLACE(amount, '¥', ''), ',', '') AS REAL)) as avg_amount
                    FROM orders
                    {where_clause}
                    AND item_id IS NOT NULL AND item_id != ''
                    AND amount IS NOT NULL AND amount != '' AND amount != 'N/A'
                    GROUP BY item_id
                    ORDER BY order_count DESC
                    LIMIT 20
                """, params)

                item_stats = []
                for row in cursor.fetchall():
                    item_stats.append({
                        'item_id': row[0],
                        'order_count': row[1],
                        'total_amount': round(row[2] or 0, 2),
                        'avg_amount': round(row[3] or 0, 2)
                    })

                return {
                    'revenue_stats': revenue_stats,
                    'daily_stats': daily_stats,
                    'status_stats': status_stats,
                    'city_stats': city_stats,
                    'item_stats': item_stats
                }

            except Exception as e:
                logger.error(f"获取订单分析数据失败: {e}")
                return {'error': str(e)}



