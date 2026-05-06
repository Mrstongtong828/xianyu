# -*- coding: utf-8 -*-
"""
LOG DAO Mixin
"""

from loguru import logger
import sqlite3
import time
from typing import List, Tuple, Dict, Optional, Any


class LogDAOMixin:
    """LOG related database operations"""

    def get_operation_logs(self, cookie_id: str = None, log_type: str = None,
                           page: int = 1, page_size: int = 50) -> dict:
        """获取操作日志"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                conditions = []
                params = []
                if cookie_id:
                    conditions.append('cookie_id = ?')
                    params.append(cookie_id)
                if log_type:
                    conditions.append('event_type = ?')
                    params.append(log_type)

                where = ' WHERE ' + ' AND '.join(conditions) if conditions else ''

                cursor.execute(f'SELECT COUNT(*) FROM risk_control_logs {where}', params)
                total = cursor.fetchone()[0]

                offset = (page - 1) * page_size
                cursor.execute(f'''
                    SELECT * FROM risk_control_logs {where}
                    ORDER BY created_at DESC LIMIT ? OFFSET ?
                ''', params + [page_size, offset])
                rows = cursor.fetchall()
                columns = [d[0] for d in cursor.description]
                return {
                    'data': [dict(zip(columns, row)) for row in rows],
                    'total': total,
                    'page': page,
                    'page_size': page_size
                }
        except Exception as e:
            logger.error(f"获取操作日志失败: {e}")
            return {'data': [], 'total': 0, 'page': page, 'page_size': page_size}



