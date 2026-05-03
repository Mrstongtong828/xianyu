# -*- coding: utf-8 -*-
"""
ITEM DAO Mixin
"""

from loguru import logger
import sqlite3
import time
from typing import List, Tuple, Dict, Optional, Any


class ItemDAOMixin:
    """ITEM related database operations"""

    def get_items_by_cookie(self, cookie_id: str) -> List[Dict]:
        """获取指定Cookie的所有商品信息

        Args:
            cookie_id: Cookie ID

        Returns:
            List[Dict]: 商品信息列表
        """
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                SELECT * FROM item_info
                WHERE cookie_id = ?
                ORDER BY updated_at DESC
                ''', (cookie_id,))

                columns = [description[0] for description in cursor.description]
                items = []

                for row in cursor.fetchall():
                    item_info = dict(zip(columns, row))

                    if item_info.get('item_detail'):
                        try:
                            item_info['item_detail_parsed'] = json.loads(item_info['item_detail'])
                        except:
                            item_info['item_detail_parsed'] = {}

                    items.append(item_info)

                return items

        except Exception as e:
            logger.error(f"获取Cookie商品信息失败: {e}")
            return []

    def get_item_schedules(self, cookie_id: str = None, schedule_type: str = None) -> list:
        with self.lock:
            cursor = self.conn.cursor()
            conditions = []
            params = []
            if cookie_id:
                conditions.append('cookie_id = ?')
                params.append(cookie_id)
            if schedule_type:
                conditions.append('schedule_type = ?')
                params.append(schedule_type)
            where = ' WHERE ' + ' AND '.join(conditions) if conditions else ''
            cursor.execute(f'SELECT * FROM item_schedule {where} ORDER BY created_at DESC', params)
            rows = cursor.fetchall()
            columns = [d[0] for d in cursor.description]
            return [dict(zip(columns, row)) for row in rows]

    def delete_item_schedule(self, schedule_id: int) -> bool:
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute('DELETE FROM item_schedule WHERE id = ?', (schedule_id,))
            self.conn.commit()
            return True



