# -*- coding: utf-8 -*-
"""
AI DAO Mixin
"""

from loguru import logger
import sqlite3
import time
from typing import List, Tuple, Dict, Optional, Any


class AiDAOMixin:
    """AI related database operations"""

    def save_ai_reply_settings(self, cookie_id: str, settings: dict) -> bool:
        """保存AI回复设置"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                INSERT OR REPLACE INTO ai_reply_settings
                (cookie_id, ai_enabled, model_name, api_key, base_url,
                 max_discount_percent, max_discount_amount, max_bargain_rounds,
                 custom_prompts, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (
                    cookie_id,
                    settings.get('ai_enabled', False),
                    settings.get('model_name', 'qwen-plus'),
                    settings.get('api_key', ''),
                    settings.get('base_url', 'https://dashscope.aliyuncs.com/compatible-mode/v1'),
                    settings.get('max_discount_percent', 10),
                    settings.get('max_discount_amount', 100),
                    settings.get('max_bargain_rounds', 3),
                    settings.get('custom_prompts', '')
                ))
                self.conn.commit()
                logger.debug(f"AI回复设置保存成功: {cookie_id}")
                return True
            except Exception as e:
                logger.error(f"保存AI回复设置失败: {e}")
                self.conn.rollback()
                return False

    def get_ai_reply_settings(self, cookie_id: str) -> dict:
        """获取AI回复设置
        
        优先使用账号级别的设置，如果账号没有配置api_key/base_url/model_name，
        则从系统设置中读取全局AI配置作为默认值
        """
        # 默认值常量，用于判断是否使用系统设置
        DEFAULT_BASE_URL = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
        DEFAULT_MODEL = 'qwen-plus'
        
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                SELECT ai_enabled, model_name, api_key, base_url,
                       max_discount_percent, max_discount_amount, max_bargain_rounds,
                       custom_prompts
                FROM ai_reply_settings WHERE cookie_id = ?
                ''', (cookie_id,))

                result = cursor.fetchone()
                
                # 获取系统级别的AI设置作为默认值
                system_api_key = self.get_system_setting('ai_api_key') or ''
                system_base_url = self.get_system_setting('ai_api_url') or DEFAULT_BASE_URL
                system_model = self.get_system_setting('ai_model') or DEFAULT_MODEL
                
                if result:
                    # 账号有设置，但如果api_key/base_url/model_name为空或等于默认值，使用系统设置
                    account_model = result[1]
                    account_api_key = result[2]
                    account_base_url = result[3]
                    
                    # 如果账号值为空或等于硬编码默认值，则使用系统设置
                    use_model = account_model if (account_model and account_model != DEFAULT_MODEL) else system_model
                    use_api_key = account_api_key if account_api_key else system_api_key
                    use_base_url = account_base_url if (account_base_url and account_base_url != DEFAULT_BASE_URL) else system_base_url
                    
                    return {
                        'ai_enabled': bool(result[0]),
                        'model_name': use_model,
                        'api_key': use_api_key,
                        'base_url': use_base_url,
                        'max_discount_percent': result[4],
                        'max_discount_amount': result[5],
                        'max_bargain_rounds': result[6],
                        'custom_prompts': result[7]
                    }
                else:
                    # 账号没有设置，使用系统设置作为默认值
                    return {
                        'ai_enabled': False,
                        'model_name': system_model,
                        'api_key': system_api_key,
                        'base_url': system_base_url,
                        'max_discount_percent': 10,
                        'max_discount_amount': 100,
                        'max_bargain_rounds': 3,
                        'custom_prompts': ''
                    }
            except Exception as e:
                logger.error(f"获取AI回复设置失败: {e}")
                return {
                    'ai_enabled': False,
                    'model_name': 'qwen-plus',
                    'api_key': '',
                    'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
                    'max_discount_percent': 10,
                    'max_discount_amount': 100,
                    'max_bargain_rounds': 3,
                    'custom_prompts': ''
                }

    def get_all_ai_reply_settings(self) -> Dict[str, dict]:
        """获取所有账号的AI回复设置"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                SELECT cookie_id, ai_enabled, model_name, api_key, base_url,
                       max_discount_percent, max_discount_amount, max_bargain_rounds,
                       custom_prompts
                FROM ai_reply_settings
                ''')

                result = {}
                for row in cursor.fetchall():
                    cookie_id = row[0]
                    result[cookie_id] = {
                        'ai_enabled': bool(row[1]),
                        'model_name': row[2],
                        'api_key': row[3],
                        'base_url': row[4],
                        'max_discount_percent': row[5],
                        'max_discount_amount': row[6],
                        'max_bargain_rounds': row[7],
                        'custom_prompts': row[8]
                    }

                return result
            except Exception as e:
                logger.error(f"获取所有AI回复设置失败: {e}")
                return {}

    # -------------------- 默认回复操作 --------------------
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

    def get_all_default_replies(self) -> Dict[str, Dict[str, any]]:
        """获取所有账号的默认回复设置"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('SELECT cookie_id, enabled, reply_content, reply_once, reply_image_url FROM default_replies')

                result = {}
                for row in cursor.fetchall():
                    cookie_id, enabled, reply_content, reply_once, reply_image_url = row
                    result[cookie_id] = {
                        'enabled': bool(enabled),
                        'reply_content': reply_content or '',
                        'reply_once': bool(reply_once) if reply_once is not None else False,
                        'reply_image_url': reply_image_url or ''
                    }

                return result
            except Exception as e:
                logger.error(f"获取所有默认回复设置失败: {e}")
                return {}

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

    def find_chat_id_by_buyer(self, cookie_id: str, buyer_id: str) -> str:
        """根据买家ID查找最近的chat_id（从AI对话记录中查找）"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                    SELECT chat_id FROM ai_conversations
                    WHERE cookie_id = ? AND user_id = ?
                    AND chat_id IS NOT NULL AND chat_id != ''
                    ORDER BY id DESC LIMIT 1
                ''', (cookie_id, buyer_id))
                row = cursor.fetchone()
                if row:
                    return row[0]
                return None
            except Exception as e:
                logger.error(f"查找chat_id失败: {e}")
                return None

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


