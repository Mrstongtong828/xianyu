"""
Notification Mixin - 通知渠道和消息通知管理
"""
import sqlite3
import json
import time
import secrets
from typing import Optional, Dict, Any, List, Tuple
from loguru import logger


class NotificationManagerMixin:
    """通知渠道和消息通知管理"""

    def upgrade_notification_channels_table(self, cursor):
        """升级notification_channels表的type字段约束"""
        try:
            logger.info("开始升级notification_channels表...")
            
            # 检查表是否存在
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='notification_channels'")
            if not cursor.fetchone():
                logger.info("notification_channels表不存在，无需升级")
                return True
                
            # 检查表中是否有数据
            cursor.execute("SELECT COUNT(*) FROM notification_channels")
            count = cursor.fetchone()[0]

            # 删除可能存在的临时表
            cursor.execute("DROP TABLE IF EXISTS notification_channels_new")

            # 创建临时表
            cursor.execute('''
            CREATE TABLE notification_channels_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                type TEXT NOT NULL CHECK (type IN ('qq','ding_talk')),
                config TEXT NOT NULL,
                enabled BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            # 复制数据，并转换不兼容的类型
            if count > 0:
                logger.info(f"复制 {count} 条通知渠道数据到新表")
                # 先查看现有数据的类型
                cursor.execute("SELECT DISTINCT type FROM notification_channels")
                existing_types = [row[0] for row in cursor.fetchall()]
                logger.info(f"现有通知渠道类型: {existing_types}")

                # 获取所有现有数据进行逐行处理
                cursor.execute("SELECT * FROM notification_channels")
                existing_data = cursor.fetchall()

                # 逐行转移数据，确保类型映射正确
                for row in existing_data:
                    old_type = row[3] if len(row) > 3 else 'qq'  # type字段，默认为qq

                    # 类型映射规则
                    type_mapping = {
                        'dingtalk': 'ding_talk',
                        'ding_talk': 'ding_talk',
                        'qq': 'qq',
                        'email': 'qq',  # 暂时映射为qq，后续版本会支持
                        'webhook': 'qq',  # 暂时映射为qq，后续版本会支持
                        'wechat': 'qq',  # 暂时映射为qq，后续版本会支持
                        'telegram': 'qq'  # 暂时映射为qq，后续版本会支持
                    }

                    new_type = type_mapping.get(old_type, 'qq')  # 默认转换为qq类型

                    if old_type != new_type:
                        logger.info(f"转换通知渠道类型: {old_type} -> {new_type}")

                    # 插入到新表
                    cursor.execute('''
                    INSERT INTO notification_channels_new
                    (id, name, user_id, type, config, enabled, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        row[0],  # id
                        row[1],  # name
                        row[2],  # user_id
                        new_type,  # type (转换后的)
                        row[4] if len(row) > 4 else '{}',  # config
                        row[5] if len(row) > 5 else True,  # enabled
                        row[6] if len(row) > 6 else None,  # created_at
                        row[7] if len(row) > 7 else None   # updated_at
                    ))
            
            # 删除旧表
            cursor.execute("DROP TABLE notification_channels")
            
            # 重命名新表
            cursor.execute("ALTER TABLE notification_channels_new RENAME TO notification_channels")
            
            logger.info("notification_channels表升级完成")
            return True
        except Exception as e:
            logger.error(f"升级notification_channels表失败: {e}")
            raise



    def upgrade_notification_channels_types(self, cursor):
        """升级notification_channels表支持更多渠道类型"""
        try:
            logger.info("开始升级notification_channels表支持更多渠道类型...")

            # 检查表是否存在
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='notification_channels'")
            if not cursor.fetchone():
                logger.info("notification_channels表不存在，无需升级")
                return True

            # 检查表中是否有数据
            cursor.execute("SELECT COUNT(*) FROM notification_channels")
            count = cursor.fetchone()[0]

            # 获取现有数据
            existing_data = []
            if count > 0:
                cursor.execute("SELECT * FROM notification_channels")
                existing_data = cursor.fetchall()
                logger.info(f"备份 {count} 条通知渠道数据")

            # 创建新表，支持所有通知渠道类型
            cursor.execute('''
            CREATE TABLE notification_channels_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                type TEXT NOT NULL CHECK (type IN ('qq','ding_talk','dingtalk','feishu','lark','bark','email','webhook','wechat','telegram')),
                config TEXT NOT NULL,
                enabled BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')

            # 复制数据，同时处理类型映射
            if existing_data:
                logger.info(f"迁移 {len(existing_data)} 条通知渠道数据到新表")
                for row in existing_data:
                    # 处理类型映射，支持更多渠道类型
                    old_type = row[3] if len(row) > 3 else 'qq'  # type字段

                    # 完整的类型映射规则，支持所有通知渠道
                    type_mapping = {
                        'ding_talk': 'dingtalk',  # 统一为dingtalk
                        'dingtalk': 'dingtalk',
                        'qq': 'qq',
                        'feishu': 'feishu',      # 飞书通知
                        'lark': 'lark',          # 飞书通知（英文名）
                        'bark': 'bark',          # Bark通知
                        'email': 'email',        # 邮件通知
                        'webhook': 'webhook',    # Webhook通知
                        'wechat': 'wechat',      # 微信通知
                        'telegram': 'telegram'   # Telegram通知
                    }

                    new_type = type_mapping.get(old_type, 'qq')  # 默认为qq

                    if old_type != new_type:
                        logger.info(f"转换通知渠道类型: {old_type} -> {new_type}")

                    # 插入到新表，确保字段完整性
                    cursor.execute('''
                    INSERT INTO notification_channels_new
                    (id, name, user_id, type, config, enabled, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        row[0],  # id
                        row[1],  # name
                        row[2],  # user_id
                        new_type,  # type (转换后的)
                        row[4] if len(row) > 4 else '{}',  # config
                        row[5] if len(row) > 5 else True,  # enabled
                        row[6] if len(row) > 6 else None,  # created_at
                        row[7] if len(row) > 7 else None   # updated_at
                    ))

            # 删除旧表
            cursor.execute("DROP TABLE notification_channels")

            # 重命名新表
            cursor.execute("ALTER TABLE notification_channels_new RENAME TO notification_channels")

            logger.info("notification_channels表类型升级完成")
            logger.info("✅ 现在支持以下所有通知渠道类型:")
            logger.info("   - qq (QQ通知)")
            logger.info("   - ding_talk/dingtalk (钉钉通知)")
            logger.info("   - feishu/lark (飞书通知)")
            logger.info("   - bark (Bark通知)")
            logger.info("   - email (邮件通知)")
            logger.info("   - webhook (Webhook通知)")
            logger.info("   - wechat (微信通知)")
            logger.info("   - telegram (Telegram通知)")
            return True
        except Exception as e:
            logger.error(f"升级notification_channels表类型失败: {e}")
            raise



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
