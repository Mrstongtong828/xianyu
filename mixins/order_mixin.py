"""
Order Mixin - 订单管理
"""
import sqlite3
import json
import time
import secrets
from typing import Optional, Dict, Any, List, Tuple
from loguru import logger


class OrderManagerMixin:
    """订单管理"""

    def insert_or_update_order(self, order_id: str, item_id: str = None, buyer_id: str = None,
                              spec_name: str = None, spec_value: str = None, quantity: str = None,
                              amount: str = None, order_status: str = None, cookie_id: str = None,
                              is_bargain: bool = None, created_at: str = None, receiver_name: str = None,
                              receiver_phone: str = None, receiver_address: str = None,
                              system_shipped: bool = None, expected_version: int = None,
                              chat_id: str = None):
        """插入或更新订单信息"""
        with self.lock:
            try:
                cursor = self.conn.cursor()

                # 检查cookie_id是否在cookies表中存在（如果提供了cookie_id）
                if cookie_id:
                    cursor.execute("SELECT id FROM cookies WHERE id = ?", (cookie_id,))
                    cookie_exists = cursor.fetchone()
                    if not cookie_exists:
                        logger.warning(f"Cookie ID {cookie_id} 不存在于cookies表中，拒绝插入订单 {order_id}")
                        return False

                # 检查订单是否已存在
                cursor.execute("SELECT order_id FROM orders WHERE order_id = ?", (order_id,))
                existing = cursor.fetchone()

                if existing:
                    # 更新现有订单
                    update_fields = []
                    update_values = []

                    if item_id is not None:
                        update_fields.append("item_id = ?")
                        update_values.append(item_id)
                    if buyer_id is not None:
                        update_fields.append("buyer_id = ?")
                        update_values.append(buyer_id)
                    if spec_name is not None:
                        update_fields.append("spec_name = ?")
                        update_values.append(spec_name)
                    if spec_value is not None:
                        update_fields.append("spec_value = ?")
                        update_values.append(spec_value)
                    if quantity is not None:
                        update_fields.append("quantity = ?")
                        update_values.append(quantity)
                    if amount is not None:
                        update_fields.append("amount = ?")
                        update_values.append(amount)
                    if order_status is not None:
                        update_fields.append("order_status = ?")
                        update_values.append(order_status)
                    if cookie_id is not None:
                        update_fields.append("cookie_id = ?")
                        update_values.append(cookie_id)
                    if is_bargain is not None:
                        update_fields.append("is_bargain = ?")
                        update_values.append(1 if is_bargain else 0)
                    if created_at is not None:
                        # 更新创建时间（仅当明确提供时）
                        update_fields.append("created_at = ?")
                        update_values.append(created_at)
                    if receiver_name is not None:
                        update_fields.append("receiver_name = ?")
                        update_values.append(receiver_name)
                    if receiver_phone is not None:
                        update_fields.append("receiver_phone = ?")
                        update_values.append(receiver_phone)
                    if receiver_address is not None:
                        update_fields.append("receiver_address = ?")
                        update_values.append(receiver_address)
                    if system_shipped is not None:
                        update_fields.append("system_shipped = ?")
                        update_values.append(1 if system_shipped else 0)
                    if chat_id is not None:
                        update_fields.append("chat_id = ?")
                        update_values.append(chat_id)

                    if update_fields:
                        update_fields.append("updated_at = CURRENT_TIMESTAMP")
                        # 增加版本号
                        update_fields.append("version = version + 1")

                        # 构建WHERE条件
                        if expected_version is not None:
                            # 使用乐观锁：只有version匹配时才更新
                            where_clause = "order_id = ? AND version = ?"
                            update_values.extend([order_id, expected_version])
                        else:
                            # 不使用乐观锁
                            where_clause = "order_id = ?"
                            update_values.append(order_id)

                        sql = f"UPDATE orders SET {', '.join(update_fields)} WHERE {where_clause}"
                        cursor.execute(sql, update_values)

                        # 检查是否更新成功（乐观锁）
                        if expected_version is not None and cursor.rowcount == 0:
                            logger.warning(f"订单更新失败（版本冲突）: {order_id}, expected_version={expected_version}")
                            return False

                        logger.info(f"更新订单信息: {order_id}")
                else:
                    # 插入新订单
                    if created_at:
                        # 使用提供的创建时间
                        cursor.execute('''
                        INSERT INTO orders (order_id, item_id, buyer_id, spec_name, spec_value,
                                          quantity, amount, order_status, cookie_id, is_bargain, created_at,
                                          receiver_name, receiver_phone, receiver_address, system_shipped, chat_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (order_id, item_id, buyer_id, spec_name, spec_value,
                              quantity, amount, order_status or 'unknown', cookie_id,
                              1 if is_bargain else 0, created_at,
                              receiver_name, receiver_phone, receiver_address,
                              1 if system_shipped else 0, chat_id or ''))
                    else:
                        # 使用默认的创建时间（CURRENT_TIMESTAMP，UTC时间）
                        cursor.execute('''
                        INSERT INTO orders (order_id, item_id, buyer_id, spec_name, spec_value,
                                          quantity, amount, order_status, cookie_id, is_bargain,
                                          receiver_name, receiver_phone, receiver_address, system_shipped, chat_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (order_id, item_id, buyer_id, spec_name, spec_value,
                              quantity, amount, order_status or 'unknown', cookie_id,
                              1 if is_bargain else 0,
                              receiver_name, receiver_phone, receiver_address,
                              1 if system_shipped else 0, chat_id or ''))
                    logger.info(f"插入新订单: {order_id}")

                self.conn.commit()
                return True

            except Exception as e:
                logger.error(f"插入或更新订单失败: {order_id} - {e}")
                self.conn.rollback()
                return False



    def get_order_by_id(self, order_id: str):
        """根据订单ID获取订单信息"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                # 先尝试查询包含version的订单
                cursor.execute('''
                SELECT order_id, item_id, buyer_id, spec_name, spec_value,
                       quantity, amount, order_status, cookie_id, is_bargain, created_at, updated_at, version, chat_id
                FROM orders WHERE order_id = ?
                ''', (order_id,))

                row = cursor.fetchone()
                if row:
                    return {
                        'id': row[0],  # 使用 order_id 作为 id
                        'order_id': row[0],
                        'item_id': row[1],
                        'buyer_id': row[2],
                        'spec_name': row[3],
                        'spec_value': row[4],
                        'quantity': row[5],
                        'amount': row[6],
                        'order_status': row[7],
                        'status': row[7],  # 同时保留status字段以兼容旧代码
                        'cookie_id': row[8],
                        'is_bargain': bool(row[9]) if row[9] is not None else False,
                        'created_at': row[10],
                        'updated_at': row[11],
                        'version': row[12] if len(row) > 12 else 1,  # 默认版本为1
                        'chat_id': row[13] if len(row) > 13 else ''
                    }
                return None

            except Exception as e:
                logger.error(f"获取订单信息失败: {order_id} - {e}")
                return None



    def delete_order(self, order_id: str):
        """删除订单"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('DELETE FROM orders WHERE order_id = ?', (order_id,))
                if cursor.rowcount > 0:
                    self.conn.commit()
                    logger.info(f"删除订单成功: {order_id}")
                    return True
                return False
            except Exception as e:
                logger.error(f"删除订单失败: {order_id} - {e}")
                self.conn.rollback()
                return False



    def get_recent_order_by_item_and_buyer(self, item_id: str, buyer_id: str):
        """根据商品ID和买家ID获取最近的订单

        Args:
            item_id: 商品ID
            buyer_id: 买家ID

        Returns:
            dict: 订单信息，如果没有找到则返回None
        """
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                SELECT order_id, item_id, buyer_id, spec_name, spec_value,
                       quantity, amount, order_status, cookie_id, is_bargain, created_at, updated_at
                FROM orders
                WHERE item_id = ? AND buyer_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                ''', (item_id, buyer_id))

                row = cursor.fetchone()
                if row:
                    return {
                        'id': row[0],  # 使用 order_id 作为 id
                        'order_id': row[0],
                        'item_id': row[1],
                        'buyer_id': row[2],
                        'spec_name': row[3],
                        'spec_value': row[4],
                        'quantity': row[5],
                        'amount': row[6],
                        'order_status': row[7],
                        'cookie_id': row[8],
                        'is_bargain': bool(row[9]) if row[9] is not None else False,
                        'created_at': row[10],
                        'updated_at': row[11]
                    }
                return None

            except Exception as e:
                logger.error(f"获取订单信息失败: item_id={item_id}, buyer_id={buyer_id} - {e}")
                return None



    def get_orders_by_cookie(self, cookie_id: str, limit: int = 100):
        """根据Cookie ID获取订单列表"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                SELECT order_id, item_id, buyer_id, spec_name, spec_value,
                       quantity, amount, order_status, is_bargain, created_at, updated_at,
                       receiver_name, receiver_phone, receiver_address
                FROM orders WHERE cookie_id = ?
                ORDER BY created_at DESC LIMIT ?
                ''', (cookie_id, limit))

                orders = []
                for row in cursor.fetchall():
                    orders.append({
                        'id': row[0],  # 使用 order_id 作为 id
                        'order_id': row[0],
                        'item_id': row[1],
                        'buyer_id': row[2],
                        'spec_name': row[3],
                        'spec_value': row[4],
                        'quantity': row[5],
                        'amount': row[6],
                        'status': row[7],
                        'is_bargain': bool(row[8]) if row[8] is not None else False,
                        'created_at': row[9],
                        'updated_at': row[10],
                        'receiver_name': row[11],
                        'receiver_phone': row[12],
                        'receiver_address': row[13]
                    })

                return orders

            except Exception as e:
                logger.error(f"获取Cookie订单列表失败: {cookie_id} - {e}")
                return []



    def get_all_orders(self, limit: int = 1000):
        """获取所有订单列表"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                SELECT order_id, item_id, buyer_id, spec_name, spec_value,
                       quantity, amount, order_status, cookie_id, is_bargain, created_at, updated_at
                FROM orders
                ORDER BY created_at DESC LIMIT ?
                ''', (limit,))

                orders = []
                for row in cursor.fetchall():
                    orders.append({
                        'id': row[0],
                        'order_id': row[0],
                        'item_id': row[1],
                        'buyer_id': row[2],
                        'spec_name': row[3],
                        'spec_value': row[4],
                        'quantity': row[5],
                        'amount': row[6],
                        'status': row[7],
                        'cookie_id': row[8],
                        'is_bargain': bool(row[9]) if row[9] is not None else False,
                        'created_at': row[10],
                        'updated_at': row[11]
                    })

                return orders

            except Exception as e:
                logger.error(f"获取所有订单列表失败: {e}")
                return []



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



    def update_order_address(self, order_id: str, receiver_address: str = None, receiver_city: str = None):
        """
        更新订单的收货地址信息

        Args:
            order_id: 订单ID
            receiver_address: 收货地址
            receiver_city: 收货城市

        Returns:
            bool: 更新是否成功
        """
        with self.lock:
            try:
                cursor = self.conn.cursor()

                update_fields = []
                update_values = []

                if receiver_address is not None:
                    update_fields.append("receiver_address = ?")
                    update_values.append(receiver_address)

                if receiver_city is not None:
                    update_fields.append("receiver_city = ?")
                    update_values.append(receiver_city)

                if update_fields:
                    update_fields.append("updated_at = CURRENT_TIMESTAMP")
                    update_values.append(order_id)

                    sql = f"UPDATE orders SET {', '.join(update_fields)} WHERE order_id = ?"
                    cursor.execute(sql, update_values)
                    self.conn.commit()

                    return cursor.rowcount > 0

                return False

            except Exception as e:
                logger.error(f"更新订单地址失败: {order_id} - {e}")
                self.conn.rollback()
                return False



    def get_orders_for_analytics(self, start_date: str = None, end_date: str = None,
                                  user_id: int = None, include_statuses: list = None):
        """
        获取用于分析的订单列表

        Args:
            start_date: 开始日期
            end_date: 结束日期
            user_id: 用户ID
            include_statuses: 要包含的订单状态列表（如果指定则只返回这些状态的订单）

        Returns:
            订单列表
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

                # 只包含指定状态
                if include_statuses:
                    placeholders = ','.join(['?' for _ in include_statuses])
                    where_conditions.append(f"order_status IN ({placeholders})")
                    params.extend(include_statuses)

                where_clause = f"WHERE {' AND '.join(where_conditions)}" if where_conditions else ""

                cursor.execute(f"""
                    SELECT
                        order_id,
                        item_id,
                        buyer_id,
                        amount,
                        order_status,
                        spec_name,
                        spec_value,
                        quantity,
                        created_at,
                        receiver_city
                    FROM orders
                    {where_clause}
                    ORDER BY created_at DESC
                    LIMIT 1000
                """, params)

                orders = []
                for row in cursor.fetchall():
                    orders.append({
                        'order_id': row[0],
                        'item_id': row[1],
                        'buyer_id': row[2],
                        'amount': row[3],
                        'order_status': row[4],
                        'spec_name': row[5],
                        'spec_value': row[6],
                        'quantity': row[7],
                        'created_at': row[8],
                        'receiver_city': row[9]
                    })

                return orders

            except Exception as e:
                logger.error(f"获取订单列表失败: {e}")
                return []


    # ---- Session 持久化 ----
