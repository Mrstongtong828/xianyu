# -*- coding: utf-8 -*-
"""
ORDER DAO Mixin
"""

from loguru import logger
import sqlite3
import time
from typing import List, Tuple, Dict, Optional, Any


class OrderDAOMixin:
    """ORDER related database operations"""

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



