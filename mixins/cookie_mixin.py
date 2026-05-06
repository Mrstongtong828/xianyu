"""
Cookie Mixin - Cookie 账号管理
"""
import sqlite3
import json
import time
import secrets
from typing import Optional, Dict, Any, List, Tuple
from loguru import logger
from utils.crypto import decrypt_value


class CookieManagerMixin:
    """Cookie 账号管理"""

    def upgrade_cookies_table_for_account_login(self, cursor):
        """升级cookies表支持账号密码登录功能"""
        try:
            logger.info("开始为cookies表添加账号登录相关字段...")

            # 为cookies表添加username字段（如果不存在）
            try:
                self._execute_sql(cursor, "SELECT username FROM cookies LIMIT 1")
                logger.info("cookies表username字段已存在")
            except sqlite3.OperationalError:
                # username字段不存在，需要添加
                self._execute_sql(cursor, "ALTER TABLE cookies ADD COLUMN username TEXT DEFAULT ''")
                logger.info("为cookies表添加username字段")

            # 为cookies表添加password字段（如果不存在）
            try:
                self._execute_sql(cursor, "SELECT password FROM cookies LIMIT 1")
                logger.info("cookies表password字段已存在")
            except sqlite3.OperationalError:
                # password字段不存在，需要添加
                self._execute_sql(cursor, "ALTER TABLE cookies ADD COLUMN password TEXT DEFAULT ''")
                logger.info("为cookies表添加password字段")

            # 为cookies表添加show_browser字段（如果不存在）
            try:
                self._execute_sql(cursor, "SELECT show_browser FROM cookies LIMIT 1")
                logger.info("cookies表show_browser字段已存在")
            except sqlite3.OperationalError:
                # show_browser字段不存在，需要添加
                self._execute_sql(cursor, "ALTER TABLE cookies ADD COLUMN show_browser INTEGER DEFAULT 0")
                logger.info("为cookies表添加show_browser字段")

            logger.info("✅ cookies表账号登录字段升级完成")
            logger.info("   - username: 用于密码登录的用户名")
            logger.info("   - password: 用于密码登录的密码")
            logger.info("   - show_browser: 登录时是否显示浏览器（0=隐藏，1=显示）")
            return True
        except Exception as e:
            logger.error(f"升级cookies表账号登录字段失败: {e}")
            raise



    def save_cookie(self, cookie_id: str, cookie_value: str, user_id: int = None) -> bool:
        """保存Cookie到数据库，如存在则更新"""
        with self.lock:
            try:
                cursor = self.conn.cursor()

                # 如果没有提供user_id，尝试从现有记录获取，否则使用admin用户ID
                if user_id is None:
                    self._execute_sql(cursor, "SELECT user_id FROM cookies WHERE id = ?", (cookie_id,))
                    existing = cursor.fetchone()
                    if existing:
                        user_id = existing[0]
                    else:
                        # 获取admin用户ID作为默认值
                        self._execute_sql(cursor, "SELECT id FROM users WHERE username = 'admin'")
                        admin_user = cursor.fetchone()
                        user_id = admin_user[0] if admin_user else 1

                self._execute_sql(cursor,
                    "INSERT OR REPLACE INTO cookies (id, value, user_id) VALUES (?, ?, ?)",
                    (cookie_id, cookie_value, user_id)
                )

                self.conn.commit()
                logger.info(f"Cookie保存成功: {cookie_id} (用户ID: {user_id})")

                # 验证保存结果
                self._execute_sql(cursor, "SELECT user_id FROM cookies WHERE id = ?", (cookie_id,))
                saved_user_id = cursor.fetchone()
                if saved_user_id:
                    logger.info(f"Cookie保存验证: {cookie_id} 实际绑定到用户ID: {saved_user_id[0]}")
                else:
                    logger.error(f"Cookie保存验证失败: {cookie_id} 未找到记录")
                return True
            except Exception as e:
                logger.error(f"Cookie保存失败: {e}")
                self.conn.rollback()
                return False

    


    def delete_cookie(self, cookie_id: str) -> bool:
        """从数据库删除Cookie及其关键字"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                # 删除关联的关键字
                self._execute_sql(cursor, "DELETE FROM keywords WHERE cookie_id = ?", (cookie_id,))
                # 删除Cookie
                self._execute_sql(cursor, "DELETE FROM cookies WHERE id = ?", (cookie_id,))
                self.conn.commit()
                logger.debug(f"Cookie删除成功: {cookie_id}")
                return True
            except Exception as e:
                logger.error(f"Cookie删除失败: {e}")
                self.conn.rollback()
                return False
    


    def get_cookie(self, cookie_id: str) -> Optional[str]:
        """获取指定Cookie值"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                self._execute_sql(cursor, "SELECT value FROM cookies WHERE id = ?", (cookie_id,))
                result = cursor.fetchone()
                return result[0] if result else None
            except Exception as e:
                logger.error(f"获取Cookie失败: {e}")
                return None
    


    def get_all_cookies(self, user_id: int = None) -> Dict[str, str]:
        """获取所有Cookie（支持用户隔离）"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                if user_id is not None:
                    self._execute_sql(cursor, "SELECT id, value FROM cookies WHERE user_id = ?", (user_id,))
                else:
                    self._execute_sql(cursor, "SELECT id, value FROM cookies")
                return {row[0]: row[1] for row in cursor.fetchall()}
            except Exception as e:
                logger.error(f"获取所有Cookie失败: {e}")
                return {}





    def get_cookie_by_id(self, cookie_id: str) -> Optional[Dict[str, str]]:
        """根据ID获取Cookie信息

        Args:
            cookie_id: Cookie ID

        Returns:
            Dict包含cookie信息，包括cookies_str字段，如果不存在返回None
        """
        with self.lock:
            try:
                cursor = self.conn.cursor()
                self._execute_sql(cursor, "SELECT id, value, user_id, created_at FROM cookies WHERE id = ?", (cookie_id,))
                result = cursor.fetchone()
                if result:
                    return {
                        'id': result[0],
                        'cookies_str': result[1],  # 使用cookies_str字段名以匹配调用方期望
                        'value': result[1],        # 保持向后兼容
                        'user_id': result[2],
                        'created_at': result[3]
                    }
                return None
            except Exception as e:
                logger.error(f"根据ID获取Cookie失败: {e}")
                return None



    def get_cookie_details(self, cookie_id: str) -> Optional[Dict[str, any]]:
        """获取Cookie的详细信息，包括user_id、auto_confirm、remark、pause_duration、username、password和show_browser"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                self._execute_sql(cursor, "SELECT id, value, user_id, auto_confirm, remark, pause_duration, username, password, show_browser, created_at FROM cookies WHERE id = ?", (cookie_id,))
                result = cursor.fetchone()
                if result:
                    return {
                        'id': result[0],
                        'value': result[1],
                        'user_id': result[2],
                        'auto_confirm': bool(result[3]),
                        'remark': result[4] or '',
                        'pause_duration': result[5] if result[5] is not None else 10,  # 0是有效值，表示不暂停
                        'username': result[6] or '',
                        'password': decrypt_value(result[7]) if result[7] else '',
                        'show_browser': bool(result[8]) if result[8] is not None else False,
                        'created_at': result[9]
                    }
                return None
            except Exception as e:
                logger.error(f"获取Cookie详细信息失败: {e}")
                return None



    def update_cookie_remark(self, cookie_id: str, remark: str) -> bool:
        """更新Cookie的备注"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                self._execute_sql(cursor, "UPDATE cookies SET remark = ? WHERE id = ?", (remark, cookie_id))
                self.conn.commit()
                logger.info(f"更新账号 {cookie_id} 备注: {remark}")
                return True
            except Exception as e:
                logger.error(f"更新账号备注失败: {e}")
                return False



    def update_cookie_pause_duration(self, cookie_id: str, pause_duration: int) -> bool:
        """更新Cookie的自动回复暂停时间"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                self._execute_sql(cursor, "UPDATE cookies SET pause_duration = ? WHERE id = ?", (pause_duration, cookie_id))
                self.conn.commit()
                logger.info(f"更新账号 {cookie_id} 自动回复暂停时间: {pause_duration}分钟")
                return True
            except Exception as e:
                logger.error(f"更新账号自动回复暂停时间失败: {e}")
                return False



    def get_cookie_pause_duration(self, cookie_id: str) -> int:
        """获取Cookie的自动回复暂停时间"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                self._execute_sql(cursor, "SELECT pause_duration FROM cookies WHERE id = ?", (cookie_id,))
                result = cursor.fetchone()
                if result:
                    if result[0] is None:
                        logger.warning(f"账号 {cookie_id} 的pause_duration为NULL，使用默认值10分钟并修复数据库")
                        # 修复数据库中的NULL值
                        self._execute_sql(cursor, "UPDATE cookies SET pause_duration = 10 WHERE id = ?", (cookie_id,))
                        self.conn.commit()
                        return 10
                    return result[0]  # 返回实际值，包括0（0表示不暂停）
                else:
                    logger.warning(f"账号 {cookie_id} 未找到记录，使用默认值10分钟")
                    return 10
            except Exception as e:
                logger.error(f"获取账号自动回复暂停时间失败: {e}")
                return 10



    def update_cookie_account_info(self, cookie_id: str, cookie_value: str = None, username: str = None, password: str = None, show_browser: bool = None, user_id: int = None) -> bool:
        """更新Cookie的账号信息（包括cookie值、用户名、密码和显示浏览器设置）
        如果记录不存在，会先创建记录（需要提供cookie_value和user_id）
        """
        with self.lock:
            try:
                cursor = self.conn.cursor()
                
                # 检查记录是否存在
                self._execute_sql(cursor, "SELECT id FROM cookies WHERE id = ?", (cookie_id,))
                exists = cursor.fetchone() is not None
                
                if not exists:
                    # 记录不存在，需要创建新记录
                    if cookie_value is None:
                        logger.warning(f"账号 {cookie_id} 不存在，且未提供cookie_value，无法创建新记录")
                        return False
                    
                    # 如果没有提供user_id，尝试从现有记录获取，否则使用admin用户ID
                    if user_id is None:
                        # 获取admin用户ID作为默认值
                        self._execute_sql(cursor, "SELECT id FROM users WHERE username = 'admin'")
                        admin_user = cursor.fetchone()
                        user_id = admin_user[0] if admin_user else 1
                    
                    # 构建插入语句
                    insert_fields = ['id', 'value', 'user_id']
                    insert_values = [cookie_id, cookie_value, user_id]
                    insert_placeholders = ['?', '?', '?']
                    
                    if username is not None:
                        insert_fields.append('username')
                        insert_values.append(username)
                        insert_placeholders.append('?')
                    
                    if password is not None:
                        insert_fields.append('password')
                        insert_values.append(encrypt_value(password))
                        insert_placeholders.append('?')
                    
                    if show_browser is not None:
                        insert_fields.append('show_browser')
                        insert_values.append(1 if show_browser else 0)
                        insert_placeholders.append('?')
                    
                    sql = f"INSERT INTO cookies ({', '.join(insert_fields)}) VALUES ({', '.join(insert_placeholders)})"
                    self._execute_sql(cursor, sql, tuple(insert_values))
                    self.conn.commit()
                    logger.info(f"创建新账号 {cookie_id} 并保存信息成功: {insert_fields}")
                    return True
                else:
                    # 记录存在，执行更新
                    # 构建动态SQL更新语句
                    update_fields = []
                    params = []
                    
                    if cookie_value is not None:
                        update_fields.append("value = ?")
                        params.append(cookie_value)
                    
                    if username is not None:
                        update_fields.append("username = ?")
                        params.append(username)
                    
                    if password is not None:
                        update_fields.append("password = ?")
                        params.append(encrypt_value(password))
                    
                    if show_browser is not None:
                        update_fields.append("show_browser = ?")
                        params.append(1 if show_browser else 0)
                    
                    if not update_fields:
                        logger.warning(f"更新账号 {cookie_id} 信息时没有提供任何更新字段")
                        return False
                    
                    params.append(cookie_id)
                    sql = f"UPDATE cookies SET {', '.join(update_fields)} WHERE id = ?"
                    
                    self._execute_sql(cursor, sql, tuple(params))
                    self.conn.commit()
                    logger.info(f"更新账号 {cookie_id} 信息成功: {update_fields}")
                    return True
            except Exception as e:
                logger.error(f"更新账号信息失败: {e}")
                import traceback
                logger.error(traceback.format_exc())
                self.conn.rollback()
                return False



    def save_cookie_status(self, cookie_id: str, enabled: bool):
        """保存Cookie的启用状态"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                INSERT OR REPLACE INTO cookie_status (cookie_id, enabled, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ''', (cookie_id, enabled))
                self.conn.commit()
                logger.debug(f"保存Cookie状态: {cookie_id} -> {'启用' if enabled else '禁用'}")
            except Exception as e:
                logger.error(f"保存Cookie状态失败: {e}")
                raise



    def get_cookie_status(self, cookie_id: str) -> bool:
        """获取Cookie的启用状态"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('SELECT enabled FROM cookie_status WHERE cookie_id = ?', (cookie_id,))
                result = cursor.fetchone()
                return bool(result[0]) if result else True  # 默认启用
            except Exception as e:
                logger.error(f"获取Cookie状态失败: {e}")
                return True  # 出错时默认启用



    def get_all_cookie_status(self) -> Dict[str, bool]:
        """获取所有Cookie的启用状态"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('SELECT cookie_id, enabled FROM cookie_status')

                result = {}
                for row in cursor.fetchall():
                    cookie_id, enabled = row
                    result[cookie_id] = bool(enabled)

                return result
            except Exception as e:
                logger.error(f"获取所有Cookie状态失败: {e}")
                return {}

    # -------------------- AI回复设置操作 --------------------


    def get_items_by_cookie(self, cookie_id: str) -> List[Dict]:
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
                SELECT * FROM item_info
                WHERE cookie_id = ?
                ORDER BY updated_at DESC
                ''', (cookie_id,))

                columns = [description[0] for description in cursor.description]
                items = []

                for row in cursor.fetchall():
                    item_info = dict(zip(columns, row))

                    # 解析item_detail JSON
                    if item_info.get('item_detail'):
                        try:
                            item_info['item_detail_parsed'] = json.loads(item_info['item_detail'])
                        except Exception:
                            item_info['item_detail_parsed'] = {}

                    items.append(item_info)

                return items

        except Exception as e:
            logger.error(f"获取Cookie商品信息失败: {e}")
            return []



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

