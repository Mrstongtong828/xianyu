"""
Item Mixin - 商品信息管理
"""
import sqlite3
import json
import time
import secrets
from typing import Optional, Dict, Any, List, Tuple
from loguru import logger


class ItemManagerMixin:
    """商品信息管理"""

    def save_keywords_with_item_id(self, cookie_id: str, keywords: List[Tuple[str, str, str]]) -> bool:
        """保存关键字列表（包含商品ID），先删除旧数据再插入新数据"""
        with self.lock:
            try:
                cursor = self.conn.cursor()

                # 先删除该cookie_id的所有关键字
                self._execute_sql(cursor, "DELETE FROM keywords WHERE cookie_id = ?", (cookie_id,))

                # 插入新关键字，使用INSERT OR REPLACE来处理可能的唯一约束冲突
                for keyword, reply, item_id in keywords:
                    # 标准化item_id：空字符串转为NULL
                    normalized_item_id = item_id if item_id and item_id.strip() else None

                    try:
                        self._execute_sql(cursor,
                            "INSERT INTO keywords (cookie_id, keyword, reply, item_id) VALUES (?, ?, ?, ?)",
                            (cookie_id, keyword, reply, normalized_item_id))
                    except sqlite3.IntegrityError as ie:
                        # 如果遇到唯一约束冲突，记录详细错误信息
                        item_desc = f"商品ID: {normalized_item_id}" if normalized_item_id else "通用关键词"
                        logger.error(f"关键词唯一约束冲突: Cookie={cookie_id}, 关键词='{keyword}', {item_desc}")
                        raise ie

                self.conn.commit()
                logger.info(f"关键字保存成功: {cookie_id}, {len(keywords)}条")
                return True
            except Exception as e:
                logger.error(f"关键字保存失败: {e}")
                self.conn.rollback()
                return False



    def get_keywords_with_item_id(self, cookie_id: str) -> List[Tuple[str, str, str]]:
        """获取指定Cookie的关键字列表（包含商品ID）"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                self._execute_sql(cursor, "SELECT keyword, reply, item_id FROM keywords WHERE cookie_id = ?", (cookie_id,))
                return [(row[0], row[1], row[2]) for row in cursor.fetchall()]
            except Exception as e:
                logger.error(f"获取关键字失败: {e}")
                return []



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
                    logger.info(f"item_info: {item_info}")
                    return item_info
                return None

        except Exception as e:
            logger.error(f"获取商品信息失败: {e}")
            return None



    def update_item_multi_spec_status(self, cookie_id: str, item_id: str, is_multi_spec: bool) -> bool:
        """更新商品的多规格状态"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                UPDATE item_info
                SET is_multi_spec = ?, updated_at = CURRENT_TIMESTAMP
                WHERE cookie_id = ? AND item_id = ?
                ''', (is_multi_spec, cookie_id, item_id))

                if cursor.rowcount > 0:
                    self.conn.commit()
                    logger.info(f"更新商品多规格状态成功: {item_id} -> {is_multi_spec}")
                    return True
                else:
                    logger.warning(f"商品不存在，无法更新多规格状态: {item_id}")
                    return False

        except Exception as e:
            logger.error(f"更新商品多规格状态失败: {e}")
            self.conn.rollback()
            return False



    def get_item_multi_spec_status(self, cookie_id: str, item_id: str) -> bool:
        """获取商品的多规格状态"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                SELECT is_multi_spec FROM item_info
                WHERE cookie_id = ? AND item_id = ?
                ''', (cookie_id, item_id))

                row = cursor.fetchone()
                if row:
                    return bool(row[0]) if row[0] is not None else False
                return False

        except Exception as e:
            logger.error(f"获取商品多规格状态失败: {e}")
            return False



    def update_item_multi_quantity_delivery_status(self, cookie_id: str, item_id: str, multi_quantity_delivery: bool) -> bool:
        """更新商品的多数量发货状态"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                UPDATE item_info
                SET multi_quantity_delivery = ?, updated_at = CURRENT_TIMESTAMP
                WHERE cookie_id = ? AND item_id = ?
                ''', (multi_quantity_delivery, cookie_id, item_id))

                if cursor.rowcount > 0:
                    self.conn.commit()
                    logger.info(f"更新商品多数量发货状态成功: {item_id} -> {multi_quantity_delivery}")
                    return True
                else:
                    logger.warning(f"未找到要更新的商品: {item_id}")
                    return False

        except Exception as e:
            logger.error(f"更新商品多数量发货状态失败: {e}")
            self.conn.rollback()
            return False



    def get_item_multi_quantity_delivery_status(self, cookie_id: str, item_id: str) -> bool:
        """获取商品的多数量发货状态"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                SELECT multi_quantity_delivery FROM item_info
                WHERE cookie_id = ? AND item_id = ?
                ''', (cookie_id, item_id))

                row = cursor.fetchone()
                if row:
                    return bool(row[0]) if row[0] is not None else False
                return False

        except Exception as e:
            logger.error(f"获取商品多数量发货状态失败: {e}")
            return False



    def get_all_items(self) -> List[Dict]:
        """获取所有商品信息

        Returns:
            List[Dict]: 所有商品信息列表
        """
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                SELECT * FROM item_info
                ORDER BY updated_at DESC
                ''')

                columns = [description[0] for description in cursor.description]
                items = []

                for row in cursor.fetchall():
                    item_info = dict(zip(columns, row))

                    # 解析item_detail JSON
                    if item_info.get('item_detail'):
                        try:
                            item_info['item_detail_parsed'] = json.loads(item_info['item_detail'])
                        except:
                            item_info['item_detail_parsed'] = {}

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
                cursor = self.conn.cursor()
                # 只更新item_detail字段，不影响其他字段
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
                                item_detail = CASE WHEN (item_detail IS NULL OR item_detail = '' OR TRIM(item_detail) = '') AND ? != '' THEN ? ELSE item_detail END,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE cookie_id = ? AND item_id = ?
                            '''
                            self._execute_sql(cursor, update_sql, (
                                item_title, item_title,
                                item_description, item_description,
                                item_category, item_category,
                                item_price, item_price,
                                item_detail, item_detail,
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



    def delete_item_schedule(self, schedule_id: int) -> bool:
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute('DELETE FROM item_schedule WHERE id = ?', (schedule_id,))
            self.conn.commit()
            return True

