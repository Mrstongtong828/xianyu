"""
Keyword Mixin - 关键字和自动回复管理
"""
import sqlite3
import json
import time
import secrets
from typing import Optional, Dict, Any, List, Tuple
from loguru import logger


class KeywordManagerMixin:
    """关键字和自动回复管理"""

    def save_keywords(self, cookie_id: str, keywords: List[Tuple[str, str]]) -> bool:
        """保存关键字列表，先删除旧数据再插入新数据（向后兼容方法）"""
        # 转换为新格式（不包含item_id）
        keywords_with_item_id = [(keyword, reply, None) for keyword, reply in keywords]
        return self.save_keywords_with_item_id(cookie_id, keywords_with_item_id)



    def save_text_keywords_only(self, cookie_id: str, keywords: List[Tuple[str, str, str]]) -> bool:
        """保存文本关键字列表，只删除文本类型的关键词，保留图片关键词"""
        with self.lock:
            try:
                cursor = self.conn.cursor()

                # 检查是否与现有图片关键词冲突
                for keyword, reply, item_id in keywords:
                    normalized_item_id = item_id if item_id and item_id.strip() else None

                    # 检查是否存在同名的图片关键词
                    if normalized_item_id:
                        # 有商品ID的情况：检查 (cookie_id, keyword, item_id) 是否存在图片关键词
                        self._execute_sql(cursor,
                            "SELECT type FROM keywords WHERE cookie_id = ? AND keyword = ? AND item_id = ? AND type = 'image'",
                            (cookie_id, keyword, normalized_item_id))
                    else:
                        # 通用关键词的情况：检查 (cookie_id, keyword) 是否存在图片关键词
                        self._execute_sql(cursor,
                            "SELECT type FROM keywords WHERE cookie_id = ? AND keyword = ? AND (item_id IS NULL OR item_id = '') AND type = 'image'",
                            (cookie_id, keyword))

                    if cursor.fetchone():
                        # 存在同名图片关键词，抛出友好的错误信息
                        item_desc = f"商品ID: {normalized_item_id}" if normalized_item_id else "通用关键词"
                        error_msg = f"关键词 '{keyword}' （{item_desc}） 已存在（图片关键词），无法保存为文本关键词"
                        logger.warning(f"文本关键词与图片关键词冲突: Cookie={cookie_id}, 关键词='{keyword}', {item_desc}")
                        raise ValueError(error_msg)

                # 只删除该cookie_id的文本类型关键字，保留图片关键词
                self._execute_sql(cursor,
                    "DELETE FROM keywords WHERE cookie_id = ? AND (type IS NULL OR type = 'text')",
                    (cookie_id,))

                # 插入新的文本关键字
                for keyword, reply, item_id in keywords:
                    # 标准化item_id：空字符串转为NULL
                    normalized_item_id = item_id if item_id and item_id.strip() else None

                    self._execute_sql(cursor,
                        "INSERT INTO keywords (cookie_id, keyword, reply, item_id, type) VALUES (?, ?, ?, ?, 'text')",
                        (cookie_id, keyword, reply, normalized_item_id))

                self.conn.commit()
                logger.info(f"文本关键字保存成功: {cookie_id}, {len(keywords)}条，图片关键词已保留")
                return True
            except ValueError:
                # 重新抛出友好的错误信息
                raise
            except Exception as e:
                logger.error(f"文本关键字保存失败: {e}")
                self.conn.rollback()
                return False
    


    def get_keywords(self, cookie_id: str) -> List[Tuple[str, str]]:
        """获取指定Cookie的关键字列表（向后兼容方法）"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                self._execute_sql(cursor, "SELECT keyword, reply FROM keywords WHERE cookie_id = ?", (cookie_id,))
                return [(row[0], row[1]) for row in cursor.fetchall()]
            except Exception as e:
                logger.error(f"获取关键字失败: {e}")
                return []



    def check_keyword_duplicate(self, cookie_id: str, keyword: str, item_id: str = None) -> bool:
        """检查关键词是否重复"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                if item_id:
                    # 如果有商品ID，检查相同cookie_id、keyword、item_id的组合
                    self._execute_sql(cursor,
                        "SELECT COUNT(*) FROM keywords WHERE cookie_id = ? AND keyword = ? AND item_id = ?",
                        (cookie_id, keyword, item_id))
                else:
                    # 如果没有商品ID，检查相同cookie_id、keyword且item_id为空的组合
                    self._execute_sql(cursor,
                        "SELECT COUNT(*) FROM keywords WHERE cookie_id = ? AND keyword = ? AND (item_id IS NULL OR item_id = '')",
                        (cookie_id, keyword))

                count = cursor.fetchone()[0]
                return count > 0
            except Exception as e:
                logger.error(f"检查关键词重复失败: {e}")
                return False



    def save_image_keyword(self, cookie_id: str, keyword: str, image_url: str, item_id: str = None) -> bool:
        """保存图片关键词（调用前应先检查重复）"""
        with self.lock:
            try:
                cursor = self.conn.cursor()

                # 标准化item_id：空字符串转为NULL
                normalized_item_id = item_id if item_id and item_id.strip() else None

                # 直接插入图片关键词（重复检查应在调用前完成）
                self._execute_sql(cursor,
                    "INSERT INTO keywords (cookie_id, keyword, reply, item_id, type, image_url) VALUES (?, ?, ?, ?, ?, ?)",
                    (cookie_id, keyword, '', normalized_item_id, 'image', image_url))

                self.conn.commit()
                logger.info(f"图片关键词保存成功: {cookie_id}, 关键词: {keyword}, 图片: {image_url}")
                return True
            except Exception as e:
                logger.error(f"图片关键词保存失败: {e}")
                self.conn.rollback()
                return False



    def get_keywords_with_type(self, cookie_id: str) -> List[Dict[str, any]]:
        """获取指定Cookie的关键字列表（包含类型信息）"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                self._execute_sql(cursor,
                    "SELECT keyword, reply, item_id, type, image_url FROM keywords WHERE cookie_id = ?",
                    (cookie_id,))

                results = []
                for row in cursor.fetchall():
                    keyword_data = {
                        'keyword': row[0],
                        'reply': row[1],
                        'item_id': row[2],
                        'type': row[3] or 'text',  # 默认为text类型
                        'image_url': row[4]
                    }
                    results.append(keyword_data)

                return results
            except Exception as e:
                logger.error(f"获取关键字失败: {e}")
                return []



    def update_keyword_image_url(self, cookie_id: str, keyword: str, new_image_url: str) -> bool:
        """更新关键词的图片URL"""
        with self.lock:
            try:
                cursor = self.conn.cursor()

                # 更新图片URL
                self._execute_sql(cursor,
                    "UPDATE keywords SET image_url = ? WHERE cookie_id = ? AND keyword = ? AND type = 'image'",
                    (new_image_url, cookie_id, keyword))

                self.conn.commit()

                # 检查是否有行被更新
                if cursor.rowcount > 0:
                    logger.info(f"关键词图片URL更新成功: {cookie_id}, 关键词: {keyword}, 新URL: {new_image_url}")
                    return True
                else:
                    logger.warning(f"未找到匹配的图片关键词: {cookie_id}, 关键词: {keyword}")
                    return False

            except Exception as e:
                logger.error(f"更新关键词图片URL失败: {e}")
                self.conn.rollback()
                return False



    def delete_keyword_by_index(self, cookie_id: str, index: int) -> bool:
        """根据索引删除关键词"""
        with self.lock:
            try:
                cursor = self.conn.cursor()

                # 先获取所有关键词
                self._execute_sql(cursor,
                    "SELECT rowid FROM keywords WHERE cookie_id = ? ORDER BY rowid",
                    (cookie_id,))
                rows = cursor.fetchall()

                if 0 <= index < len(rows):
                    rowid = rows[index][0]
                    self._execute_sql(cursor, "DELETE FROM keywords WHERE rowid = ?", (rowid,))
                    self.conn.commit()
                    logger.info(f"删除关键词成功: {cookie_id}, 索引: {index}")
                    return True
                else:
                    logger.warning(f"关键词索引超出范围: {index}")
                    return False

            except Exception as e:
                logger.error(f"删除关键词失败: {e}")
                self.conn.rollback()
                return False




    def get_all_keywords(self, user_id: int = None) -> Dict[str, List[Tuple[str, str]]]:
        """获取所有Cookie的关键字（支持用户隔离）"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                if user_id is not None:
                    cursor.execute("""
                    SELECT k.cookie_id, k.keyword, k.reply
                    FROM keywords k
                    JOIN cookies c ON k.cookie_id = c.id
                    WHERE c.user_id = ?
                    """, (user_id,))
                else:
                    self._execute_sql(cursor, "SELECT cookie_id, keyword, reply FROM keywords")

                result = {}
                for row in cursor.fetchall():
                    cookie_id, keyword, reply = row
                    if cookie_id not in result:
                        result[cookie_id] = []
                    result[cookie_id].append((keyword, reply))

                return result
            except Exception as e:
                logger.error(f"获取所有关键字失败: {e}")
                return {}



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
