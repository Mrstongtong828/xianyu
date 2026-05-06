# -*- coding: utf-8 -*-
"""
QUOTA DAO Mixin
"""

from loguru import logger
import sqlite3
import time
from typing import List, Tuple, Dict, Optional, Any


class QuotaDAOMixin:
    """QUOTA related database operations"""

    def get_daily_quota(self, cookie_id: str) -> dict:
        """获取当日操作计数"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                today = time.strftime('%Y-%m-%d')
                cursor.execute('''
                    SELECT auto_reply_count, auto_delivery_count
                    FROM daily_quota WHERE cookie_id = ? AND date = ?
                ''', (cookie_id, today))
                row = cursor.fetchone()
                if row:
                    return {'auto_reply_count': row[0], 'auto_delivery_count': row[1], 'date': today}
                return {'auto_reply_count': 0, 'auto_delivery_count': 0, 'date': today}
        except:
            return {'auto_reply_count': 0, 'auto_delivery_count': 0, 'date': today}

    def increment_daily_quota(self, cookie_id: str, quota_type: str) -> dict:
        """增加当日操作计数"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                today = time.strftime('%Y-%m-%d')
                field = 'auto_reply_count' if quota_type == 'reply' else 'auto_delivery_count'
                cursor.execute(f'''
                    INSERT INTO daily_quota (cookie_id, date, auto_reply_count, auto_delivery_count)
                    VALUES (?, ?, 0, 0)
                    ON CONFLICT(cookie_id, date) DO UPDATE SET
                        {field} = {field} + 1
                ''', (cookie_id, today))
                self.conn.commit()
                return self.get_daily_quota(cookie_id)
        except:
            return {'auto_reply_count': 0, 'auto_delivery_count': 0, 'date': today}

    def check_daily_quota(self, cookie_id: str, quota_type: str) -> tuple:
        """检查是否超出配额，返回(是否允许, 当前计数, 上限)"""
        config = self.get_quota_config()
        quota = self.get_daily_quota(cookie_id)

        if quota_type == 'reply':
            current = quota['auto_reply_count']
            limit = config['daily_reply_limit']
        else:
            current = quota['auto_delivery_count']
            limit = config['daily_delivery_limit']

        allowed = current < limit
        return (allowed, current, limit)



