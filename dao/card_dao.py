# -*- coding: utf-8 -*-
"""
CARD DAO Mixin
"""

from loguru import logger
import sqlite3
import time
from typing import List, Tuple, Dict, Optional, Any


class CardDAOMixin:
    """CARD related database operations"""

    def get_all_cards(self, user_id: int = None):
        """获取所有卡券（支持用户隔离）"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                if user_id is not None:
                    cursor.execute('''
                    SELECT id, name, type, api_config, text_content, data_content, image_url,
                           description, enabled, delay_seconds, is_multi_spec,
                           spec_name, spec_value, created_at, updated_at
                    FROM cards
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    ''', (user_id,))
                else:
                    cursor.execute('''
                    SELECT id, name, type, api_config, text_content, data_content, image_url,
                           description, enabled, delay_seconds, is_multi_spec,
                           spec_name, spec_value, created_at, updated_at
                    FROM cards
                    ORDER BY created_at DESC
                    ''')

                cards = []
                for row in cursor.fetchall():
                    # 解析api_config JSON字符串
                    api_config = row[3]
                    if api_config:
                        try:
                            import json
                            api_config = json.loads(api_config)
                        except (json.JSONDecodeError, TypeError):
                            # 如果解析失败，保持原始字符串
                            pass

                    cards.append({
                        'id': row[0],
                        'name': row[1],
                        'type': row[2],
                        'api_config': api_config,
                        'text_content': row[4],
                        'data_content': row[5],
                        'image_url': row[6],
                        'description': row[7],
                        'enabled': bool(row[8]),
                        'delay_seconds': row[9] or 0,
                        'is_multi_spec': bool(row[10]) if row[10] is not None else False,
                        'spec_name': row[11],
                        'spec_value': row[12],
                        'created_at': row[13],
                        'updated_at': row[14]
                    })

                return cards
            except Exception as e:
                logger.error(f"获取卡券列表失败: {e}")
                return []

    def get_card_by_id(self, card_id: int, user_id: int = None):
        """根据ID获取卡券（支持用户隔离）"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                if user_id is not None:
                    cursor.execute('''
                    SELECT id, name, type, api_config, text_content, data_content, image_url,
                           description, enabled, delay_seconds, is_multi_spec,
                           spec_name, spec_value, created_at, updated_at
                    FROM cards WHERE id = ? AND user_id = ?
                    ''', (card_id, user_id))
                else:
                    cursor.execute('''
                    SELECT id, name, type, api_config, text_content, data_content, image_url,
                           description, enabled, delay_seconds, is_multi_spec,
                           spec_name, spec_value, created_at, updated_at
                    FROM cards WHERE id = ?
                    ''', (card_id,))

                row = cursor.fetchone()
                if row:
                    # 解析api_config JSON字符串
                    api_config = row[3]
                    if api_config:
                        try:
                            import json
                            api_config = json.loads(api_config)
                        except (json.JSONDecodeError, TypeError):
                            # 如果解析失败，保持原始字符串
                            pass

                    return {
                        'id': row[0],
                        'name': row[1],
                        'type': row[2],
                        'api_config': api_config,
                        'text_content': row[4],
                        'data_content': row[5],
                        'image_url': row[6],
                        'description': row[7],
                        'enabled': bool(row[8]),
                        'delay_seconds': row[9] or 0,
                        'is_multi_spec': bool(row[10]) if row[10] is not None else False,
                        'spec_name': row[11],
                        'spec_value': row[12],
                        'created_at': row[13],
                        'updated_at': row[14]
                    }
                return None
            except Exception as e:
                logger.error(f"获取卡券失败: {e}")
                return None

    def update_card(self, card_id: int, name: str = None, card_type: str = None,
                   api_config=None, text_content: str = None, data_content: str = None,
                   image_url: str = None, description: str = None, enabled: bool = None,
                   delay_seconds: int = None, is_multi_spec: bool = None, spec_name: str = None,
                   spec_value: str = None):
        """更新卡券"""
        with self.lock:
            try:
                # 处理api_config参数
                api_config_str = None
                if api_config is not None:
                    if isinstance(api_config, dict):
                        import json
                        api_config_str = json.dumps(api_config)
                    else:
                        api_config_str = str(api_config)

                cursor = self.conn.cursor()

                # 构建更新语句
                update_fields = []
                params = []

                if name is not None:
                    update_fields.append("name = ?")
                    params.append(name)
                if card_type is not None:
                    update_fields.append("type = ?")
                    params.append(card_type)
                if api_config_str is not None:
                    update_fields.append("api_config = ?")
                    params.append(api_config_str)
                if text_content is not None:
                    update_fields.append("text_content = ?")
                    params.append(text_content)
                if data_content is not None:
                    update_fields.append("data_content = ?")
                    params.append(data_content)
                if image_url is not None:
                    update_fields.append("image_url = ?")
                    params.append(image_url)
                if description is not None:
                    update_fields.append("description = ?")
                    params.append(description)
                if enabled is not None:
                    update_fields.append("enabled = ?")
                    params.append(enabled)
                if delay_seconds is not None:
                    update_fields.append("delay_seconds = ?")
                    params.append(delay_seconds)
                if is_multi_spec is not None:
                    update_fields.append("is_multi_spec = ?")
                    params.append(is_multi_spec)
                if spec_name is not None:
                    update_fields.append("spec_name = ?")
                    params.append(spec_name)
                if spec_value is not None:
                    update_fields.append("spec_value = ?")
                    params.append(spec_value)

                if not update_fields:
                    return True  # 没有需要更新的字段

                update_fields.append("updated_at = CURRENT_TIMESTAMP")
                params.append(card_id)

                sql = f"UPDATE cards SET {', '.join(update_fields)} WHERE id = ?"
                self._execute_sql(cursor, sql, params)

                if cursor.rowcount > 0:
                    self.conn.commit()
                    logger.info(f"更新卡券成功: ID {card_id}")
                    return True
                else:
                    return False  # 没有找到对应的记录

            except Exception as e:
                logger.error(f"更新卡券失败: {e}")
                self.conn.rollback()
                raise

    def delete_card(self, card_id: int):
        """删除卡券"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                self._execute_sql(cursor, "DELETE FROM cards WHERE id = ?", (card_id,))

                if cursor.rowcount > 0:
                    self.conn.commit()
                    logger.info(f"删除卡券成功: ID {card_id}")
                    return True
                else:
                    return False  # 没有找到对应的记录

            except Exception as e:
                logger.error(f"删除卡券失败: {e}")
                self.conn.rollback()
                raise



