"""
User Mixin - 用户和会话管理
"""
import sqlite3
import json
import time
import secrets
import hashlib
import bcrypt
from typing import Optional, Dict, Any, List, Tuple
from loguru import logger


class UserManagerMixin:
    """用户和会话管理"""

    def update_admin_user_id(self, cursor):
        """更新admin用户ID"""
        try:
            logger.info("开始更新admin用户ID...")
            # 创建默认admin用户（只在首次初始化时创建）
            cursor.execute('SELECT COUNT(*) FROM users WHERE username = ?', ('admin',))
            admin_exists = cursor.fetchone()[0] > 0

            if not admin_exists:
                # 首次创建admin用户，生成随机密码
                import secrets
                import string
                chars = string.ascii_letters + string.digits
                default_password = ''.join(secrets.choice(chars) for _ in range(12))
                default_password_hash = bcrypt.hashpw(default_password.encode(), bcrypt.gensalt()).decode()
                cursor.execute('''
                INSERT INTO users (username, email, password_hash) VALUES
                ('admin', 'admin@localhost', ?)
                ''', (default_password_hash,))
                # 将随机密码写入文件，供 check-default-password 和启动日志使用
                pw_file = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    'data', '.admin_default_password'
                )
                try:
                    os.makedirs(os.path.dirname(pw_file), exist_ok=True)
                    with open(pw_file, 'w', encoding='utf-8') as f:
                        f.write(default_password)
                    try:
                        import stat
                        os.chmod(pw_file, stat.S_IRUSR | stat.S_IWUSR)
                    except Exception:
                        pass
                except Exception as e:
                    logger.error(f"保存默认密码文件失败: {e}")
                logger.warning("=" * 50)
                logger.warning(f"首次创建 admin 用户，初始密码: {default_password}")
                logger.warning("请尽快登录并修改密码！")
                logger.warning("=" * 50)

            # 获取admin用户ID，用于历史数据绑定
            self._execute_sql(cursor, "SELECT id FROM users WHERE username = 'admin'")
            admin_user = cursor.fetchone()
            if admin_user:
                admin_user_id = admin_user[0]

                # 将历史cookies数据绑定到admin用户（如果user_id列不存在）
                try:
                    self._execute_sql(cursor, "SELECT user_id FROM cookies LIMIT 1")
                except sqlite3.OperationalError:
                    # user_id列不存在，需要添加并更新历史数据
                    self._execute_sql(cursor, "ALTER TABLE cookies ADD COLUMN user_id INTEGER")
                    self._execute_sql(cursor, "UPDATE cookies SET user_id = ? WHERE user_id IS NULL", (admin_user_id,))
                else:
                    # user_id列存在，更新NULL值
                    self._execute_sql(cursor, "UPDATE cookies SET user_id = ? WHERE user_id IS NULL", (admin_user_id,))

                # 为cookies表添加auto_confirm字段（如果不存在）
                try:
                    self._execute_sql(cursor, "SELECT auto_confirm FROM cookies LIMIT 1")
                except sqlite3.OperationalError:
                    # auto_confirm列不存在，需要添加并设置默认值
                    self._execute_sql(cursor, "ALTER TABLE cookies ADD COLUMN auto_confirm INTEGER DEFAULT 1")
                    self._execute_sql(cursor, "UPDATE cookies SET auto_confirm = 1 WHERE auto_confirm IS NULL")
                else:
                    # auto_confirm列存在，更新NULL值
                    self._execute_sql(cursor, "UPDATE cookies SET auto_confirm = 1 WHERE auto_confirm IS NULL")

                # 为delivery_rules表添加user_id字段（如果不存在）
                try:
                    self._execute_sql(cursor, "SELECT user_id FROM delivery_rules LIMIT 1")
                except sqlite3.OperationalError:
                    # user_id列不存在，需要添加并更新历史数据
                    self._execute_sql(cursor, "ALTER TABLE delivery_rules ADD COLUMN user_id INTEGER")
                    self._execute_sql(cursor, "UPDATE delivery_rules SET user_id = ? WHERE user_id IS NULL", (admin_user_id,))
                else:
                    # user_id列存在，更新NULL值
                    self._execute_sql(cursor, "UPDATE delivery_rules SET user_id = ? WHERE user_id IS NULL", (admin_user_id,))

                # 为notification_channels表添加user_id字段（如果不存在）
                try:
                    self._execute_sql(cursor, "SELECT user_id FROM notification_channels LIMIT 1")
                except sqlite3.OperationalError:
                    # user_id列不存在，需要添加并更新历史数据
                    self._execute_sql(cursor, "ALTER TABLE notification_channels ADD COLUMN user_id INTEGER")
                    self._execute_sql(cursor, "UPDATE notification_channels SET user_id = ? WHERE user_id IS NULL", (admin_user_id,))
                else:
                    # user_id列存在，更新NULL值
                    self._execute_sql(cursor, "UPDATE notification_channels SET user_id = ? WHERE user_id IS NULL", (admin_user_id,))

                # 为email_verifications表添加type字段（如果不存在）
                try:
                    self._execute_sql(cursor, "SELECT type FROM email_verifications LIMIT 1")
                except sqlite3.OperationalError:
                    # type列不存在，需要添加并更新历史数据
                    self._execute_sql(cursor, "ALTER TABLE email_verifications ADD COLUMN type TEXT DEFAULT 'register'")
                    self._execute_sql(cursor, "UPDATE email_verifications SET type = 'register' WHERE type IS NULL")
                else:
                    # type列存在，更新NULL值
                    self._execute_sql(cursor, "UPDATE email_verifications SET type = 'register' WHERE type IS NULL")

                # 为cards表添加多规格字段（如果不存在）
                try:
                    self._execute_sql(cursor, "SELECT is_multi_spec FROM cards LIMIT 1")
                except sqlite3.OperationalError:
                    # 多规格字段不存在，需要添加
                    self._execute_sql(cursor, "ALTER TABLE cards ADD COLUMN is_multi_spec BOOLEAN DEFAULT FALSE")
                    self._execute_sql(cursor, "ALTER TABLE cards ADD COLUMN spec_name TEXT")
                    self._execute_sql(cursor, "ALTER TABLE cards ADD COLUMN spec_value TEXT")
                    logger.info("为cards表添加多规格字段")

                # 为item_info表添加多规格字段（如果不存在）
                try:
                    self._execute_sql(cursor, "SELECT is_multi_spec FROM item_info LIMIT 1")
                except sqlite3.OperationalError:
                    # 多规格字段不存在，需要添加
                    self._execute_sql(cursor, "ALTER TABLE item_info ADD COLUMN is_multi_spec BOOLEAN DEFAULT FALSE")
                    logger.info("为item_info表添加多规格字段")

                # 为item_info表添加多数量发货字段（如果不存在）
                try:
                    self._execute_sql(cursor, "SELECT multi_quantity_delivery FROM item_info LIMIT 1")
                except sqlite3.OperationalError:
                    # 多数量发货字段不存在，需要添加
                    self._execute_sql(cursor, "ALTER TABLE item_info ADD COLUMN multi_quantity_delivery BOOLEAN DEFAULT FALSE")
                    logger.info("为item_info表添加多数量发货字段")

                # 检查orders表是否有is_bargain字段
                try:
                    self._execute_sql(cursor, "SELECT is_bargain FROM orders LIMIT 1")
                except sqlite3.OperationalError:
                    # is_bargain字段不存在，需要添加
                    self._execute_sql(cursor, "ALTER TABLE orders ADD COLUMN is_bargain INTEGER DEFAULT 0")
                    logger.info("为orders表添加is_bargain字段")

                # 检查orders表是否有receiver_name字段
                try:
                    self._execute_sql(cursor, "SELECT receiver_name FROM orders LIMIT 1")
                except sqlite3.OperationalError:
                    # receiver_name字段不存在，需要添加
                    self._execute_sql(cursor, "ALTER TABLE orders ADD COLUMN receiver_name TEXT")
                    logger.info("为orders表添加receiver_name字段")

                # 检查orders表是否有receiver_phone字段
                try:
                    self._execute_sql(cursor, "SELECT receiver_phone FROM orders LIMIT 1")
                except sqlite3.OperationalError:
                    # receiver_phone字段不存在，需要添加
                    self._execute_sql(cursor, "ALTER TABLE orders ADD COLUMN receiver_phone TEXT")
                    logger.info("为orders表添加receiver_phone字段")

                # 检查orders表是否有receiver_address字段
                try:
                    self._execute_sql(cursor, "SELECT receiver_address FROM orders LIMIT 1")
                except sqlite3.OperationalError:
                    # receiver_address字段不存在，需要添加
                    self._execute_sql(cursor, "ALTER TABLE orders ADD COLUMN receiver_address TEXT")
                    logger.info("为orders表添加receiver_address字段")

                # 检查orders表是否有system_shipped字段（系统是否已发货）
                try:
                    self._execute_sql(cursor, "SELECT system_shipped FROM orders LIMIT 1")
                except sqlite3.OperationalError:
                    # system_shipped字段不存在，需要添加
                    self._execute_sql(cursor, "ALTER TABLE orders ADD COLUMN system_shipped INTEGER DEFAULT 0")
                    logger.info("为orders表添加system_shipped字段")

                # 处理keywords表的唯一约束问题
                # 由于SQLite不支持直接修改约束，我们需要重建表
                self._migrate_keywords_table_constraints(cursor)

            self.conn.commit()
            logger.info(f"admin用户ID更新完成")
        except Exception as e:
            logger.error(f"更新admin用户ID失败: {e}")
            raise
            


    def create_user(self, username: str, email: str, password: str) -> bool:
        """创建新用户"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

                cursor.execute('''
                INSERT INTO users (username, email, password_hash)
                VALUES (?, ?, ?)
                ''', (username, email, password_hash))

                self.conn.commit()
                logger.info(f"创建用户成功: {username} ({email})")
                return True
            except sqlite3.IntegrityError as e:
                logger.error(f"创建用户失败，用户名或邮箱已存在: {e}")
                self.conn.rollback()
                return False
            except Exception as e:
                logger.error(f"创建用户失败: {e}")
                self.conn.rollback()
                return False



    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """根据用户名获取用户信息"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                SELECT id, username, email, password_hash, is_active, created_at, updated_at
                FROM users WHERE username = ?
                ''', (username,))

                row = cursor.fetchone()
                if row:
                    return {
                        'id': row[0],
                        'username': row[1],
                        'email': row[2],
                        'password_hash': row[3],
                        'is_active': row[4],
                        'created_at': row[5],
                        'updated_at': row[6]
                    }
                return None
            except Exception as e:
                logger.error(f"获取用户信息失败: {e}")
                return None



    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """根据邮箱获取用户信息"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                SELECT id, username, email, password_hash, is_active, created_at, updated_at
                FROM users WHERE email = ?
                ''', (email,))

                row = cursor.fetchone()
                if row:
                    return {
                        'id': row[0],
                        'username': row[1],
                        'email': row[2],
                        'password_hash': row[3],
                        'is_active': row[4],
                        'created_at': row[5],
                        'updated_at': row[6]
                    }
                return None
            except Exception as e:
                logger.error(f"获取用户信息失败: {e}")
                return None



    def verify_user_password(self, username: str, password: str) -> bool:
        """验证用户密码（支持自动从SHA-256升级到bcrypt）"""
        user = self.get_user_by_username(username)
        if not user:
            return False

        stored_hash = user['password_hash']
        if not user['is_active']:
            return False

        # 检查是否为旧的SHA-256哈希（64字符十六进制）
        if len(stored_hash) == 64 and all(c in '0123456789abcdef' for c in stored_hash.lower()):
            # SHA-256哈希，验证后自动升级为bcrypt
            sha256_hash = hashlib.sha256(password.encode()).hexdigest()
            if sha256_hash == stored_hash:
                # 验证通过，静默升级为bcrypt哈希
                new_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
                self._upgrade_password_hash(username, new_hash)
                return True
            return False
        else:
            # 使用bcrypt验证
            try:
                return bcrypt.checkpw(password.encode(), stored_hash.encode())
            except Exception as e:
                logger.error(f"bcrypt密码验证失败: {e}")
                return False



    def update_user_password(self, username: str, new_password: str) -> bool:
        """更新用户密码"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                password_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()

                cursor.execute('''
                UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP
                WHERE username = ?
                ''', (password_hash, username))

                if cursor.rowcount > 0:
                    self.conn.commit()
                    logger.info(f"用户 {username} 密码更新成功")
                    return True
                else:
                    logger.warning(f"用户 {username} 不存在，密码更新失败")
                    return False

            except Exception as e:
                logger.error(f"更新用户密码失败: {e}")
                self.conn.rollback()
                return False



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



    def get_all_users(self):
        """获取所有用户信息（管理员专用）"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                SELECT id, username, email, created_at, updated_at
                FROM users
                ORDER BY created_at DESC
                ''')

                users = []
                for row in cursor.fetchall():
                    users.append({
                        'id': row[0],
                        'username': row[1],
                        'email': row[2],
                        'created_at': row[3],
                        'updated_at': row[4]
                    })

                return users
            except Exception as e:
                logger.error(f"获取所有用户失败: {e}")
                return []



    def get_user_by_id(self, user_id: int):
        """根据ID获取用户信息"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                SELECT id, username, email, created_at, updated_at
                FROM users
                WHERE id = ?
                ''', (user_id,))

                row = cursor.fetchone()
                if row:
                    return {
                        'id': row[0],
                        'username': row[1],
                        'email': row[2],
                        'created_at': row[3],
                        'updated_at': row[4]
                    }
                return None
            except Exception as e:
                logger.error(f"获取用户信息失败: {e}")
                return None



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



    def save_session(self, token: str, user_id: int, username: str, is_admin: bool, expire_seconds: int = 86400):
        with self.lock:
            cursor = self.conn.cursor()
            now = time.time()
            cursor.execute(
                'INSERT OR REPLACE INTO user_sessions (token, user_id, username, is_admin, created_at, expires_at) VALUES (?,?,?,?,?,?)',
                (token, user_id, username, is_admin, now, now + expire_seconds)
            )
            self.conn.commit()



    def get_session(self, token: str):
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute('SELECT user_id, username, is_admin, created_at, expires_at FROM user_sessions WHERE token=?', (token,))
            row = cursor.fetchone()
            if not row:
                return None
            user_id, username, is_admin, created_at, expires_at = row
            if time.time() > expires_at:
                cursor.execute('DELETE FROM user_sessions WHERE token=?', (token,))
                self.conn.commit()
                return None
            return {'user_id': user_id, 'username': username, 'is_admin': bool(is_admin), 'timestamp': created_at}



    def delete_session(self, token: str):
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute('DELETE FROM user_sessions WHERE token=?', (token,))
            self.conn.commit()

