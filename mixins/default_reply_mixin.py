"""
Default_Reply Mixin - 默认回复管理
"""
import sqlite3
import json
import time
import secrets
from typing import Optional, Dict, Any, List, Tuple
from loguru import logger


class DefaultReplyManagerMixin:
    """默认回复管理"""

    def save_default_reply(self, cookie_id: str, enabled: bool, reply_content: str = None, reply_once: bool = False, reply_image_url: str = None):
        """保存默认回复设置"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                INSERT OR REPLACE INTO default_replies (cookie_id, enabled, reply_content, reply_image_url, reply_once, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (cookie_id, enabled, reply_content, reply_image_url, reply_once))
                self.conn.commit()
                logger.debug(f"保存默认回复设置: {cookie_id} -> {'启用' if enabled else '禁用'}, 只回复一次: {'是' if reply_once else '否'}, 图片: {reply_image_url}")
            except Exception as e:
                logger.error(f"保存默认回复设置失败: {e}")
                raise



    def get_default_reply(self, cookie_id: str) -> Optional[Dict[str, any]]:
        """获取指定账号的默认回复设置"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                SELECT enabled, reply_content, reply_once, reply_image_url FROM default_replies WHERE cookie_id = ?
                ''', (cookie_id,))
                result = cursor.fetchone()
                if result:
                    enabled, reply_content, reply_once, reply_image_url = result
                    return {
                        'enabled': bool(enabled),
                        'reply_content': reply_content or '',
                        'reply_once': bool(reply_once) if reply_once is not None else False,
                        'reply_image_url': reply_image_url or ''
                    }
                return None
            except Exception as e:
                logger.error(f"获取默认回复设置失败: {e}")
                return None



    def add_default_reply_record(self, cookie_id: str, chat_id: str):
        """记录已回复的chat_id"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                INSERT OR IGNORE INTO default_reply_records (cookie_id, chat_id)
                VALUES (?, ?)
                ''', (cookie_id, chat_id))
                self.conn.commit()
                logger.debug(f"记录默认回复: {cookie_id} -> {chat_id}")
            except Exception as e:
                logger.error(f"记录默认回复失败: {e}")



    def has_default_reply_record(self, cookie_id: str, chat_id: str) -> bool:
        """检查是否已经回复过该chat_id"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                SELECT 1 FROM default_reply_records WHERE cookie_id = ? AND chat_id = ?
                ''', (cookie_id, chat_id))
                result = cursor.fetchone()
                return result is not None
            except Exception as e:
                logger.error(f"检查默认回复记录失败: {e}")
                return False



    def clear_default_reply_records(self, cookie_id: str):
        """清空指定账号的默认回复记录"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('DELETE FROM default_reply_records WHERE cookie_id = ?', (cookie_id,))
                self.conn.commit()
                logger.debug(f"清空默认回复记录: {cookie_id}")
            except Exception as e:
                logger.error(f"清空默认回复记录失败: {e}")



    def delete_default_reply(self, cookie_id: str) -> bool:
        """删除指定账号的默认回复设置"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                self._execute_sql(cursor, "DELETE FROM default_replies WHERE cookie_id = ?", (cookie_id,))
                self.conn.commit()
                logger.debug(f"删除默认回复设置: {cookie_id}")
                return True
            except Exception as e:
                logger.error(f"删除默认回复设置失败: {e}")
                self.conn.rollback()
                return False



    def update_default_reply_image_url(self, cookie_id: str, new_image_url: str) -> bool:
        """更新默认回复的图片URL（用于将本地图片URL更新为CDN URL）"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                UPDATE default_replies SET reply_image_url = ? WHERE cookie_id = ?
                ''', (new_image_url, cookie_id))
                self.conn.commit()
                logger.debug(f"更新默认回复图片URL: {cookie_id} -> {new_image_url}")
                return True
            except Exception as e:
                logger.error(f"更新默认回复图片URL失败: {e}")
                self.conn.rollback()
                return False

    # -------------------- 通知渠道操作 --------------------
