"""
Backup Mixin - backup管理
"""
import sqlite3
import json
import time
import secrets
from typing import Optional, Dict, Any, List, Tuple
from loguru import logger


class BackupManagerMixin:
    """backup管理"""

    def export_backup(self, user_id: int = None) -> Dict[str, any]:
        """导出系统备份数据（支持用户隔离）"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                backup_data = {
                    'version': '1.0',
                    'timestamp': time.time(),
                    'user_id': user_id,
                    'data': {}
                }

                if user_id is not None:
                    # 用户级备份：只备份该用户的数据
                    # 备份用户的cookies
                    self._execute_sql(cursor, "SELECT * FROM cookies WHERE user_id = ?", (user_id,))
                    columns = [description[0] for description in cursor.description]
                    rows = cursor.fetchall()
                    backup_data['data']['cookies'] = {
                        'columns': columns,
                        'rows': [list(row) for row in rows]
                    }

                    # 备份用户cookies相关的其他数据
                    user_cookie_ids = [row[0] for row in rows]  # 获取用户的cookie_id列表

                    if user_cookie_ids:
                        placeholders = ','.join(['?' for _ in user_cookie_ids])

                        # 备份关键字
                        cursor.execute(f"SELECT * FROM keywords WHERE cookie_id IN ({placeholders})", user_cookie_ids)
                        columns = [description[0] for description in cursor.description]
                        rows = cursor.fetchall()
                        backup_data['data']['keywords'] = {
                            'columns': columns,
                            'rows': [list(row) for row in rows]
                        }

                        # 备份其他相关表
                        related_tables = ['cookie_status', 'default_replies', 'message_notifications',
                                        'item_info', 'ai_reply_settings', 'ai_conversations']

                        for table in related_tables:
                            cursor.execute(f"SELECT * FROM {table} WHERE cookie_id IN ({placeholders})", user_cookie_ids)
                            columns = [description[0] for description in cursor.description]
                            rows = cursor.fetchall()
                            backup_data['data'][table] = {
                                'columns': columns,
                                'rows': [list(row) for row in rows]
                            }
                else:
                    # 系统级备份：备份所有数据
                    tables = [
                        'cookies', 'keywords', 'cookie_status', 'cards',
                        'delivery_rules', 'default_replies', 'notification_channels',
                        'message_notifications', 'system_settings', 'item_info',
                        'ai_reply_settings', 'ai_conversations', 'ai_item_cache'
                    ]

                    for table in tables:
                        cursor.execute(f"SELECT * FROM {table}")
                        columns = [description[0] for description in cursor.description]
                        rows = cursor.fetchall()

                        backup_data['data'][table] = {
                            'columns': columns,
                            'rows': [list(row) for row in rows]
                        }

                logger.info(f"导出备份成功，用户ID: {user_id}")
                return backup_data

            except Exception as e:
                logger.error(f"导出备份失败: {e}")
                raise



    def import_backup(self, backup_data: Dict[str, any], user_id: int = None) -> bool:
        """导入系统备份数据（支持用户隔离）"""
        with self.lock:
            try:
                # 验证备份数据格式
                if not isinstance(backup_data, dict) or 'data' not in backup_data:
                    raise ValueError("备份数据格式无效")

                # 开始事务
                cursor = self.conn.cursor()
                self._execute_sql(cursor, "BEGIN TRANSACTION")

                if user_id is not None:
                    # 用户级导入：只清空该用户的数据
                    # 获取用户的cookie_id列表
                    self._execute_sql(cursor, "SELECT id FROM cookies WHERE user_id = ?", (user_id,))
                    user_cookie_ids = [row[0] for row in cursor.fetchall()]

                    if user_cookie_ids:
                        placeholders = ','.join(['?' for _ in user_cookie_ids])

                        # 删除用户相关数据
                        related_tables = ['message_notifications', 'default_replies', 'item_info',
                                        'cookie_status', 'keywords', 'ai_conversations', 'ai_reply_settings']

                        for table in related_tables:
                            cursor.execute(f"DELETE FROM {table} WHERE cookie_id IN ({placeholders})", user_cookie_ids)

                        # 删除用户的cookies
                        self._execute_sql(cursor, "DELETE FROM cookies WHERE user_id = ?", (user_id,))
                else:
                    # 系统级导入：清空所有数据（除了用户和管理员密码）
                    tables = [
                        'message_notifications', 'notification_channels', 'default_replies',
                        'delivery_rules', 'cards', 'item_info', 'cookie_status', 'keywords',
                        'ai_conversations', 'ai_reply_settings', 'ai_item_cache', 'cookies'
                    ]

                    for table in tables:
                        cursor.execute(f"DELETE FROM {table}")

                    # 清空系统设置（保留管理员密码）
                    self._execute_sql(cursor, "DELETE FROM system_settings WHERE key != 'admin_password_hash'")

                # 导入数据
                data = backup_data['data']
                for table_name, table_data in data.items():
                    if table_name not in ['cookies', 'keywords', 'cookie_status', 'cards',
                                        'delivery_rules', 'default_replies', 'notification_channels',
                                        'message_notifications', 'system_settings', 'item_info',
                                        'ai_reply_settings', 'ai_conversations', 'ai_item_cache']:
                        continue

                    columns = table_data['columns']
                    rows = table_data['rows']

                    if not rows:
                        continue

                    # 如果是用户级导入，需要确保cookies表的user_id正确
                    if user_id is not None and table_name == 'cookies':
                        # 更新所有导入的cookies的user_id
                        updated_rows = []
                        for row in rows:
                            row_dict = dict(zip(columns, row))
                            row_dict['user_id'] = user_id
                            updated_rows.append([row_dict[col] for col in columns])
                        rows = updated_rows

                    # 构建插入语句
                    placeholders = ','.join(['?' for _ in columns])

                    if table_name == 'system_settings':
                        # 系统设置需要特殊处理，避免覆盖管理员密码
                        for row in rows:
                            if len(row) >= 1 and row[0] != 'admin_password_hash':
                                cursor.execute(f"INSERT INTO {table_name} ({','.join(columns)}) VALUES ({placeholders})", row)
                    else:
                        cursor.executemany(f"INSERT INTO {table_name} ({','.join(columns)}) VALUES ({placeholders})", rows)

                # 提交事务
                self.conn.commit()
                logger.info("导入备份成功")
                return True

            except Exception as e:
                logger.error(f"导入备份失败: {e}")
                self.conn.rollback()
                return False

    # -------------------- 系统设置操作 --------------------
