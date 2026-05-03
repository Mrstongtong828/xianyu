# -*- coding: utf-8 -*-
"""
OUTREACH DAO Mixin
"""

from loguru import logger
import sqlite3
import time
from typing import List, Tuple, Dict, Optional, Any


class OutreachDAOMixin:
    """OUTREACH related database operations"""

    def add_active_outreach(self, cookie_id: str, item_url: str, message: str = '',
                             item_title: str = '', seller_id: str = '',
                             seller_name: str = '', chat_id: str = '') -> int:
        """添加主动询价记录"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                    INSERT INTO active_outreach (cookie_id, item_url, item_title, seller_id,
                        seller_name, chat_id, message, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
                ''', (cookie_id, item_url, item_title, seller_id, seller_name, chat_id, message))
                self.conn.commit()
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"添加主动询价记录失败: {e}")
            return -1

    def update_active_outreach_status(self, record_id: int, status: str, reply: str = '',
                                       error_message: str = ''):
        """更新主动询价记录状态"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                fields = ['status = ?']
                values = [status]
                if reply:
                    fields.append('reply = ?')
                    values.append(reply)
                if error_message:
                    fields.append('error_message = ?')
                    values.append(error_message)
                fields.append('updated_at = CURRENT_TIMESTAMP')
                values.append(record_id)
                cursor.execute(f'''
                    UPDATE active_outreach SET {', '.join(fields)}
                    WHERE id = ?
                ''', values)
                self.conn.commit()
        except Exception as e:
            logger.error(f"更新主动询价记录失败: {e}")



