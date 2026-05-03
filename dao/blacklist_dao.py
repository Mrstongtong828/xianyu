# -*- coding: utf-8 -*-
"""
BLACKLIST DAO Mixin
"""

from loguru import logger
import sqlite3
import time
from typing import List, Tuple, Dict, Optional, Any


class BlacklistDAOMixin:
    """BLACKLIST related database operations"""

    def get_blacklist(self, user_id: int = None, page: int = 1, page_size: int = 50) -> dict:
        """获取黑名单列表"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                where = ''
                params = []
                if user_id:
                    where = 'WHERE user_id = ?'
                    params.append(user_id)

                cursor.execute(f'SELECT COUNT(*) FROM buyer_blacklist {where}', params)
                total = cursor.fetchone()[0]

                offset = (page - 1) * page_size
                cursor.execute(f'''
                    SELECT * FROM buyer_blacklist {where}
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
            logger.error(f"获取黑名单失败: {e}")
            return {'data': [], 'total': 0, 'page': page, 'page_size': page_size}



