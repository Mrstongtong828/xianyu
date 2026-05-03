# -*- coding: utf-8 -*-
"""
DELIVERY DAO Mixin
"""

from loguru import logger
import sqlite3
import time
from typing import List, Tuple, Dict, Optional, Any


class DeliveryDAOMixin:
    """DELIVERY related database operations"""

    def add_delivery_retry(self, cookie_id: str, order_id: str = None, item_id: str = None,
                           buyer_id: str = None, buyer_name: str = '', chat_id: str = '',
                           quantity: int = 1, spec_name: str = '', spec_value: str = '',
                           error_type: str = 'no_match', error_message: str = '') -> int:
        """添加发货失败重试记录"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                    INSERT INTO delivery_retry_queue
                    (cookie_id, order_id, item_id, buyer_id, buyer_name, chat_id,
                     quantity, spec_name, spec_value, error_type, error_message, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                ''', (cookie_id, order_id, item_id, buyer_id, buyer_name, chat_id,
                      quantity, spec_name, spec_value, error_type, error_message))
                self.conn.commit()
                retry_id = cursor.lastrowid
                logger.info(f"发货失败已加入重试队列: id={retry_id}, order={order_id}, 买家={buyer_name}")
                return retry_id
        except Exception as e:
            logger.error(f"添加发货重试记录失败: {e}")
            return -1

    def get_pending_delivery_retries(self) -> list:
        """获取需要重试的发货记录"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                    SELECT * FROM delivery_retry_queue
                    WHERE status IN ('pending', 'retrying')
                    AND next_retry_at <= datetime('now', 'localtime')
                    ORDER BY created_at ASC
                ''')
                rows = cursor.fetchall()
                columns = [d[0] for d in cursor.description]
                return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            logger.error(f"获取待重试发货记录失败: {e}")
            return []

    def update_delivery_retry_status(self, retry_id: int, status: str, error_message: str = None,
                                      increment_retry: bool = True, delay_minutes: int = 5) -> bool:
        """更新发货重试状态"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                if increment_retry:
                    cursor.execute('''
                        UPDATE delivery_retry_queue
                        SET status = ?, error_message = COALESCE(?, error_message),
                            retry_count = retry_count + 1,
                            next_retry_at = datetime('now', 'localtime', ? || ' minutes'),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    ''', (status, error_message, f'+{delay_minutes}', retry_id))
                else:
                    cursor.execute('''
                        UPDATE delivery_retry_queue
                        SET status = ?, error_message = COALESCE(?, error_message),
                            next_retry_at = datetime('now', 'localtime', ? || ' minutes'),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    ''', (status, error_message, f'+{delay_minutes}', retry_id))
                self.conn.commit()
                logger.info(f"发货重试状态更新: id={retry_id}, status={status}")
                return True
        except Exception as e:
            logger.error(f"更新发货重试状态失败: {e}")
            return False

    def delete_delivery_retry(self, retry_id: int) -> bool:
        """删除发货重试记录"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute('DELETE FROM delivery_retry_queue WHERE id = ?', (retry_id,))
                self.conn.commit()
                return True
        except Exception as e:
            logger.error(f"删除发货重试记录失败: {e}")
            return False



