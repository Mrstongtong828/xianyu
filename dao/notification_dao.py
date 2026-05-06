# -*- coding: utf-8 -*-
"""
NOTIFICATION DAO Mixin
"""

from loguru import logger
import sqlite3
import time
from typing import List, Tuple, Dict, Optional, Any


class NotificationDAOMixin:
    """NOTIFICATION related database operations"""

    def create_notification_channel(self, name: str, channel_type: str, config: str, user_id: int = None) -> int:
        """创建通知渠道"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                INSERT INTO notification_channels (name, type, config, user_id)
                VALUES (?, ?, ?, ?)
                ''', (name, channel_type, config, user_id))
                self.conn.commit()
                channel_id = cursor.lastrowid
                logger.debug(f"创建通知渠道: {name} (ID: {channel_id})")
                return channel_id
            except Exception as e:
                logger.error(f"创建通知渠道失败: {e}")
                self.conn.rollback()
                raise

    def get_notification_channels(self, user_id: int = None) -> List[Dict[str, any]]:
        """获取所有通知渠道"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                if user_id is not None:
                    cursor.execute('''
                    SELECT id, name, type, config, enabled, created_at, updated_at
                    FROM notification_channels
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    ''', (user_id,))
                else:
                    cursor.execute('''
                    SELECT id, name, type, config, enabled, created_at, updated_at
                    FROM notification_channels
                    ORDER BY created_at DESC
                    ''')

                channels = []
                for row in cursor.fetchall():
                    channels.append({
                        'id': row[0],
                        'name': row[1],
                        'type': row[2],
                        'config': row[3],
                        'enabled': bool(row[4]),
                        'created_at': row[5],
                        'updated_at': row[6]
                    })

                return channels
            except Exception as e:
                logger.error(f"获取通知渠道失败: {e}")
                return []

    def get_notification_channel(self, channel_id: int) -> Optional[Dict[str, any]]:
        """获取指定通知渠道"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                SELECT id, name, type, config, enabled, created_at, updated_at
                FROM notification_channels WHERE id = ?
                ''', (channel_id,))

                row = cursor.fetchone()
                if row:
                    return {
                        'id': row[0],
                        'name': row[1],
                        'type': row[2],
                        'config': row[3],
                        'enabled': bool(row[4]),
                        'created_at': row[5],
                        'updated_at': row[6]
                    }
                return None
            except Exception as e:
                logger.error(f"获取通知渠道失败: {e}")
                return None

    def update_notification_channel(self, channel_id: int, name: str, config: str, enabled: bool = True) -> bool:
        """更新通知渠道"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                UPDATE notification_channels
                SET name = ?, config = ?, enabled = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                ''', (name, config, enabled, channel_id))
                self.conn.commit()
                logger.debug(f"更新通知渠道: {channel_id}")
                return cursor.rowcount > 0
            except Exception as e:
                logger.error(f"更新通知渠道失败: {e}")
                self.conn.rollback()
                return False

    def delete_notification_channel(self, channel_id: int) -> bool:
        """删除通知渠道"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                self._execute_sql(cursor, "DELETE FROM notification_channels WHERE id = ?", (channel_id,))
                self.conn.commit()
                logger.debug(f"删除通知渠道: {channel_id}")
                return cursor.rowcount > 0
            except Exception as e:
                logger.error(f"删除通知渠道失败: {e}")
                self.conn.rollback()
                return False

    # -------------------- 消息通知配置操作 --------------------
    def set_message_notification(self, cookie_id: str, channel_id: int, enabled: bool = True) -> bool:
        """设置账号的消息通知"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                INSERT OR REPLACE INTO message_notifications (cookie_id, channel_id, enabled)
                VALUES (?, ?, ?)
                ''', (cookie_id, channel_id, enabled))
                self.conn.commit()
                logger.debug(f"设置消息通知: {cookie_id} -> {channel_id}")
                return True
            except Exception as e:
                logger.error(f"设置消息通知失败: {e}")
                self.conn.rollback()
                return False

    def get_account_notifications(self, cookie_id: str) -> List[Dict[str, any]]:
        """获取账号的通知配置"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                SELECT mn.id, mn.channel_id, mn.enabled, nc.name, nc.type, nc.config
                FROM message_notifications mn
                JOIN notification_channels nc ON mn.channel_id = nc.id
                WHERE mn.cookie_id = ? AND nc.enabled = 1
                ORDER BY mn.id
                ''', (cookie_id,))

                notifications = []
                for row in cursor.fetchall():
                    notifications.append({
                        'id': row[0],
                        'channel_id': row[1],
                        'enabled': bool(row[2]),
                        'channel_name': row[3],
                        'channel_type': row[4],
                        'channel_config': row[5]
                    })

                return notifications
            except Exception as e:
                logger.error(f"获取账号通知配置失败: {e}")
                return []

    def get_all_message_notifications(self) -> Dict[str, List[Dict[str, any]]]:
        """获取所有账号的通知配置"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                SELECT mn.cookie_id, mn.id, mn.channel_id, mn.enabled, nc.name, nc.type, nc.config
                FROM message_notifications mn
                JOIN notification_channels nc ON mn.channel_id = nc.id
                WHERE nc.enabled = 1
                ORDER BY mn.cookie_id, mn.id
                ''')

                result = {}
                for row in cursor.fetchall():
                    cookie_id = row[0]
                    if cookie_id not in result:
                        result[cookie_id] = []

                    result[cookie_id].append({
                        'id': row[1],
                        'channel_id': row[2],
                        'enabled': bool(row[3]),
                        'channel_name': row[4],
                        'channel_type': row[5],
                        'channel_config': row[6]
                    })

                return result
            except Exception as e:
                logger.error(f"获取所有消息通知配置失败: {e}")
                return {}

    def delete_message_notification(self, notification_id: int) -> bool:
        """删除消息通知配置"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                self._execute_sql(cursor, "DELETE FROM message_notifications WHERE id = ?", (notification_id,))
                self.conn.commit()
                logger.debug(f"删除消息通知配置: {notification_id}")
                return cursor.rowcount > 0
            except Exception as e:
                logger.error(f"删除消息通知配置失败: {e}")
                self.conn.rollback()
                return False

    def delete_account_notifications(self, cookie_id: str) -> bool:
        """删除账号的所有消息通知配置"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                self._execute_sql(cursor, "DELETE FROM message_notifications WHERE cookie_id = ?", (cookie_id,))
                self.conn.commit()
                logger.debug(f"删除账号通知配置: {cookie_id}")
                return cursor.rowcount > 0
            except Exception as e:
                logger.error(f"删除账号通知配置失败: {e}")
                self.conn.rollback()
                return False

    # -------------------- 备份和恢复操作 --------------------


