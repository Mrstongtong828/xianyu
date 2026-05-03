"""
Blacklist Mixin - blacklist管理
"""
import sqlite3
import json
import time
import secrets
from typing import Optional, Dict, Any, List, Tuple
from loguru import logger


class BlacklistManagerMixin:
    """blacklist管理"""

    def add_to_blacklist(self, user_id: int, buyer_id: str, buyer_name: str = '', reason: str = '') -> bool:
        """添加买家到黑名单"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO buyer_blacklist (user_id, buyer_id, buyer_name, reason)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, buyer_id, buyer_name, reason))
                self.conn.commit()
                logger.info(f"买家已加入黑名单: user_id={user_id}, buyer_id={buyer_id}")
                return True
        except Exception as e:
            logger.error(f"添加黑名单失败: {e}")
            return False



    def remove_from_blacklist(self, blacklist_id: int) -> bool:
        """从黑名单移除"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute('DELETE FROM buyer_blacklist WHERE id = ?', (blacklist_id,))
                self.conn.commit()
                return True
        except Exception as e:
            logger.error(f"移除黑名单失败: {e}")
            return False



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



    def is_buyer_blacklisted(self, user_id: int, buyer_id: str) -> bool:
        """检查买家是否在黑名单中"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute(
                    'SELECT COUNT(*) FROM buyer_blacklist WHERE user_id = ? AND buyer_id = ?',
                    (user_id, buyer_id)
                )
                return cursor.fetchone()[0] > 0
        except Exception as e:
            logger.error(f"检查黑名单失败: {e}")
            return False

