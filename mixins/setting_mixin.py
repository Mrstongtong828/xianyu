"""
Setting Mixin - 系统设置和 AI 回复配置管理
"""
import sqlite3
import json
import time
import secrets
from typing import Optional, Dict, Any, List, Tuple
from loguru import logger


class SettingManagerMixin:
    """系统设置和 AI 回复配置管理"""

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


    def get_system_setting(self, key: str) -> Optional[str]:
        """获取系统设置"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                self._execute_sql(cursor, "SELECT value FROM system_settings WHERE key = ?", (key,))
                result = cursor.fetchone()
                return result[0] if result else None
            except Exception as e:
                logger.error(f"获取系统设置失败: {e}")
                return None



    def set_system_setting(self, key: str, value: str, description: str = None) -> bool:
        """设置系统设置"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                INSERT OR REPLACE INTO system_settings (key, value, description, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ''', (key, value, description))
                self.conn.commit()
                logger.debug(f"设置系统设置: {key}")
                return True
            except Exception as e:
                logger.error(f"设置系统设置失败: {e}")
                self.conn.rollback()
                return False



    def get_all_system_settings(self) -> Dict[str, str]:
        """获取所有系统设置"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                self._execute_sql(cursor, "SELECT key, value FROM system_settings")

                settings = {}
                for row in cursor.fetchall():
                    settings[row[0]] = row[1]

                return settings
            except Exception as e:
                logger.error(f"获取所有系统设置失败: {e}")
                return {}

    # 管理员密码现在统一使用用户表管理，不再需要单独的方法

    # ==================== 用户管理方法 ====================



    def get_evaluation_config(self, cookie_id: str) -> dict:
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM evaluation_config WHERE cookie_id = ?', (cookie_id,))
            row = cursor.fetchone()
            if row:
                columns = [d[0] for d in cursor.description]
                return dict(zip(columns, row))
            return {'auto_evaluate_enabled': False, 'evaluate_content': '感谢您的购买，欢迎再次光临！', 'auto_reply_review_enabled': False, 'reply_review_content': '感谢支持！'}



    def update_evaluation_config(self, cookie_id: str, data: dict) -> bool:
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO evaluation_config (cookie_id, auto_evaluate_enabled, evaluate_content, auto_reply_review_enabled, reply_review_content)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(cookie_id) DO UPDATE SET
                    auto_evaluate_enabled = excluded.auto_evaluate_enabled,
                    evaluate_content = excluded.evaluate_content,
                    auto_reply_review_enabled = excluded.auto_reply_review_enabled,
                    reply_review_content = excluded.reply_review_content,
                    updated_at = CURRENT_TIMESTAMP
            ''', (cookie_id, data.get('auto_evaluate_enabled', False), data.get('evaluate_content', ''),
                  data.get('auto_reply_review_enabled', False), data.get('reply_review_content', '')))
            self.conn.commit()
            return True



    def get_quota_config(self) -> dict:
        """获取配额配置"""
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT value FROM system_settings WHERE key = 'daily_reply_limit'")
            reply_limit = cursor.fetchone()
            cursor.execute("SELECT value FROM system_settings WHERE key = 'daily_delivery_limit'")
            delivery_limit = cursor.fetchone()
            return {
                'daily_reply_limit': int(reply_limit[0]) if reply_limit else 200,
                'daily_delivery_limit': int(delivery_limit[0]) if delivery_limit else 100
            }

