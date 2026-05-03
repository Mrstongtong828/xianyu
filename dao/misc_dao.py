"""
MISC DAO Mixin
"""

from loguru import logger
import sqlite3
import time
from typing import List, Tuple, Dict, Optional, Any


class MiscDAOMixin:
    """MISC related database operations"""

    def save_verification_code(self, email: str, code: str, code_type: str = 'register', expires_minutes: int = 10) -> bool:
        """保存邮箱验证码"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                expires_at = time.time() + (expires_minutes * 60)

                cursor.execute('''
                INSERT INTO email_verifications (email, code, type, expires_at)
                VALUES (?, ?, ?, ?)
                ''', (email, code, code_type, expires_at))

                self.conn.commit()
                logger.info(f"保存验证码成功: {email} ({code_type})")
                return True
            except Exception as e:
                logger.error(f"保存验证码失败: {e}")
                self.conn.rollback()
                return False

    def verify_email_code(self, email: str, code: str, code_type: str = 'register') -> bool:
        """验证邮箱验证码"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                current_time = time.time()

                # 查找有效的验证码
                cursor.execute('''
                SELECT id FROM email_verifications
                WHERE email = ? AND code = ? AND type = ? AND expires_at > ? AND used = FALSE
                ORDER BY created_at DESC LIMIT 1
                ''', (email, code, code_type, current_time))

                row = cursor.fetchone()
                if row:
                    # 标记验证码为已使用
                    cursor.execute('''
                    UPDATE email_verifications SET used = TRUE WHERE id = ?
                    ''', (row[0],))
                    self.conn.commit()
                    logger.info(f"验证码验证成功: {email} ({code_type})")
                    return True
                else:
                    logger.warning(f"验证码验证失败: {email} - {code} ({code_type})")
                    return False
            except Exception as e:
                logger.error(f"验证邮箱验证码失败: {e}")
                return False

    async def send_verification_email(self, email: str, code: str) -> bool:
        """发送验证码邮件（支持SMTP和API两种方式）"""
        try:
            subject = "闲鱼自动回复系统 - 邮箱验证码"
            # 使用简单的纯文本邮件内容
            text_content = f"""【闲鱼自动回复系统】邮箱验证码

您的验证码是：{code}

该验证码将在10分钟后过期，请尽快使用。

如非本人操作，请忽略此邮件。
"""
            # TODO: 实现邮件发送逻辑（SMTP或API）
            logger.info(f"邮件内容已生成: {email}")
            return True
        except Exception as e:
            logger.error(f"发送验证码邮件失败: {e}")
            return False

    def create_card(self, name: str, card_type: str, api_config=None,
                   text_content: str = None, data_content: str = None, image_url: str = None,
                   description: str = None, enabled: bool = True, delay_seconds: int = 0,
                   is_multi_spec: bool = False, spec_name: str = None, spec_value: str = None,
                   user_id: int = None):
        """创建新卡券（支持多规格）"""
        with self.lock:
            try:
                # 验证多规格参数
                if is_multi_spec:
                    if not spec_name or not spec_value:
                        raise ValueError("多规格卡券必须提供规格名称和规格值")

                    # 检查唯一性：卡券名称+规格名称+规格值
                    cursor = self.conn.cursor()
                    cursor.execute('''
                    SELECT COUNT(*) FROM cards
                    WHERE name = ? AND spec_name = ? AND spec_value = ? AND user_id = ?
                    ''', (name, spec_name, spec_value, user_id))

                    if cursor.fetchone()[0] > 0:
                        raise ValueError(f"卡券已存在：{name} - {spec_name}:{spec_value}")
                else:
                    # 检查唯一性：仅卡券名称
                    cursor = self.conn.cursor()
                    cursor.execute('''
                    SELECT COUNT(*) FROM cards
                    WHERE name = ? AND (is_multi_spec = 0 OR is_multi_spec IS NULL) AND user_id = ?
                    ''', (name, user_id))

                    if cursor.fetchone()[0] > 0:
                        raise ValueError(f"卡券名称已存在：{name}")

                # 处理api_config参数 - 如果是字典则转换为JSON字符串
                api_config_str = None
                if api_config is not None:
                    if isinstance(api_config, dict):
                        import json
                        api_config_str = json.dumps(api_config)
                    else:
                        api_config_str = str(api_config)

                cursor.execute('''
                INSERT INTO cards (name, type, api_config, text_content, data_content, image_url,
                                 description, enabled, delay_seconds, is_multi_spec,
                                 spec_name, spec_value, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (name, card_type, api_config_str, text_content, data_content, image_url,
                      description, enabled, delay_seconds, is_multi_spec,
                      spec_name, spec_value, user_id))
                self.conn.commit()
                card_id = cursor.lastrowid

                if is_multi_spec:
                    logger.info(f"创建多规格卡券成功: {name} - {spec_name}:{spec_value} (ID: {card_id})")
                else:
                    logger.info(f"创建卡券成功: {name} (ID: {card_id})")
                return card_id
            except Exception as e:
                logger.error(f"创建卡券失败: {e}")
                raise

    def update_card_image_url(self, card_id: int, new_image_url: str) -> bool:
        """更新卡券的图片URL"""
        with self.lock:
            try:
                cursor = self.conn.cursor()

                # 更新图片URL
                self._execute_sql(cursor,
                    "UPDATE cards SET image_url = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND type = 'image'",
                    (new_image_url, card_id))

                self.conn.commit()

                # 检查是否有行被更新
                if cursor.rowcount > 0:
                    logger.info(f"卡券图片URL更新成功: 卡券ID: {card_id}, 新URL: {new_image_url}")
                    return True
                else:
                    logger.warning(f"未找到匹配的图片卡券: 卡券ID: {card_id}")
                    return False

            except Exception as e:
                logger.error(f"更新卡券图片URL失败: {e}")
                self.conn.rollback()
                return False

    # ==================== 自动发货规则方法 ====================

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

    def get_delivery_rules_by_keyword(self, keyword: str):
        """根据关键字获取匹配的发货规则"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                # 使用更灵活的匹配方式：既支持商品内容包含关键字，也支持关键字包含在商品内容中
                cursor.execute('''
                SELECT dr.id, dr.keyword, dr.card_id, dr.delivery_count, dr.enabled,
                       dr.description, dr.delivery_times,
                       c.name as card_name, c.type as card_type, c.api_config,
                       c.text_content, c.data_content, c.image_url, c.enabled as card_enabled, c.description as card_description,
                       c.delay_seconds as card_delay_seconds,
                       c.is_multi_spec, c.spec_name, c.spec_value
                FROM delivery_rules dr
                LEFT JOIN cards c ON dr.card_id = c.id
                WHERE dr.enabled = 1 AND c.enabled = 1
                AND (? LIKE '%' || dr.keyword || '%' OR dr.keyword LIKE '%' || ? || '%')
                ORDER BY
                    CASE
                        WHEN ? LIKE '%' || dr.keyword || '%' THEN LENGTH(dr.keyword)
                        ELSE LENGTH(dr.keyword) / 2
                    END DESC,
                    dr.id ASC
                ''', (keyword, keyword, keyword))

                rules = []
                for row in cursor.fetchall():
                    # 解析api_config JSON字符串
                    api_config = row[9]
                    if api_config:
                        try:
                            import json
                            api_config = json.loads(api_config)
                        except (json.JSONDecodeError, TypeError):
                            # 如果解析失败，保持原始字符串
                            pass

                    rules.append({
                        'id': row[0],
                        'keyword': row[1],
                        'card_id': row[2],
                        'delivery_count': row[3],
                        'enabled': bool(row[4]),
                        'description': row[5],
                        'delivery_times': row[6],
                        'card_name': row[7],
                        'card_type': row[8],
                        'api_config': api_config,  # 修复字段名
                        'text_content': row[10],
                        'data_content': row[11],
                        'image_url': row[12],
                        'card_enabled': bool(row[13]),
                        'card_description': row[14],  # 卡券备注信息
                        'card_delay_seconds': row[15] or 0,  # 延时秒数
                        'is_multi_spec': bool(row[16]) if row[16] is not None else False,
                        'spec_name': row[17],
                        'spec_value': row[18]
                    })

                return rules
            except Exception as e:
                logger.error(f"根据关键字获取发货规则失败: {e}")
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

    def get_delivery_rules_by_keyword_and_spec(self, keyword: str, spec_name: str = None, spec_value: str = None):
        """根据关键字和规格信息获取匹配的发货规则（支持多规格）"""
        with self.lock:
            try:
                cursor = self.conn.cursor()

                # 优先匹配：卡券名称+规格名称+规格值
                if spec_name and spec_value:
                    cursor.execute('''
                    SELECT dr.id, dr.keyword, dr.card_id, dr.delivery_count, dr.enabled,
                           dr.description, dr.delivery_times,
                           c.name as card_name, c.type as card_type, c.api_config,
                           c.text_content, c.data_content, c.enabled as card_enabled,
                           c.description as card_description, c.delay_seconds as card_delay_seconds,
                           c.is_multi_spec, c.spec_name, c.spec_value
                    FROM delivery_rules dr
                    LEFT JOIN cards c ON dr.card_id = c.id
                    WHERE dr.enabled = 1 AND c.enabled = 1
                    AND (? LIKE '%' || dr.keyword || '%' OR dr.keyword LIKE '%' || ? || '%')
                    AND c.is_multi_spec = 1 AND c.spec_name = ? AND c.spec_value = ?
                    ORDER BY
                        CASE
                            WHEN ? LIKE '%' || dr.keyword || '%' THEN LENGTH(dr.keyword)
                            ELSE LENGTH(dr.keyword) / 2
                        END DESC,
                        dr.delivery_times ASC
                    ''', (keyword, keyword, spec_name, spec_value, keyword))

                    rules = []
                    for row in cursor.fetchall():
                        # 解析api_config JSON字符串
                        api_config = row[9]
                        if api_config:
                            try:
                                import json
                                api_config = json.loads(api_config)
                            except (json.JSONDecodeError, TypeError):
                                # 如果解析失败，保持原始字符串
                                pass

                        rules.append({
                            'id': row[0],
                            'keyword': row[1],
                            'card_id': row[2],
                            'delivery_count': row[3],
                            'enabled': bool(row[4]),
                            'description': row[5],
                            'delivery_times': row[6] or 0,
                            'card_name': row[7],
                            'card_type': row[8],
                            'api_config': api_config,
                            'text_content': row[10],
                            'data_content': row[11],
                            'card_enabled': bool(row[12]),
                            'card_description': row[13],
                            'card_delay_seconds': row[14] or 0,
                            'is_multi_spec': bool(row[15]),
                            'spec_name': row[16],
                            'spec_value': row[17]
                        })

                    if rules:
                        logger.info(f"找到多规格匹配规则: {keyword} - {spec_name}:{spec_value}")
                        return rules

                # 兜底匹配：仅卡券名称
                cursor.execute('''
                SELECT dr.id, dr.keyword, dr.card_id, dr.delivery_count, dr.enabled,
                       dr.description, dr.delivery_times,
                       c.name as card_name, c.type as card_type, c.api_config,
                       c.text_content, c.data_content, c.enabled as card_enabled,
                       c.description as card_description, c.delay_seconds as card_delay_seconds,
                       c.is_multi_spec, c.spec_name, c.spec_value
                FROM delivery_rules dr
                LEFT JOIN cards c ON dr.card_id = c.id
                WHERE dr.enabled = 1 AND c.enabled = 1
                AND (? LIKE '%' || dr.keyword || '%' OR dr.keyword LIKE '%' || ? || '%')
                AND (c.is_multi_spec = 0 OR c.is_multi_spec IS NULL)
                ORDER BY
                    CASE
                        WHEN ? LIKE '%' || dr.keyword || '%' THEN LENGTH(dr.keyword)
                        ELSE LENGTH(dr.keyword) / 2
                    END DESC,
                    dr.delivery_times ASC
                ''', (keyword, keyword, keyword))

                rules = []
                for row in cursor.fetchall():
                    # 解析api_config JSON字符串
                    api_config = row[9]
                    if api_config:
                        try:
                            import json
                            api_config = json.loads(api_config)
                        except (json.JSONDecodeError, TypeError):
                            # 如果解析失败，保持原始字符串
                            pass

                    rules.append({
                        'id': row[0],
                        'keyword': row[1],
                        'card_id': row[2],
                        'delivery_count': row[3],
                        'enabled': bool(row[4]),
                        'description': row[5],
                        'delivery_times': row[6] or 0,
                        'card_name': row[7],
                        'card_type': row[8],
                        'api_config': api_config,
                        'text_content': row[10],
                        'data_content': row[11],
                        'card_enabled': bool(row[12]),
                        'card_description': row[13],
                        'card_delay_seconds': row[14] or 0,
                        'is_multi_spec': bool(row[15]) if row[15] is not None else False,
                        'spec_name': row[16],
                        'spec_value': row[17]
                    })

                if rules:
                    logger.info(f"找到兜底匹配规则: {keyword}")
                else:
                    logger.info(f"未找到匹配规则: {keyword}")

                return rules

            except Exception as e:
                logger.error(f"获取发货规则失败: {e}")
                return []

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

    def consume_batch_data(self, card_id: int):
        """消费批量数据的第一条记录（线程安全）"""
        with self.lock:
            try:
                cursor = self.conn.cursor()

                # 获取卡券的批量数据
                self._execute_sql(cursor, "SELECT data_content FROM cards WHERE id = ? AND type = 'data'", (card_id,))
                result = cursor.fetchone()

                if not result or not result[0]:
                    logger.warning(f"卡券 {card_id} 没有批量数据")
                    return None

                data_content = result[0]
                lines = [line.strip() for line in data_content.split('\n') if line.strip()]

                if not lines:
                    logger.warning(f"卡券 {card_id} 批量数据为空")
                    return None

                # 获取第一条数据
                first_line = lines[0]

                # 移除第一条数据，更新数据库
                remaining_lines = lines[1:]
                new_data_content = '\n'.join(remaining_lines)

                cursor.execute('''
                UPDATE cards
                SET data_content = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                ''', (new_data_content, card_id))

                self.conn.commit()

                logger.info(f"消费批量数据成功: 卡券ID={card_id}, 剩余={len(remaining_lines)}条")
                return first_line

            except Exception as e:
                logger.error(f"消费批量数据失败: {e}")
                self.conn.rollback()
                return None

    # ==================== 商品信息管理 ====================

    def save_item_basic_info(self, cookie_id: str, item_id: str, item_title: str = None,
                            item_description: str = None, item_category: str = None,
                            item_price: str = None, item_detail: str = None) -> bool:
        """保存或更新商品基本信息，使用原子操作避免并发问题

        Args:
            cookie_id: Cookie ID
            item_id: 商品ID
            item_title: 商品标题
            item_description: 商品描述
            item_category: 商品分类
            item_price: 商品价格
            item_detail: 商品详情JSON

        Returns:
            bool: 操作是否成功
        """
        try:
            with self.lock:
                cursor = self.conn.cursor()

                # 使用 INSERT OR IGNORE + UPDATE 的原子操作模式
                # 首先尝试插入，如果已存在则忽略
                cursor.execute('''
                INSERT OR IGNORE INTO item_info (cookie_id, item_id, item_title, item_description,
                                               item_category, item_price, item_detail, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ''', (cookie_id, item_id, item_title or '', item_description or '',
                      item_category or '', item_price or '', item_detail or ''))

                # 如果是新插入的记录，直接返回成功
                if cursor.rowcount > 0:
                    self.conn.commit()
                    logger.info(f"新增商品基本信息: {item_id} - {item_title}")
                    return True

                # 记录已存在，使用原子UPDATE操作，只更新非空字段且不覆盖现有非空值
                update_parts = []
                params = []

                # 使用 CASE WHEN 语句进行条件更新，避免覆盖现有数据
                if item_title:
                    update_parts.append("item_title = CASE WHEN (item_title IS NULL OR item_title = '') THEN ? ELSE item_title END")
                    params.append(item_title)

                if item_description:
                    update_parts.append("item_description = CASE WHEN (item_description IS NULL OR item_description = '') THEN ? ELSE item_description END")
                    params.append(item_description)

                if item_category:
                    update_parts.append("item_category = CASE WHEN (item_category IS NULL OR item_category = '') THEN ? ELSE item_category END")
                    params.append(item_category)

                if item_price:
                    update_parts.append("item_price = CASE WHEN (item_price IS NULL OR item_price = '') THEN ? ELSE item_price END")
                    params.append(item_price)

                # 对于item_detail，只有在现有值为空时才更新
                if item_detail:
                    update_parts.append("item_detail = CASE WHEN (item_detail IS NULL OR item_detail = '' OR TRIM(item_detail) = '') THEN ? ELSE item_detail END")
                    params.append(item_detail)

                if update_parts:
                    update_parts.append("updated_at = CURRENT_TIMESTAMP")
                    params.extend([cookie_id, item_id])

                    sql = f"UPDATE item_info SET {', '.join(update_parts)} WHERE cookie_id = ? AND item_id = ?"
                    self._execute_sql(cursor, sql, params)

                    if cursor.rowcount > 0:
                        logger.info(f"更新商品基本信息: {item_id} - {item_title}")
                    else:
                        logger.debug(f"商品信息无需更新: {item_id}")

                self.conn.commit()
                return True

        except Exception as e:
            logger.error(f"保存商品基本信息失败: {e}")
            self.conn.rollback()
            return False

    def save_item_info(self, cookie_id: str, item_id: str, item_data = None) -> bool:
        """保存或更新商品信息

        Args:
            cookie_id: Cookie ID
            item_id: 商品ID
            item_data: 商品详情数据，可以是字符串或字典，也可以为None

        Returns:
            bool: 操作是否成功
        """
        try:
            # 验证：如果只有商品ID，没有商品详情数据，则不插入数据库
            if not item_data:
                logger.debug(f"跳过保存商品信息：缺少商品详情数据 - {item_id}")
                return False

            # 如果是字典类型，检查是否有标题信息
            if isinstance(item_data, dict):
                title = item_data.get('title', '').strip()
                if not title:
                    logger.debug(f"跳过保存商品信息：缺少商品标题 - {item_id}")
                    return False

            # 如果是字符串类型，检查是否为空
            if isinstance(item_data, str) and not item_data.strip():
                logger.debug(f"跳过保存商品信息：商品详情为空 - {item_id}")
                return False

            with self.lock:
                cursor = self.conn.cursor()

                # 检查商品是否已存在
                cursor.execute('''
                SELECT id, item_detail FROM item_info
                WHERE cookie_id = ? AND item_id = ?
                ''', (cookie_id, item_id))

                existing = cursor.fetchone()

                if existing:
                    # 如果传入的商品详情有值，则用最新数据覆盖
                    if item_data is not None and item_data:
                        # 处理字符串类型的详情数据
                        if isinstance(item_data, str):
                            cursor.execute('''
                            UPDATE item_info SET
                                item_detail = ?, updated_at = CURRENT_TIMESTAMP
                            WHERE cookie_id = ? AND item_id = ?
                            ''', (item_data, cookie_id, item_id))
                        else:
                            # 处理字典类型的详情数据（向后兼容）
                            cursor.execute('''
                            UPDATE item_info SET
                                item_title = ?, item_description = ?, item_category = ?,
                                item_price = ?, item_detail = ?, updated_at = CURRENT_TIMESTAMP
                            WHERE cookie_id = ? AND item_id = ?
                            ''', (
                                item_data.get('title', ''),
                                item_data.get('description', ''),
                                item_data.get('category', ''),
                                item_data.get('price', ''),
                                json.dumps(item_data, ensure_ascii=False),
                                cookie_id, item_id
                            ))
                        logger.info(f"更新商品信息（覆盖）: {item_id}")
                    else:
                        # 如果商品详情没有数据，则不更新，只记录存在
                        logger.debug(f"商品信息已存在，无新数据，跳过更新: {item_id}")
                        return True
                else:
                    # 新增商品信息
                    if isinstance(item_data, str):
                        # 直接保存字符串详情
                        cursor.execute('''
                        INSERT INTO item_info (cookie_id, item_id, item_detail)
                        VALUES (?, ?, ?)
                        ''', (cookie_id, item_id, item_data))
                    else:
                        # 处理字典类型的详情数据（向后兼容）
                        cursor.execute('''
                        INSERT INTO item_info (cookie_id, item_id, item_title, item_description,
                                             item_category, item_price, item_detail)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            cookie_id, item_id,
                            item_data.get('title', '') if item_data else '',
                            item_data.get('description', '') if item_data else '',
                            item_data.get('category', '') if item_data else '',
                            item_data.get('price', '') if item_data else '',
                            json.dumps(item_data, ensure_ascii=False) if item_data else ''
                        ))
                    logger.info(f"新增商品信息: {item_id}")

                self.conn.commit()
                return True

        except Exception as e:
            logger.error(f"保存商品信息失败: {e}")
            self.conn.rollback()
            return False

    def get_item_info(self, cookie_id: str, item_id: str) -> Optional[Dict]:
        """获取商品信息

        Args:
            cookie_id: Cookie ID
            item_id: 商品ID

        Returns:
            Dict: 商品信息，如果不存在返回None
        """
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                SELECT * FROM item_info
                WHERE cookie_id = ? AND item_id = ?
                ''', (cookie_id, item_id))

                row = cursor.fetchone()
                if row:
                    columns = [description[0] for description in cursor.description]
                    item_info = dict(zip(columns, row))

                    # 解析item_detail JSON
                    if item_info.get('item_detail'):
                        try:
                            item_info['item_detail_parsed'] = json.loads(item_info['item_detail'])
                        except:
                            item_info['item_detail_parsed'] = {}

                    if not item_info.get('item_image'):
                        detail = item_info.get('item_detail_parsed', {})
                        pic_info = detail.get('pic_info', {}) or detail.get('picInfo', {})
                        if pic_info and pic_info.get('picUrl'):
                            item_info['item_image'] = pic_info['picUrl']

                    items.append(item_info)

                return items

        except Exception as e:
            logger.error(f"获取所有商品信息失败: {e}")
            return []

    def update_item_detail(self, cookie_id: str, item_id: str, item_detail: str) -> bool:
        """更新商品详情（不覆盖商品标题等基本信息）

        Args:
            cookie_id: Cookie ID
            item_id: 商品ID
            item_detail: 商品详情JSON字符串

        Returns:
            bool: 操作是否成功
        """
        try:
            with self.lock:
                # 如果已有item_detail是有效JSON且包含pic_info，则合并保留
                cursor = self.conn.cursor()
                cursor.execute('''
                SELECT item_detail FROM item_info
                WHERE cookie_id = ? AND item_id = ?
                ''', (cookie_id, item_id))
                existing = cursor.fetchone()
                if existing and existing[0]:
                    try:
                        old_json = json.loads(existing[0])
                        if isinstance(old_json, dict) and old_json.get('pic_info'):
                            new_is_json = False
                            try:
                                new_json = json.loads(item_detail)
                                if isinstance(new_json, dict):
                                    new_json.setdefault('pic_info', old_json['pic_info'])
                                    new_json.setdefault('picInfo', old_json.get('picInfo', {}))
                                    item_detail = json.dumps(new_json, ensure_ascii=False)
                                    new_is_json = True
                            except:
                                pass
                            if not new_is_json:
                                merged = dict(old_json)
                                merged['description'] = item_detail
                                item_detail = json.dumps(merged, ensure_ascii=False)
                    except:
                        pass

                # 更新item_detail字段
                cursor.execute('''
                UPDATE item_info SET
                    item_detail = ?, updated_at = CURRENT_TIMESTAMP
                WHERE cookie_id = ? AND item_id = ?
                ''', (item_detail, cookie_id, item_id))

                if cursor.rowcount > 0:
                    self.conn.commit()
                    logger.info(f"更新商品详情成功: {item_id}")
                    return True
                else:
                    logger.warning(f"未找到要更新的商品: {item_id}")
                    return False

        except Exception as e:
            logger.error(f"更新商品详情失败: {e}")
            self.conn.rollback()
            return False

    def update_item_title_only(self, cookie_id: str, item_id: str, item_title: str) -> bool:
        """仅更新商品标题（并发安全）

        Args:
            cookie_id: Cookie ID
            item_id: 商品ID
            item_title: 商品标题

        Returns:
            bool: 操作是否成功
        """
        try:
            with self.lock:
                cursor = self.conn.cursor()
                # 使用 INSERT OR REPLACE 确保记录存在，但只更新标题字段
                cursor.execute('''
                INSERT INTO item_info (cookie_id, item_id, item_title, item_description,
                                     item_category, item_price, item_detail, created_at, updated_at)
                VALUES (?, ?, ?,
                       COALESCE((SELECT item_description FROM item_info WHERE cookie_id = ? AND item_id = ?), ''),
                       COALESCE((SELECT item_category FROM item_info WHERE cookie_id = ? AND item_id = ?), ''),
                       COALESCE((SELECT item_price FROM item_info WHERE cookie_id = ? AND item_id = ?), ''),
                       COALESCE((SELECT item_detail FROM item_info WHERE cookie_id = ? AND item_id = ?), ''),
                       COALESCE((SELECT created_at FROM item_info WHERE cookie_id = ? AND item_id = ?), CURRENT_TIMESTAMP),
                       CURRENT_TIMESTAMP)
                ON CONFLICT(cookie_id, item_id) DO UPDATE SET
                    item_title = excluded.item_title,
                    updated_at = CURRENT_TIMESTAMP
                ''', (cookie_id, item_id, item_title,
                      cookie_id, item_id, cookie_id, item_id, cookie_id, item_id,
                      cookie_id, item_id, cookie_id, item_id))

                self.conn.commit()
                logger.info(f"更新商品标题成功: {item_id} - {item_title}")
                return True

        except Exception as e:
            logger.error(f"更新商品标题失败: {e}")
            self.conn.rollback()
            return False

    def batch_save_item_basic_info(self, items_data: list) -> int:
        """批量保存商品基本信息（并发安全）

        Args:
            items_data: 商品数据列表，每个元素包含 cookie_id, item_id, item_title 等字段

        Returns:
            int: 成功保存的商品数量
        """
        if not items_data:
            return 0

        success_count = 0
        try:
            with self.lock:
                cursor = self.conn.cursor()

                # 使用事务批量处理
                cursor.execute('BEGIN TRANSACTION')

                for item_data in items_data:
                    try:
                        cookie_id = item_data.get('cookie_id')
                        item_id = item_data.get('item_id')
                        item_title = item_data.get('item_title', '')
                        item_description = item_data.get('item_description', '')
                        item_category = item_data.get('item_category', '')
                        item_price = item_data.get('item_price', '')
                        item_detail = item_data.get('item_detail', '')

                        if not cookie_id or not item_id:
                            continue

                        # 验证：如果没有商品标题，则跳过保存
                        if not item_title or not item_title.strip():
                            logger.debug(f"跳过批量保存商品信息：缺少商品标题 - {item_id}")
                            continue

                        # 使用 INSERT OR IGNORE + UPDATE 模式
                        cursor.execute('''
                        INSERT OR IGNORE INTO item_info (cookie_id, item_id, item_title, item_description,
                                                       item_category, item_price, item_detail, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                        ''', (cookie_id, item_id, item_title, item_description,
                              item_category, item_price, item_detail))

                        if cursor.rowcount == 0:
                            # 记录已存在，进行条件更新
                            update_sql = '''
                            UPDATE item_info SET
                                item_title = CASE WHEN (item_title IS NULL OR item_title = '') AND ? != '' THEN ? ELSE item_title END,
                                item_description = CASE WHEN (item_description IS NULL OR item_description = '') AND ? != '' THEN ? ELSE item_description END,
                                item_category = CASE WHEN (item_category IS NULL OR item_category = '') AND ? != '' THEN ? ELSE item_category END,
                                item_price = CASE WHEN (item_price IS NULL OR item_price = '') AND ? != '' THEN ? ELSE item_price END,
                                item_detail = ?,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE cookie_id = ? AND item_id = ?
                            '''
                            self._execute_sql(cursor, update_sql, (
                                item_title, item_title,
                                item_description, item_description,
                                item_category, item_category,
                                item_price, item_price,
                                item_detail,
                                cookie_id, item_id
                            ))

                        success_count += 1

                    except Exception as item_e:
                        logger.warning(f"批量保存单个商品失败 {item_data.get('item_id', 'unknown')}: {item_e}")
                        continue

                cursor.execute('COMMIT')
                logger.info(f"批量保存商品信息完成: {success_count}/{len(items_data)} 个商品")
                return success_count

        except Exception as e:
            logger.error(f"批量保存商品信息失败: {e}")
            try:
                cursor.execute('ROLLBACK')
            except:
                pass
            return success_count

    def delete_item_info(self, cookie_id: str, item_id: str) -> bool:
        """删除商品信息

        Args:
            cookie_id: Cookie ID
            item_id: 商品ID

        Returns:
            bool: 操作是否成功
        """
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute('DELETE FROM item_info WHERE cookie_id = ? AND item_id = ?',
                             (cookie_id, item_id))

                if cursor.rowcount > 0:
                    self.conn.commit()
                    logger.info(f"删除商品信息成功: {cookie_id} - {item_id}")
                    return True
                else:
                    logger.warning(f"未找到要删除的商品信息: {cookie_id} - {item_id}")
                    return False

        except Exception as e:
            logger.error(f"删除商品信息失败: {e}")
            self.conn.rollback()
            return False

    def batch_delete_item_info(self, items_to_delete: list) -> int:
        """批量删除商品信息

        Args:
            items_to_delete: 要删除的商品列表，每个元素包含 cookie_id 和 item_id

        Returns:
            int: 成功删除的商品数量
        """
        if not items_to_delete:
            return 0

        success_count = 0
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute('BEGIN TRANSACTION')

                for item_data in items_to_delete:
                    try:
                        cookie_id = item_data.get('cookie_id')
                        item_id = item_data.get('item_id')

                        if not cookie_id or not item_id:
                            continue

                        cursor.execute('DELETE FROM item_info WHERE cookie_id = ? AND item_id = ?',
                                     (cookie_id, item_id))

                        if cursor.rowcount > 0:
                            success_count += 1
                            logger.debug(f"删除商品信息: {cookie_id} - {item_id}")

                    except Exception as item_e:
                        logger.warning(f"删除单个商品失败 {item_data.get('item_id', 'unknown')}: {item_e}")
                        continue

                cursor.execute('COMMIT')
                logger.info(f"批量删除商品信息完成: {success_count}/{len(items_to_delete)} 个商品")
                return success_count

        except Exception as e:
            logger.error(f"批量删除商品信息失败: {e}")
            try:
                cursor.execute('ROLLBACK')
            except:
                pass
            return success_count

    # ==================== 用户设置管理方法 ====================

    def get_user_settings(self, user_id: int):
        """获取用户的所有设置"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                SELECT key, value, description, updated_at
                FROM user_settings
                WHERE user_id = ?
                ORDER BY key
                ''', (user_id,))

                settings = {}
                for row in cursor.fetchall():
                    settings[row[0]] = {
                        'value': row[1],
                        'description': row[2],
                        'updated_at': row[3]
                    }

                return settings
            except Exception as e:
                logger.error(f"获取用户设置失败: {e}")
                return {}

    def get_user_setting(self, user_id: int, key: str):
        """获取用户的特定设置"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                SELECT value, description, updated_at
                FROM user_settings
                WHERE user_id = ? AND key = ?
                ''', (user_id, key))

                row = cursor.fetchone()
                if row:
                    return {
                        'key': key,
                        'value': row[0],
                        'description': row[1],
                        'updated_at': row[2]
                    }
                return None
            except Exception as e:
                logger.error(f"获取用户设置失败: {e}")
                return None

    def set_user_setting(self, user_id: int, key: str, value: str, description: str = None):
        """设置用户配置"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                INSERT OR REPLACE INTO user_settings (user_id, key, value, description, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (user_id, key, value, description))

                self.conn.commit()
                logger.info(f"用户设置更新成功: user_id={user_id}, key={key}")
                return True
            except Exception as e:
                logger.error(f"设置用户配置失败: {e}")
                self.conn.rollback()
                return False

    # ==================== 管理员专用方法 ====================

    def delete_user_and_data(self, user_id: int):
        """删除用户及其所有相关数据"""
        with self.lock:
            try:
                cursor = self.conn.cursor()

                # 开始事务
                cursor.execute('BEGIN TRANSACTION')

                # 删除用户相关的所有数据
                # 1. 删除用户设置
                cursor.execute('DELETE FROM user_settings WHERE user_id = ?', (user_id,))

                # 2. 删除用户的卡券
                cursor.execute('DELETE FROM cards WHERE user_id = ?', (user_id,))

                # 3. 删除用户的发货规则
                cursor.execute('DELETE FROM delivery_rules WHERE user_id = ?', (user_id,))

                # 4. 删除用户的通知渠道
                cursor.execute('DELETE FROM notification_channels WHERE user_id = ?', (user_id,))

                # 5. 删除用户的Cookie
                cursor.execute('DELETE FROM cookies WHERE user_id = ?', (user_id,))

                # 6. 删除用户的关键字
                cursor.execute('DELETE FROM keywords WHERE cookie_id IN (SELECT id FROM cookies WHERE user_id = ?)', (user_id,))

                # 7. 删除用户的默认回复
                cursor.execute('DELETE FROM default_replies WHERE cookie_id IN (SELECT id FROM cookies WHERE user_id = ?)', (user_id,))

                # 8. 删除用户的AI回复设置
                cursor.execute('DELETE FROM ai_reply_settings WHERE cookie_id IN (SELECT id FROM cookies WHERE user_id = ?)', (user_id,))

                # 9. 删除用户的消息通知
                cursor.execute('DELETE FROM message_notifications WHERE cookie_id IN (SELECT id FROM cookies WHERE user_id = ?)', (user_id,))

                # 10. 最后删除用户本身
                cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))

                # 提交事务
                cursor.execute('COMMIT')

                logger.info(f"用户及相关数据删除成功: user_id={user_id}")
                return True

            except Exception as e:
                # 回滚事务
                cursor.execute('ROLLBACK')
                logger.error(f"删除用户及相关数据失败: {e}")
                return False

    def get_table_data(self, table_name: str):
        """获取指定表的所有数据"""
        with self.lock:
            try:
                cursor = self.conn.cursor()

                # 获取表结构
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns_info = cursor.fetchall()
                columns = [col[1] for col in columns_info]  # 列名

                # 获取表数据
                cursor.execute(f"SELECT * FROM {table_name}")
                rows = cursor.fetchall()

                # 转换为字典列表
                data = []
                for row in rows:
                    row_dict = {}
                    for i, value in enumerate(row):
                        row_dict[columns[i]] = value
                    data.append(row_dict)

                return data, columns

            except Exception as e:
                logger.error(f"获取表数据失败: {table_name} - {e}")
                return [], []

    def insert_or_update_order(self, order_id: str, item_id: str = None, buyer_id: str = None,
                              spec_name: str = None, spec_value: str = None, quantity: str = None,
                              amount: str = None, order_status: str = None, cookie_id: str = None,
                              is_bargain: bool = None, created_at: str = None, receiver_name: str = None,
                              receiver_phone: str = None, receiver_address: str = None,
                              system_shipped: bool = None, expected_version: int = None,
                              chat_id: str = None):
        """插入或更新订单信息"""
        with self.lock:
            try:
                cursor = self.conn.cursor()

                # 检查cookie_id是否在cookies表中存在（如果提供了cookie_id）
                if cookie_id:
                    cursor.execute("SELECT id FROM cookies WHERE id = ?", (cookie_id,))
                    cookie_exists = cursor.fetchone()
                    if not cookie_exists:
                        logger.warning(f"Cookie ID {cookie_id} 不存在于cookies表中，拒绝插入订单 {order_id}")
                        return False

                # 检查订单是否已存在
                cursor.execute("SELECT order_id FROM orders WHERE order_id = ?", (order_id,))
                existing = cursor.fetchone()

                if existing:
                    # 更新现有订单
                    update_fields = []
                    update_values = []

                    if item_id is not None:
                        update_fields.append("item_id = ?")
                        update_values.append(item_id)
                    if buyer_id is not None:
                        update_fields.append("buyer_id = ?")
                        update_values.append(buyer_id)
                    if spec_name is not None:
                        update_fields.append("spec_name = ?")
                        update_values.append(spec_name)
                    if spec_value is not None:
                        update_fields.append("spec_value = ?")
                        update_values.append(spec_value)
                    if quantity is not None:
                        update_fields.append("quantity = ?")
                        update_values.append(quantity)
                    if amount is not None:
                        update_fields.append("amount = ?")
                        update_values.append(amount)
                    if order_status is not None:
                        update_fields.append("order_status = ?")
                        update_values.append(order_status)
                    if cookie_id is not None:
                        update_fields.append("cookie_id = ?")
                        update_values.append(cookie_id)
                    if is_bargain is not None:
                        update_fields.append("is_bargain = ?")
                        update_values.append(1 if is_bargain else 0)
                    if created_at is not None:
                        # 更新创建时间（仅当明确提供时）
                        update_fields.append("created_at = ?")
                        update_values.append(created_at)
                    if receiver_name is not None:
                        update_fields.append("receiver_name = ?")
                        update_values.append(receiver_name)
                    if receiver_phone is not None:
                        update_fields.append("receiver_phone = ?")
                        update_values.append(receiver_phone)
                    if receiver_address is not None:
                        update_fields.append("receiver_address = ?")
                        update_values.append(receiver_address)
                    if system_shipped is not None:
                        update_fields.append("system_shipped = ?")
                        update_values.append(1 if system_shipped else 0)
                    if chat_id is not None:
                        update_fields.append("chat_id = ?")
                        update_values.append(chat_id)

                    if update_fields:
                        update_fields.append("updated_at = CURRENT_TIMESTAMP")
                        # 增加版本号
                        update_fields.append("version = version + 1")

                        # 构建WHERE条件
                        if expected_version is not None:
                            # 使用乐观锁：只有version匹配时才更新
                            where_clause = "order_id = ? AND version = ?"
                            update_values.extend([order_id, expected_version])
                        else:
                            # 不使用乐观锁
                            where_clause = "order_id = ?"
                            update_values.append(order_id)

                        sql = f"UPDATE orders SET {', '.join(update_fields)} WHERE {where_clause}"
                        cursor.execute(sql, update_values)

                        # 检查是否更新成功（乐观锁）
                        if expected_version is not None and cursor.rowcount == 0:
                            logger.warning(f"订单更新失败（版本冲突）: {order_id}, expected_version={expected_version}")
                            return False

                        logger.info(f"更新订单信息: {order_id}")
                else:
                    # 插入新订单
                    if created_at:
                        # 使用提供的创建时间
                        cursor.execute('''
                        INSERT INTO orders (order_id, item_id, buyer_id, spec_name, spec_value,
                                          quantity, amount, order_status, cookie_id, is_bargain, created_at,
                                          receiver_name, receiver_phone, receiver_address, system_shipped, chat_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (order_id, item_id, buyer_id, spec_name, spec_value,
                              quantity, amount, order_status or 'unknown', cookie_id,
                              1 if is_bargain else 0, created_at,
                              receiver_name, receiver_phone, receiver_address,
                              1 if system_shipped else 0, chat_id or ''))
                    else:
                        # 使用默认的创建时间（CURRENT_TIMESTAMP，UTC时间）
                        cursor.execute('''
                        INSERT INTO orders (order_id, item_id, buyer_id, spec_name, spec_value,
                                          quantity, amount, order_status, cookie_id, is_bargain,
                                          receiver_name, receiver_phone, receiver_address, system_shipped, chat_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (order_id, item_id, buyer_id, spec_name, spec_value,
                              quantity, amount, order_status or 'unknown', cookie_id,
                              1 if is_bargain else 0,
                              receiver_name, receiver_phone, receiver_address,
                              1 if system_shipped else 0, chat_id or ''))
                    logger.info(f"插入新订单: {order_id}")

                self.conn.commit()
                return True

            except Exception as e:
                logger.error(f"插入或更新订单失败: {order_id} - {e}")
                self.conn.rollback()
                return False

    def get_recent_order_by_item_and_buyer(self, item_id: str, buyer_id: str):
        """根据商品ID和买家ID获取最近的订单

        Args:
            item_id: 商品ID
            buyer_id: 买家ID

        Returns:
            dict: 订单信息，如果没有找到则返回None
        """
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                SELECT order_id, item_id, buyer_id, spec_name, spec_value,
                       quantity, amount, order_status, cookie_id, is_bargain, created_at, updated_at
                FROM orders
                WHERE item_id = ? AND buyer_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                ''', (item_id, buyer_id))

                row = cursor.fetchone()
                if row:
                    return {
                        'id': row[0],  # 使用 order_id 作为 id
                        'order_id': row[0],
                        'item_id': row[1],
                        'buyer_id': row[2],
                        'spec_name': row[3],
                        'spec_value': row[4],
                        'quantity': row[5],
                        'amount': row[6],
                        'order_status': row[7],
                        'cookie_id': row[8],
                        'is_bargain': bool(row[9]) if row[9] is not None else False,
                        'created_at': row[10],
                        'updated_at': row[11]
                    }
                return None

            except Exception as e:
                logger.error(f"获取订单信息失败: item_id={item_id}, buyer_id={buyer_id} - {e}")
                return None

    def delete_table_record(self, table_name: str, record_id: str):
        """删除指定表的指定记录"""
        with self.lock:
            try:
                cursor = self.conn.cursor()

                # 根据表名确定主键字段
                primary_key_map = {
                    'users': 'id',
                    'cookies': 'id',
                    'cookie_status': 'id',
                    'keywords': 'id',
                    'default_replies': 'id',
                    'default_reply_records': 'id',
                    'item_replay': 'item_id',
                    'ai_reply_settings': 'id',
                    'ai_conversations': 'id',
                    'ai_item_cache': 'id',
                    'item_info': 'id',
                    'message_notifications': 'id',
                    'cards': 'id',
                    'delivery_rules': 'id',
                    'notification_channels': 'id',
                    'user_settings': 'id',
                    'system_settings': 'id',
                    'email_verifications': 'id',
                    'captcha_codes': 'id',
                    'orders': 'order_id'
                }

                primary_key = primary_key_map.get(table_name, 'id')

                # 删除记录
                cursor.execute(f"DELETE FROM {table_name} WHERE {primary_key} = ?", (record_id,))

                if cursor.rowcount > 0:
                    self.conn.commit()
                    logger.info(f"删除表记录成功: {table_name}.{record_id}")
                    return True
                else:
                    logger.warning(f"删除表记录失败，记录不存在: {table_name}.{record_id}")
                    return False

            except Exception as e:
                logger.error(f"删除表记录失败: {table_name}.{record_id} - {e}")
                self.conn.rollback()
                return False

    def clear_table_data(self, table_name: str):
        """清空指定表的所有数据"""
        with self.lock:
            try:
                cursor = self.conn.cursor()

                # 清空表数据
                cursor.execute(f"DELETE FROM {table_name}")

                # 重置自增ID（如果有的话）
                cursor.execute(f"DELETE FROM sqlite_sequence WHERE name = ?", (table_name,))

                self.conn.commit()
                logger.info(f"清空表数据成功: {table_name}")
                return True

            except Exception as e:
                logger.error(f"清空表数据失败: {table_name} - {e}")
                self.conn.rollback()
                return False

    def upgrade_keywords_table_for_image_support(self, cursor):
        """升级keywords表以支持图片关键词"""
        try:
            logger.info("开始升级keywords表以支持图片关键词...")

            # 检查是否已经有type字段
            cursor.execute("PRAGMA table_info(keywords)")
            columns = [column[1] for column in cursor.fetchall()]

            if 'type' not in columns:
                logger.info("添加type字段到keywords表...")
                cursor.execute("ALTER TABLE keywords ADD COLUMN type TEXT DEFAULT 'text'")

            if 'image_url' not in columns:
                logger.info("添加image_url字段到keywords表...")
                cursor.execute("ALTER TABLE keywords ADD COLUMN image_url TEXT")

            # 为现有记录设置默认类型
            cursor.execute("UPDATE keywords SET type = 'text' WHERE type IS NULL")

            logger.info("keywords表升级完成")
            return True

        except Exception as e:
            logger.error(f"升级keywords表失败: {e}")
            raise
    def get_item_replay(self, item_id: str) -> Optional[Dict[str, Any]]:
        """
        根据商品ID获取商品回复信息，并返回统一格式

        Args:
            item_id (str): 商品ID

        Returns:
            Optional[Dict[str, Any]]: 商品回复信息字典（统一格式），找不到返回 None
        """
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                    SELECT reply_content FROM item_replay
                    WHERE item_id = ?
                ''', (item_id,))

                row = cursor.fetchone()
                if row:
                    (reply_content,) = row
                    return {
                        'reply_content': reply_content or ''
                    }
                return None
        except Exception as e:
            logger.error(f"获取商品回复失败: {e}")
            return None

    def get_item_reply(self, cookie_id: str, item_id: str) -> Optional[Dict[str, Any]]:
        """
        获取指定账号和商品的回复内容

        Args:
            cookie_id (str): 账号ID
            item_id (str): 商品ID

        Returns:
            Dict: 包含回复内容的字典，如果不存在返回None
        """
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                    SELECT reply_content, created_at, updated_at
                    FROM item_replay
                    WHERE cookie_id = ? AND item_id = ?
                ''', (cookie_id, item_id))

                row = cursor.fetchone()
                if row:
                    return {
                        'reply_content': row[0] or '',
                        'created_at': row[1],
                        'updated_at': row[2]
                    }
                return None
        except Exception as e:
            logger.error(f"获取指定商品回复失败: {e}")
            return None

    def update_item_reply(self, cookie_id: str, item_id: str, reply_content: str) -> bool:
        """
        更新指定cookie和item的回复内容及更新时间

        Args:
            cookie_id (str): 账号ID
            item_id (str): 商品ID
            reply_content (str): 回复内容

        Returns:
            bool: 更新成功返回True，失败返回False
        """
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                    UPDATE item_replay
                    SET reply_content = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE cookie_id = ? AND item_id = ?
                ''', (reply_content, cookie_id, item_id))

                if cursor.rowcount == 0:
                    # 如果没更新到，说明该条记录不存在，可以考虑插入
                    cursor.execute('''
                        INSERT INTO item_replay (item_id, cookie_id, reply_content, created_at, updated_at)
                        VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ''', (item_id, cookie_id, reply_content))

                self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"更新商品回复失败: {e}")
            return False

    def get_itemReplays_by_cookie(self, cookie_id: str) -> List[Dict]:
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
                SELECT r.item_id, r.cookie_id, r.reply_content, r.created_at, r.updated_at, i.item_title, i.item_detail
                    FROM item_replay r
                    LEFT JOIN item_info i ON i.item_id = r.item_id
                    WHERE r.cookie_id = ?
                    ORDER BY r.updated_at DESC
                ''', (cookie_id,))

                columns = [description[0] for description in cursor.description]
                items = []

                for row in cursor.fetchall():
                    item_info = dict(zip(columns, row))

                    items.append(item_info)

                return items

        except Exception as e:
            logger.error(f"获取Cookie商品信息失败: {e}")
            return []

    def delete_item_reply(self, cookie_id: str, item_id: str) -> bool:
        """
        删除指定 cookie_id 和 item_id 的商品回复

        Args:
            cookie_id: Cookie ID
            item_id: 商品ID

        Returns:
            bool: 删除成功返回 True，失败返回 False
        """
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                    DELETE FROM item_replay
                    WHERE cookie_id = ? AND item_id = ?
                ''', (cookie_id, item_id))
                self.conn.commit()
                # 判断是否有删除行
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"删除商品回复失败: {e}")
            return False

    def batch_delete_item_replies(self, items: List[Dict[str, str]]) -> Dict[str, int]:
        """
        批量删除商品回复

        Args:
            items: List[Dict] 每个字典包含 cookie_id 和 item_id

        Returns:
            Dict[str, int]: 返回成功和失败的数量，例如 {"success_count": 3, "failed_count": 1}
        """
        success_count = 0
        failed_count = 0

        try:
            with self.lock:
                cursor = self.conn.cursor()
                for item in items:
                    cookie_id = item.get('cookie_id')
                    item_id = item.get('item_id')
                    if not cookie_id or not item_id:
                        failed_count += 1
                        continue
                    cursor.execute('''
                        DELETE FROM item_replay
                        WHERE cookie_id = ? AND item_id = ?
                    ''', (cookie_id, item_id))
                    if cursor.rowcount > 0:
                        success_count += 1
                    else:
                        failed_count += 1
                self.conn.commit()
        except Exception as e:
            logger.error(f"批量删除商品回复失败: {e}")
            # 整体失败则视为全部失败
            return {"success_count": 0, "failed_count": len(items)}

        return {"success_count": success_count, "failed_count": failed_count}

    # ==================== 风控日志管理 ====================

    def add_risk_control_log(self, cookie_id: str, event_type: str = 'slider_captcha',
                           event_description: str = None, processing_result: str = None,
                           processing_status: str = 'processing', error_message: str = None) -> bool:
        """
        添加风控日志记录

        Args:
            cookie_id: Cookie ID
            event_type: 事件类型，默认为'slider_captcha'
            event_description: 事件描述
            processing_result: 处理结果
            processing_status: 处理状态 ('processing', 'success', 'failed')
            error_message: 错误信息

        Returns:
            bool: 添加成功返回True，失败返回False
        """
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                    INSERT INTO risk_control_logs
                    (cookie_id, event_type, event_description, processing_result, processing_status, error_message)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (cookie_id, event_type, event_description, processing_result, processing_status, error_message))
                self.conn.commit()
                return True
        except Exception as e:
            logger.error(f"添加风控日志失败: {e}")
            return False

    def update_risk_control_log(self, log_id: int, processing_result: str = None,
                              processing_status: str = None, error_message: str = None) -> bool:
        """
        更新风控日志记录

        Args:
            log_id: 日志ID
            processing_result: 处理结果
            processing_status: 处理状态
            error_message: 错误信息

        Returns:
            bool: 更新成功返回True，失败返回False
        """
        try:
            with self.lock:
                cursor = self.conn.cursor()

                # 构建更新语句
                update_fields = []
                params = []

                if processing_result is not None:
                    update_fields.append("processing_result = ?")
                    params.append(processing_result)

                if processing_status is not None:
                    update_fields.append("processing_status = ?")
                    params.append(processing_status)

                if error_message is not None:
                    update_fields.append("error_message = ?")
                    params.append(error_message)

                if update_fields:
                    update_fields.append("updated_at = CURRENT_TIMESTAMP")
                    params.append(log_id)

                    sql = f"UPDATE risk_control_logs SET {', '.join(update_fields)} WHERE id = ?"
                    cursor.execute(sql, params)
                    self.conn.commit()
                    return cursor.rowcount > 0

                return False
        except Exception as e:
            logger.error(f"更新风控日志失败: {e}")
            return False

    def get_risk_control_logs(self, cookie_id: str = None, limit: int = 100, offset: int = 0) -> List[Dict]:
        """
        获取风控日志列表

        Args:
            cookie_id: Cookie ID，为None时获取所有日志
            limit: 限制返回数量
            offset: 偏移量

        Returns:
            List[Dict]: 风控日志列表
        """
        try:
            with self.lock:
                cursor = self.conn.cursor()

                if cookie_id:
                    cursor.execute('''
                        SELECT r.*, c.id as cookie_name
                        FROM risk_control_logs r
                        LEFT JOIN cookies c ON r.cookie_id = c.id
                        WHERE r.cookie_id = ?
                        ORDER BY r.created_at DESC
                        LIMIT ? OFFSET ?
                    ''', (cookie_id, limit, offset))
                else:
                    cursor.execute('''
                        SELECT r.*, c.id as cookie_name
                        FROM risk_control_logs r
                        LEFT JOIN cookies c ON r.cookie_id = c.id
                        ORDER BY r.created_at DESC
                        LIMIT ? OFFSET ?
                    ''', (limit, offset))

                columns = [description[0] for description in cursor.description]
                logs = []

                for row in cursor.fetchall():
                    log_info = dict(zip(columns, row))
                    logs.append(log_info)

                return logs
        except Exception as e:
            logger.error(f"获取风控日志失败: {e}")
            return []

    def get_risk_control_logs_count(self, cookie_id: str = None) -> int:
        """
        获取风控日志总数

        Args:
            cookie_id: Cookie ID，为None时获取所有日志数量

        Returns:
            int: 日志总数
        """
        try:
            with self.lock:
                cursor = self.conn.cursor()

                if cookie_id:
                    cursor.execute('SELECT COUNT(*) FROM risk_control_logs WHERE cookie_id = ?', (cookie_id,))
                else:
                    cursor.execute('SELECT COUNT(*) FROM risk_control_logs')

                return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"获取风控日志数量失败: {e}")
            return 0

    def delete_risk_control_log(self, log_id: int) -> bool:
        """
        删除风控日志记录

        Args:
            log_id: 日志ID

        Returns:
            bool: 删除成功返回True，失败返回False
        """
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute('DELETE FROM risk_control_logs WHERE id = ?', (log_id,))
                self.conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"删除风控日志失败: {e}")
            return False
    
    def cleanup_old_data(self, days: int = 90) -> dict:
        """清理过期的历史数据，防止数据库无限增长
        
        Args:
            days: 保留最近N天的数据，默认90天
            
        Returns:
            清理统计信息
        """
        try:
            with self.lock:
                cursor = self.conn.cursor()
                stats = {}
                
                # 清理AI对话历史（保留最近90天）
                try:
                    cursor.execute(
                        "DELETE FROM ai_conversations WHERE created_at < datetime('now', '-' || ? || ' days')",
                        (days,)
                    )
                    stats['ai_conversations'] = cursor.rowcount
                    if cursor.rowcount > 0:
                        logger.info(f"清理了 {cursor.rowcount} 条过期的AI对话记录（{days}天前）")
                except Exception as e:
                    logger.warning(f"清理AI对话历史失败: {e}")
                    stats['ai_conversations'] = 0
                
                # 清理风控日志（保留最近90天）
                try:
                    cursor.execute(
                        "DELETE FROM risk_control_logs WHERE created_at < datetime('now', '-' || ? || ' days')",
                        (days,)
                    )
                    stats['risk_control_logs'] = cursor.rowcount
                    if cursor.rowcount > 0:
                        logger.info(f"清理了 {cursor.rowcount} 条过期的风控日志（{days}天前）")
                except Exception as e:
                    logger.warning(f"清理风控日志失败: {e}")
                    stats['risk_control_logs'] = 0
                
                # 清理AI商品缓存（保留最近30天）
                cache_days = min(days, 30)  # AI商品缓存最多保留30天
                try:
                    cursor.execute(
                        "DELETE FROM ai_item_cache WHERE last_updated < datetime('now', '-' || ? || ' days')",
                        (cache_days,)
                    )
                    stats['ai_item_cache'] = cursor.rowcount
                    if cursor.rowcount > 0:
                        logger.info(f"清理了 {cursor.rowcount} 条过期的AI商品缓存（{cache_days}天前）")
                except Exception as e:
                    logger.warning(f"清理AI商品缓存失败: {e}")
                    stats['ai_item_cache'] = 0
                
                # 清理验证码记录（保留最近1天）
                try:
                    cursor.execute(
                        "DELETE FROM captcha_codes WHERE created_at < datetime('now', '-1 day')"
                    )
                    stats['captcha_codes'] = cursor.rowcount
                    if cursor.rowcount > 0:
                        logger.info(f"清理了 {cursor.rowcount} 条过期的验证码记录")
                except Exception as e:
                    logger.warning(f"清理验证码记录失败: {e}")
                    stats['captcha_codes'] = 0
                
                # 清理邮箱验证记录（保留最近7天）
                try:
                    cursor.execute(
                        "DELETE FROM email_verifications WHERE created_at < datetime('now', '-7 days')"
                    )
                    stats['email_verifications'] = cursor.rowcount
                    if cursor.rowcount > 0:
                        logger.info(f"清理了 {cursor.rowcount} 条过期的邮箱验证记录")
                except Exception as e:
                    logger.warning(f"清理邮箱验证记录失败: {e}")
                    stats['email_verifications'] = 0
                
                # 提交更改
                self.conn.commit()
                
                # 执行VACUUM以释放磁盘空间（仅当清理了大量数据时）
                total_cleaned = sum(stats.values())
                if total_cleaned > 100:
                    logger.info(f"共清理了 {total_cleaned} 条记录，执行VACUUM以释放磁盘空间...")
                    cursor.execute("VACUUM")
                    logger.info("VACUUM执行完成")
                    stats['vacuum_executed'] = True
                else:
                    stats['vacuum_executed'] = False
                
                stats['total_cleaned'] = total_cleaned
                return stats
                
        except Exception as e:
            logger.error(f"清理历史数据时出错: {e}")
            return {'error': str(e)}

    # ==================== BI报表统计函数 ====================

    def update_order_address(self, order_id: str, receiver_address: str = None, receiver_city: str = None):
        """
        更新订单的收货地址信息

        Args:
            order_id: 订单ID
            receiver_address: 收货地址
            receiver_city: 收货城市

        Returns:
            bool: 更新是否成功
        """
        with self.lock:
            try:
                cursor = self.conn.cursor()

                update_fields = []
                update_values = []

                if receiver_address is not None:
                    update_fields.append("receiver_address = ?")
                    update_values.append(receiver_address)

                if receiver_city is not None:
                    update_fields.append("receiver_city = ?")
                    update_values.append(receiver_city)

                if update_fields:
                    update_fields.append("updated_at = CURRENT_TIMESTAMP")
                    update_values.append(order_id)

                    sql = f"UPDATE orders SET {', '.join(update_fields)} WHERE order_id = ?"
                    cursor.execute(sql, update_values)
                    self.conn.commit()

                    return cursor.rowcount > 0

                return False

            except Exception as e:
                logger.error(f"更新订单地址失败: {order_id} - {e}")
                self.conn.rollback()
                return False

    def get_orders_for_analytics(self, start_date: str = None, end_date: str = None,
                                  user_id: int = None, include_statuses: list = None):
        """
        获取用于分析的订单列表

        Args:
            start_date: 开始日期
            end_date: 结束日期
            user_id: 用户ID
            include_statuses: 要包含的订单状态列表（如果指定则只返回这些状态的订单）

        Returns:
            订单列表
        """
        with self.lock:
            try:
                cursor = self.conn.cursor()

                # 构建WHERE条件
                where_conditions = []
                params = []

                if start_date:
                    where_conditions.append("DATE(created_at) >= ?")
                    params.append(start_date)

                if end_date:
                    where_conditions.append("DATE(created_at) <= ?")
                    params.append(end_date)

                # 关联cookies表以过滤user_id
                if user_id is not None:
                    where_conditions.append("EXISTS (SELECT 1 FROM cookies WHERE cookies.id = orders.cookie_id AND cookies.user_id = ?)")
                    params.append(user_id)

                # 只包含指定状态
                if include_statuses:
                    placeholders = ','.join(['?' for _ in include_statuses])
                    where_conditions.append(f"order_status IN ({placeholders})")
                    params.extend(include_statuses)

                where_clause = f"WHERE {' AND '.join(where_conditions)}" if where_conditions else ""

                cursor.execute(f"""
                    SELECT
                        order_id,
                        item_id,
                        buyer_id,
                        amount,
                        order_status,
                        spec_name,
                        spec_value,
                        quantity,
                        created_at,
                        receiver_city
                    FROM orders
                    {where_clause}
                    ORDER BY created_at DESC
                    LIMIT 1000
                """, params)

                orders = []
                for row in cursor.fetchall():
                    orders.append({
                        'order_id': row[0],
                        'item_id': row[1],
                        'buyer_id': row[2],
                        'amount': row[3],
                        'order_status': row[4],
                        'spec_name': row[5],
                        'spec_value': row[6],
                        'quantity': row[7],
                        'created_at': row[8],
                        'receiver_city': row[9]
                    })

                return orders

            except Exception as e:
                logger.error(f"获取订单列表失败: {e}")
                return []


    # ---- Session 持久化 ----
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

    def get_ai_conversations(self, cookie_id: str = None, chat_id: str = None, buyer_id: str = None,
                             page: int = 1, page_size: int = 20) -> dict:
        """获取AI对话历史"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                conditions = []
                params = []
                if cookie_id:
                    conditions.append('cookie_id = ?')
                    params.append(cookie_id)
                if chat_id:
                    conditions.append('chat_id = ?')
                    params.append(chat_id)
                if buyer_id:
                    conditions.append('user_id = ?')
                    params.append(buyer_id)
                
                where = ' WHERE ' + ' AND '.join(conditions) if conditions else ''
                
                cursor.execute(f'SELECT COUNT(*) FROM ai_conversations {where}', params)
                total = cursor.fetchone()[0]
                
                offset = (page - 1) * page_size
                cursor.execute(f'''
                    SELECT * FROM ai_conversations {where}
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
            logger.error(f"获取AI对话历史失败: {e}")
            return {'data': [], 'total': 0, 'page': page, 'page_size': page_size}

    def get_ai_conversation_chats(self, cookie_id: str = None) -> list:
        """获取有对话的chat_id列表（用于筛选）"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                if cookie_id:
                    cursor.execute('''
                        SELECT DISTINCT chat_id, user_id, COUNT(*) as msg_count, 
                               MAX(created_at) as last_msg
                        FROM ai_conversations WHERE cookie_id = ?
                        GROUP BY chat_id ORDER BY last_msg DESC LIMIT 50
                    ''', (cookie_id,))
                else:
                    cursor.execute('''
                        SELECT DISTINCT chat_id, user_id, COUNT(*) as msg_count,
                               MAX(created_at) as last_msg
                        FROM ai_conversations
                        GROUP BY chat_id ORDER BY last_msg DESC LIMIT 50
                    ''')
                rows = cursor.fetchall()
                columns = ['chat_id', 'buyer_id', 'msg_count', 'last_msg']
                return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            logger.error(f"获取对话列表失败: {e}")
            return []

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

    def add_item_schedule(self, cookie_id: str, item_id: str, item_title: str,
                          schedule_type: str, schedule_time: str = '', cron_expression: str = '') -> int:
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO item_schedule (cookie_id, item_id, item_title, schedule_type, schedule_time, cron_expression)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (cookie_id, item_id, item_title, schedule_type, schedule_time, cron_expression))
            self.conn.commit()
            return cursor.lastrowid

    def update_item_schedule(self, schedule_id: int, data: dict) -> bool:
        with self.lock:
            cursor = self.conn.cursor()
            fields = []
            params = []
            for key in ['schedule_time', 'cron_expression', 'enabled', 'schedule_type']:
                if key in data:
                    fields.append(f'{key} = ?')
                    params.append(data[key])
            if not fields:
                return False
            fields.append('updated_at = CURRENT_TIMESTAMP')
            params.append(schedule_id)
            cursor.execute(f"UPDATE item_schedule SET {', '.join(fields)} WHERE id = ?", params)
            self.conn.commit()
            return True

    def get_pending_schedules(self) -> list:
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT * FROM item_schedule
                WHERE enabled = 1
                AND schedule_time IS NOT NULL
                AND schedule_time != ''
                AND schedule_time <= datetime('now', 'localtime')
                AND (last_run_at IS NULL OR last_run_at < schedule_time)
            ''')
            rows = cursor.fetchall()
            columns = [d[0] for d in cursor.description]
            return [dict(zip(columns, row)) for row in rows]

    def mark_schedule_run(self, schedule_id: int) -> bool:
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute('UPDATE item_schedule SET last_run_at = CURRENT_TIMESTAMP WHERE id = ?', (schedule_id,))
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

    def get_active_outreach_history(self, cookie_id: str = None, page: int = 1,
                                     page_size: int = 20) -> dict:
        """获取主动询价历史记录"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                where = ''
                params = []
                if cookie_id:
                    where = ' WHERE cookie_id = ?'
                    params.append(cookie_id)
                cursor.execute(f'SELECT COUNT(*) FROM active_outreach{where}', params)
                total = cursor.fetchone()[0]
                offset = (page - 1) * page_size
                cursor.execute(f'''
                    SELECT id, cookie_id, item_url, item_title, seller_id, seller_name,
                           chat_id, message, reply, status, error_message, created_at, updated_at
                    FROM active_outreach{where}
                    ORDER BY created_at DESC LIMIT ? OFFSET ?
                ''', params + [page_size, offset])
                rows = cursor.fetchall()
                data = []
                for row in rows:
                    data.append({
                        'id': row[0], 'cookie_id': row[1], 'item_url': row[2],
                        'item_title': row[3], 'seller_id': row[4], 'seller_name': row[5],
                        'chat_id': row[6], 'message': row[7], 'reply': row[8],
                        'status': row[9], 'error_message': row[10],
                        'created_at': row[11], 'updated_at': row[12]
                    })
                return {'data': data, 'total': total, 'page': page, 'page_size': page_size}
        except Exception as e:
            logger.error(f"获取主动询价历史失败: {e}")
            return {'data': [], 'total': 0, 'page': page, 'page_size': page_size}


    def add_bargain_session(self, cookie_id: str, item_url: str, item_id: str = '',
                            item_title: str = '', seller_id: str = '', seller_name: str = '',
                            target_price: float = 0, initial_message: str = '',
                            chat_id: str = '', status: str = 'pending',
                            max_rounds: int = 5) -> int:
        """添加砍价会话"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                    INSERT INTO bargain_sessions (cookie_id, item_url, item_id, item_title,
                        seller_id, seller_name, target_price, initial_message, chat_id,
                        status, max_rounds)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (cookie_id, item_url, item_id, item_title, seller_id, seller_name,
                      target_price, initial_message, chat_id, status, max_rounds))
                self.conn.commit()
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"添加砍价会话失败: {e}")
            return -1

    def update_bargain_session(self, session_id: int, **kwargs):
        """更新砍价会话"""
        try:
            if not kwargs:
                return
            with self.lock:
                cursor = self.conn.cursor()
                fields = []
                values = []
                for key, value in kwargs.items():
                    fields.append(f'{key} = ?')
                    values.append(value)
                fields.append('updated_at = CURRENT_TIMESTAMP')
                values.append(session_id)
                cursor.execute(f'''
                    UPDATE bargain_sessions SET {', '.join(fields)}
                    WHERE id = ?
                ''', values)
                self.conn.commit()
        except Exception as e:
            logger.error(f"更新砍价会话失败: {e}")

    def get_bargain_session(self, session_id: int) -> Optional[dict]:
        """获取砍价会话详情"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                    SELECT id, cookie_id, item_url, item_id, item_title, seller_id,
                           seller_name, chat_id, target_price, current_round, max_rounds,
                           initial_message, last_seller_message, last_buyer_message,
                           status, result_price, created_at, updated_at
                    FROM bargain_sessions WHERE id = ?
                ''', (session_id,))
                row = cursor.fetchone()
                if not row:
                    return None
                return {
                    'id': row[0], 'cookie_id': row[1], 'item_url': row[2],
                    'item_id': row[3], 'item_title': row[4], 'seller_id': row[5],
                    'seller_name': row[6], 'chat_id': row[7], 'target_price': row[8],
                    'current_round': row[9], 'max_rounds': row[10],
                    'initial_message': row[11], 'last_seller_message': row[12],
                    'last_buyer_message': row[13], 'status': row[14],
                    'result_price': row[15], 'created_at': row[16], 'updated_at': row[17]
                }
        except Exception as e:
            logger.error(f"获取砍价会话失败: {e}")
            return None

    def get_active_bargain_sessions(self, cookie_id: str = None) -> List[dict]:
        """获取活跃的砍价会话"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                if cookie_id:
                    cursor.execute('''
                        SELECT id, cookie_id, item_url, item_id, item_title, seller_id,
                               seller_name, chat_id, target_price, current_round, max_rounds,
                               initial_message, last_seller_message, last_buyer_message,
                               status, result_price, created_at, updated_at
                        FROM bargain_sessions
                        WHERE status IN ('pending', 'sending', 'active') AND cookie_id = ?
                        ORDER BY created_at DESC
                    ''', (cookie_id,))
                else:
                    cursor.execute('''
                        SELECT id, cookie_id, item_url, item_id, item_title, seller_id,
                               seller_name, chat_id, target_price, current_round, max_rounds,
                               initial_message, last_seller_message, last_buyer_message,
                               status, result_price, created_at, updated_at
                        FROM bargain_sessions
                        WHERE status IN ('pending', 'sending', 'active')
                        ORDER BY created_at DESC
                    ''')
                rows = cursor.fetchall()
                return [{
                    'id': r[0], 'cookie_id': r[1], 'item_url': r[2],
                    'item_id': r[3], 'item_title': r[4], 'seller_id': r[5],
                    'seller_name': r[6], 'chat_id': r[7], 'target_price': r[8],
                    'current_round': r[9], 'max_rounds': r[10],
                    'initial_message': r[11], 'last_seller_message': r[12],
                    'last_buyer_message': r[13], 'status': r[14],
                    'result_price': r[15], 'created_at': r[16], 'updated_at': r[17]
                } for r in rows]
        except Exception as e:
            logger.error(f"获取活跃砍价会话失败: {e}")
            return []

    def get_bargain_history(self, cookie_id: str = None, page: int = 1,
                            page_size: int = 20) -> dict:
        """获取砍价历史记录"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                where = ''
                params = []
                if cookie_id:
                    where = ' WHERE cookie_id = ?'
                    params.append(cookie_id)
                cursor.execute(f'SELECT COUNT(*) FROM bargain_sessions{where}', params)
                total = cursor.fetchone()[0]
                offset = (page - 1) * page_size
                cursor.execute(f'''
                    SELECT id, cookie_id, item_url, item_id, item_title, seller_id,
                           seller_name, chat_id, target_price, current_round, max_rounds,
                           initial_message, last_seller_message, last_buyer_message,
                           status, result_price, created_at, updated_at
                    FROM bargain_sessions{where}
                    ORDER BY created_at DESC LIMIT ? OFFSET ?
                ''', params + [page_size, offset])
                rows = cursor.fetchall()
                data = []
                for r in rows:
                    data.append({
                        'id': r[0], 'cookie_id': r[1], 'item_url': r[2],
                        'item_id': r[3], 'item_title': r[4], 'seller_id': r[5],
                        'seller_name': r[6], 'chat_id': r[7], 'target_price': r[8],
                        'current_round': r[9], 'max_rounds': r[10],
                        'initial_message': r[11], 'last_seller_message': r[12],
                        'last_buyer_message': r[13], 'status': r[14],
                        'result_price': r[15], 'created_at': r[16], 'updated_at': r[17]
                    })
                return {'data': data, 'total': total, 'page': page, 'page_size': page_size}
        except Exception as e:
            logger.error(f"获取砍价历史失败: {e}")
            return {'data': [], 'total': 0, 'page': page, 'page_size': page_size}


