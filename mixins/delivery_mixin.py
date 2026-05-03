"""
Delivery Mixin - 发货规则管理
"""
import sqlite3
import json
import time
import secrets
from typing import Optional, Dict, Any, List, Tuple
from loguru import logger


class DeliveryManagerMixin:
    """发货规则管理"""

    def create_delivery_rule(self, keyword: str, card_id: int, delivery_count: int = 1,
                           enabled: bool = True, description: str = None, user_id: int = None):
        """创建发货规则"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                INSERT INTO delivery_rules (keyword, card_id, delivery_count, enabled, description, user_id)
                VALUES (?, ?, ?, ?, ?, ?)
                ''', (keyword, card_id, delivery_count, enabled, description, user_id))
                self.conn.commit()
                rule_id = cursor.lastrowid
                logger.info(f"创建发货规则成功: {keyword} -> 卡券ID {card_id} (规则ID: {rule_id})")
                return rule_id
            except Exception as e:
                logger.error(f"创建发货规则失败: {e}")
                raise



    def get_all_delivery_rules(self, user_id: int = None):
        """获取所有发货规则"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                if user_id is not None:
                    cursor.execute('''
                    SELECT dr.id, dr.keyword, dr.card_id, dr.delivery_count, dr.enabled,
                           dr.description, dr.delivery_times, dr.created_at, dr.updated_at,
                           c.name as card_name, c.type as card_type,
                           c.is_multi_spec, c.spec_name, c.spec_value
                    FROM delivery_rules dr
                    LEFT JOIN cards c ON dr.card_id = c.id
                    WHERE dr.user_id = ?
                    ORDER BY dr.created_at DESC
                    ''', (user_id,))
                else:
                    cursor.execute('''
                    SELECT dr.id, dr.keyword, dr.card_id, dr.delivery_count, dr.enabled,
                           dr.description, dr.delivery_times, dr.created_at, dr.updated_at,
                           c.name as card_name, c.type as card_type,
                           c.is_multi_spec, c.spec_name, c.spec_value
                    FROM delivery_rules dr
                    LEFT JOIN cards c ON dr.card_id = c.id
                    ORDER BY dr.created_at DESC
                    ''')

                rules = []
                for row in cursor.fetchall():
                    rules.append({
                        'id': row[0],
                        'keyword': row[1],
                        'card_id': row[2],
                        'delivery_count': row[3],
                        'enabled': bool(row[4]),
                        'description': row[5],
                        'delivery_times': row[6],
                        'created_at': row[7],
                        'updated_at': row[8],
                        'card_name': row[9],
                        'card_type': row[10],
                        'is_multi_spec': bool(row[11]) if row[11] is not None else False,
                        'spec_name': row[12],
                        'spec_value': row[13]
                    })

                return rules
            except Exception as e:
                logger.error(f"获取发货规则列表失败: {e}")
                return []



    def get_delivery_rule_by_id(self, rule_id: int, user_id: int = None):
        """根据ID获取发货规则（支持用户隔离）"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                if user_id is not None:
                    self._execute_sql(cursor, '''
                    SELECT dr.id, dr.keyword, dr.card_id, dr.delivery_count, dr.enabled,
                           dr.description, dr.delivery_times, dr.created_at, dr.updated_at,
                           c.name as card_name, c.type as card_type
                    FROM delivery_rules dr
                    LEFT JOIN cards c ON dr.card_id = c.id
                    WHERE dr.id = ? AND dr.user_id = ?
                    ''', (rule_id, user_id))
                else:
                    self._execute_sql(cursor, '''
                    SELECT dr.id, dr.keyword, dr.card_id, dr.delivery_count, dr.enabled,
                           dr.description, dr.delivery_times, dr.created_at, dr.updated_at,
                           c.name as card_name, c.type as card_type
                    FROM delivery_rules dr
                    LEFT JOIN cards c ON dr.card_id = c.id
                    WHERE dr.id = ?
                    ''', (rule_id,))

                row = cursor.fetchone()
                if row:
                    return {
                        'id': row[0],
                        'keyword': row[1],
                        'card_id': row[2],
                        'delivery_count': row[3],
                        'enabled': bool(row[4]),
                        'description': row[5],
                        'delivery_times': row[6],
                        'created_at': row[7],
                        'updated_at': row[8],
                        'card_name': row[9],
                        'card_type': row[10]
                    }
                return None
            except Exception as e:
                logger.error(f"获取发货规则失败: {e}")
                return None



    def update_delivery_rule(self, rule_id: int, keyword: str = None, card_id: int = None,
                           delivery_count: int = None, enabled: bool = None,
                           description: str = None, user_id: int = None):
        """更新发货规则（支持用户隔离）"""
        with self.lock:
            try:
                cursor = self.conn.cursor()

                # 构建更新语句
                update_fields = []
                params = []

                if keyword is not None:
                    update_fields.append("keyword = ?")
                    params.append(keyword)
                if card_id is not None:
                    update_fields.append("card_id = ?")
                    params.append(card_id)
                if delivery_count is not None:
                    update_fields.append("delivery_count = ?")
                    params.append(delivery_count)
                if enabled is not None:
                    update_fields.append("enabled = ?")
                    params.append(enabled)
                if description is not None:
                    update_fields.append("description = ?")
                    params.append(description)

                if not update_fields:
                    return True  # 没有需要更新的字段

                update_fields.append("updated_at = CURRENT_TIMESTAMP")
                params.append(rule_id)

                if user_id is not None:
                    params.append(user_id)
                    sql = f"UPDATE delivery_rules SET {', '.join(update_fields)} WHERE id = ? AND user_id = ?"
                else:
                    sql = f"UPDATE delivery_rules SET {', '.join(update_fields)} WHERE id = ?"

                self._execute_sql(cursor, sql, params)

                if cursor.rowcount > 0:
                    self.conn.commit()
                    logger.info(f"更新发货规则成功: ID {rule_id}")
                    return True
                else:
                    return False  # 没有找到对应的记录

            except Exception as e:
                logger.error(f"更新发货规则失败: {e}")
                self.conn.rollback()
                raise



    def increment_delivery_times(self, rule_id: int):
        """增加发货次数"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                UPDATE delivery_rules
                SET delivery_times = delivery_times + 1, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                ''', (rule_id,))
                self.conn.commit()
                logger.debug(f"发货规则 {rule_id} 发货次数已增加")
            except Exception as e:
                logger.error(f"更新发货次数失败: {e}")



    def delete_delivery_rule(self, rule_id: int, user_id: int = None):
        """删除发货规则（支持用户隔离）"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                if user_id is not None:
                    self._execute_sql(cursor, "DELETE FROM delivery_rules WHERE id = ? AND user_id = ?", (rule_id, user_id))
                else:
                    self._execute_sql(cursor, "DELETE FROM delivery_rules WHERE id = ?", (rule_id,))

                if cursor.rowcount > 0:
                    self.conn.commit()
                    logger.info(f"删除发货规则成功: ID {rule_id} (用户ID: {user_id})")
                    return True
                else:
                    return False  # 没有找到对应的记录

            except Exception as e:
                logger.error(f"删除发货规则失败: {e}")
                self.conn.rollback()
                raise



    def add_delivery_retry(self, cookie_id: str, order_id: str = None, item_id: str = None,
                           buyer_id: str = None, buyer_name: str = '', chat_id: str = '',
                           quantity: int = 1, spec_name: str = '', spec_value: str = '',
                           error_type: str = 'no_match', error_message: str = '') -> int:
        """添加发货失败重试记录"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                    INSERT INTO delivery_retry_queue
                    (cookie_id, order_id, item_id, buyer_id, buyer_name, chat_id,
                     quantity, spec_name, spec_value, error_type, error_message, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                ''', (cookie_id, order_id, item_id, buyer_id, buyer_name, chat_id,
                      quantity, spec_name, spec_value, error_type, error_message))
                self.conn.commit()
                retry_id = cursor.lastrowid
                logger.info(f"发货失败已加入重试队列: id={retry_id}, order={order_id}, 买家={buyer_name}")
                return retry_id
        except Exception as e:
            logger.error(f"添加发货重试记录失败: {e}")
            return -1



    def get_pending_delivery_retries(self) -> list:
        """获取需要重试的发货记录"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                    SELECT * FROM delivery_retry_queue
                    WHERE status IN ('pending', 'retrying')
                    AND next_retry_at <= datetime('now', 'localtime')
                    ORDER BY created_at ASC
                ''')
                rows = cursor.fetchall()
                columns = [d[0] for d in cursor.description]
                return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            logger.error(f"获取待重试发货记录失败: {e}")
            return []



    def update_delivery_retry_status(self, retry_id: int, status: str, error_message: str = None,
                                      increment_retry: bool = True, delay_minutes: int = 5) -> bool:
        """更新发货重试状态"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                if increment_retry:
                    cursor.execute('''
                        UPDATE delivery_retry_queue
                        SET status = ?, error_message = COALESCE(?, error_message),
                            retry_count = retry_count + 1,
                            next_retry_at = datetime('now', 'localtime', ? || ' minutes'),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    ''', (status, error_message, f'+{delay_minutes}', retry_id))
                else:
                    cursor.execute('''
                        UPDATE delivery_retry_queue
                        SET status = ?, error_message = COALESCE(?, error_message),
                            next_retry_at = datetime('now', 'localtime', ? || ' minutes'),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    ''', (status, error_message, f'+{delay_minutes}', retry_id))
                self.conn.commit()
                logger.info(f"发货重试状态更新: id={retry_id}, status={status}")
                return True
        except Exception as e:
            logger.error(f"更新发货重试状态失败: {e}")
            return False



    def get_delivery_retry_queue(self, cookie_id: str = None, page: int = 1, page_size: int = 20) -> dict:
        """获取发货重试队列列表"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                where = ''
                params = []
                if cookie_id:
                    where = 'WHERE cookie_id = ?'
                    params.append(cookie_id)

                cursor.execute(f'SELECT COUNT(*) FROM delivery_retry_queue {where}', params)
                total = cursor.fetchone()[0]

                offset = (page - 1) * page_size
                cursor.execute(f'''
                    SELECT * FROM delivery_retry_queue {where}
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
            logger.error(f"获取发货重试队列失败: {e}")
            return {'data': [], 'total': 0, 'page': page, 'page_size': page_size}



    def delete_delivery_retry(self, retry_id: int) -> bool:
        """删除发货重试记录"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute('DELETE FROM delivery_retry_queue WHERE id = ?', (retry_id,))
                self.conn.commit()
                return True
        except Exception as e:
            logger.error(f"删除发货重试记录失败: {e}")
            return False

