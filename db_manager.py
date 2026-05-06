import sqlite3
import os
import threading
import hashlib
import time
import json
import random
import string
import aiohttp
import io
import base64
import bcrypt
from PIL import Image, ImageDraw, ImageFont
from typing import List, Tuple, Dict, Optional, Any
from loguru import logger
from utils.crypto import encrypt_value, decrypt_value

# ===== SQL 注入防护：表名白名单 =====
_ALLOWED_TABLES = frozenset({
    # 正式业务表
    'users', 'email_verifications', 'captcha_codes', 'cookies', 'keywords',
    'cookie_status', 'ai_reply_settings', 'ai_conversations', 'ai_item_cache',
    'cards', 'orders', 'item_info', 'delivery_rules', 'default_replies',
    'item_replay', 'default_reply_records', 'notification_channels',
    'system_settings', 'message_notifications', 'user_settings',
    'risk_control_logs', 'daily_quota',
    # 遗留迁移表（仅用于迁移流程，迁移完成后删除）
    'old_notification_channels', 'legacy_delivery_rules', 'old_keywords', 'backup_cookies',
})


def _validate_table_name(name: str) -> str:
    """校验表名，防止 SQL 注入。通过白名单确保只有合法表名可用于动态 SQL。"""
    if name not in _ALLOWED_TABLES:
        raise ValueError(f"不允许的表名: {name}")
    return name



# Mixin imports
from mixins.item_mixin import ItemManagerMixin
from mixins.cookie_mixin import CookieManagerMixin
from mixins.user_mixin import UserManagerMixin
from mixins.notification_mixin import NotificationManagerMixin
from mixins.keyword_mixin import KeywordManagerMixin
from mixins.delivery_mixin import DeliveryManagerMixin
from mixins.setting_mixin import SettingManagerMixin
from mixins.order_mixin import OrderManagerMixin
from mixins.default_reply_mixin import DefaultReplyManagerMixin
from mixins.card_mixin import CardManagerMixin
from mixins.log_mixin import LogManagerMixin
from mixins.blacklist_mixin import BlacklistManagerMixin
from mixins.backup_mixin import BackupManagerMixin
from mixins.maintenance_mixin import MaintenanceManagerMixin


class DBManager(ItemManagerMixin, CookieManagerMixin, UserManagerMixin, NotificationManagerMixin, KeywordManagerMixin, DeliveryManagerMixin, SettingManagerMixin, OrderManagerMixin, DefaultReplyManagerMixin, CardManagerMixin, LogManagerMixin, BlacklistManagerMixin, BackupManagerMixin, MaintenanceManagerMixin):
    """SQLite数据库管理，持久化存储Cookie和关键字"""
    
    def __init__(self, db_path: str = None):
        """初始化数据库连接和表结构"""
        # 支持环境变量配置数据库路径
        if db_path is None:
            db_path = os.getenv('DB_PATH', 'data/xianyu_data.db')

        # 确保数据目录存在并有正确权限
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            try:
                os.makedirs(db_dir, mode=0o755, exist_ok=True)
                logger.info(f"创建数据目录: {db_dir}")
            except PermissionError as e:
                logger.error(f"创建数据目录失败，权限不足: {e}")
                # 尝试使用当前目录
                db_path = os.path.basename(db_path)
                logger.warning(f"使用当前目录作为数据库路径: {db_path}")
            except Exception as e:
                logger.error(f"创建数据目录失败: {e}")
                raise

        # 检查目录权限
        if db_dir and os.path.exists(db_dir):
            if not os.access(db_dir, os.W_OK):
                logger.error(f"数据目录没有写权限: {db_dir}")
                # 尝试使用当前目录
                db_path = os.path.basename(db_path)
                logger.warning(f"使用当前目录作为数据库路径: {db_path}")

        self.db_path = db_path
        logger.info(f"数据库路径: {self.db_path}")
        self.conn = None
        self.lock = threading.RLock()  # 使用可重入锁保护数据库操作

        # SQL日志配置 - 默认启用
        self.sql_log_enabled = False  # 默认关闭SQL日志
        self.sql_log_level = 'INFO'  # 默认使用INFO级别

        # 允许通过环境变量覆盖默认设置
        if os.getenv('SQL_LOG_ENABLED'):
            self.sql_log_enabled = os.getenv('SQL_LOG_ENABLED', 'true').lower() == 'true'
        if os.getenv('SQL_LOG_LEVEL'):
            self.sql_log_level = os.getenv('SQL_LOG_LEVEL', 'INFO').upper()

        logger.info(f"SQL日志已启用，日志级别: {self.sql_log_level}")

        self.init_db()
    
    def init_db(self):
        """初始化数据库表结构"""
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            cursor = self.conn.cursor()

            cursor.execute('PRAGMA journal_mode=WAL;')
            cursor.execute('PRAGMA synchronous=NORMAL;')
            cursor.execute('PRAGMA cache_size=-8000;')
            cursor.execute('PRAGMA busy_timeout=5000;')
            
            # 创建用户表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')

            # 创建邮箱验证码表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS email_verifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                code TEXT NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                used BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')

            # 创建图形验证码表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS captcha_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                code TEXT NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')

            # 创建cookies表（添加user_id字段和auto_confirm字段）
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS cookies (
                id TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                auto_confirm INTEGER DEFAULT 1,
                remark TEXT DEFAULT '',
                pause_duration INTEGER DEFAULT 10,
                username TEXT DEFAULT '',
                password TEXT DEFAULT '',
                show_browser INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            ''')

            
            # 创建keywords表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS keywords (
                cookie_id TEXT,
                keyword TEXT,
                reply TEXT,
                item_id TEXT,
                type TEXT DEFAULT 'text',
                image_url TEXT,
                FOREIGN KEY (cookie_id) REFERENCES cookies(id) ON DELETE CASCADE
            )
            ''')

            # 创建cookie_status表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS cookie_status (
                cookie_id TEXT PRIMARY KEY,
                enabled BOOLEAN DEFAULT TRUE,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cookie_id) REFERENCES cookies(id) ON DELETE CASCADE
            )
            ''')

            # 创建AI回复配置表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS ai_reply_settings (
                cookie_id TEXT PRIMARY KEY,
                ai_enabled BOOLEAN DEFAULT FALSE,
                model_name TEXT DEFAULT 'qwen-plus',
                api_key TEXT,
                base_url TEXT DEFAULT 'https://dashscope.aliyuncs.com/compatible-mode/v1',
                max_discount_percent INTEGER DEFAULT 10,
                max_discount_amount INTEGER DEFAULT 100,
                max_bargain_rounds INTEGER DEFAULT 3,
                custom_prompts TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cookie_id) REFERENCES cookies(id) ON DELETE CASCADE
            )
            ''')

            # 创建AI对话历史表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS ai_conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cookie_id TEXT NOT NULL,
                chat_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                intent TEXT,
                bargain_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cookie_id) REFERENCES cookies (id) ON DELETE CASCADE
            )
            ''')

            # 创建AI商品信息缓存表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS ai_item_cache (
                item_id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                price REAL,
                description TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')

            # 创建卡券表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL CHECK (type IN ('api', 'text', 'data', 'image')),
                api_config TEXT,
                text_content TEXT,
                data_content TEXT,
                image_url TEXT,
                description TEXT,
                enabled BOOLEAN DEFAULT TRUE,
                delay_seconds INTEGER DEFAULT 0,
                is_multi_spec BOOLEAN DEFAULT FALSE,
                spec_name TEXT,
                spec_value TEXT,
                user_id INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            ''')

            # 创建订单表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                item_id TEXT,
                buyer_id TEXT,
                spec_name TEXT,
                spec_value TEXT,
                quantity TEXT,
                amount TEXT,
                order_status TEXT DEFAULT 'unknown',
                cookie_id TEXT,
                is_bargain INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cookie_id) REFERENCES cookies(id) ON DELETE CASCADE
            )
            ''')

            # 检查并添加 is_bargain 列（用于标记小刀订单）
            try:
                self._execute_sql(cursor, "SELECT is_bargain FROM orders LIMIT 1")
            except sqlite3.OperationalError:
                # is_bargain 列不存在，需要添加
                logger.info("正在为 orders 表添加 is_bargain 列...")
                self._execute_sql(cursor, "ALTER TABLE orders ADD COLUMN is_bargain INTEGER DEFAULT 0")
                logger.info("orders 表 is_bargain 列添加完成")

            # 检查并添加收货人信息列
            try:
                self._execute_sql(cursor, "SELECT receiver_name FROM orders LIMIT 1")
            except sqlite3.OperationalError:
                # receiver_name 列不存在，需要添加
                logger.info("正在为 orders 表添加收货人信息列...")
                self._execute_sql(cursor, "ALTER TABLE orders ADD COLUMN receiver_name TEXT DEFAULT ''")
                self._execute_sql(cursor, "ALTER TABLE orders ADD COLUMN receiver_phone TEXT DEFAULT ''")
                self._execute_sql(cursor, "ALTER TABLE orders ADD COLUMN receiver_address TEXT DEFAULT ''")
                logger.info("orders 表收货人信息列添加完成")

            # 检查并添加 version 列（用于乐观锁）
            try:
                self._execute_sql(cursor, "SELECT version FROM orders LIMIT 1")
            except sqlite3.OperationalError:
                # version 列不存在，需要添加
                logger.info("正在为 orders 表添加 version 列...")
                self._execute_sql(cursor, "ALTER TABLE orders ADD COLUMN version INTEGER DEFAULT 1")
                logger.info("orders 表 version 列添加完成")

            # 检查并添加 chat_id 列到 orders 表（用于手动发货时发送消息）
            try:
                self._execute_sql(cursor, "SELECT chat_id FROM orders LIMIT 1")
            except sqlite3.OperationalError:
                logger.info("正在为 orders 表添加 chat_id 列...")
                self._execute_sql(cursor, "ALTER TABLE orders ADD COLUMN chat_id TEXT DEFAULT ''")
                logger.info("orders 表 chat_id 列添加完成")

            # 检查并添加 user_id 列（用于数据库迁移）
            try:
                self._execute_sql(cursor, "SELECT user_id FROM cards LIMIT 1")
            except sqlite3.OperationalError:
                # user_id 列不存在，需要添加
                logger.info("正在为 cards 表添加 user_id 列...")
                self._execute_sql(cursor, "ALTER TABLE cards ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1")
                self._execute_sql(cursor, "CREATE INDEX IF NOT EXISTS idx_cards_user_id ON cards(user_id)")
                logger.info("cards 表 user_id 列添加完成")

            # 检查并添加 delay_seconds 列（用于自动发货延时功能）
            try:
                self._execute_sql(cursor, "SELECT delay_seconds FROM cards LIMIT 1")
            except sqlite3.OperationalError:
                # delay_seconds 列不存在，需要添加
                logger.info("正在为 cards 表添加 delay_seconds 列...")
                self._execute_sql(cursor, "ALTER TABLE cards ADD COLUMN delay_seconds INTEGER DEFAULT 0")
                logger.info("cards 表 delay_seconds 列添加完成")

            # 检查并添加 item_id 列（用于自动回复商品ID功能）
            try:
                self._execute_sql(cursor, "SELECT item_id FROM keywords LIMIT 1")
            except sqlite3.OperationalError:
                # item_id 列不存在，需要添加
                logger.info("正在为 keywords 表添加 item_id 列...")
                self._execute_sql(cursor, "ALTER TABLE keywords ADD COLUMN item_id TEXT")
                logger.info("keywords 表 item_id 列添加完成")

            # 创建商品信息表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS item_info (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cookie_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                item_title TEXT,
                item_description TEXT,
                item_category TEXT,
                item_price TEXT,
                item_detail TEXT,
                is_multi_spec BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cookie_id) REFERENCES cookies(id) ON DELETE CASCADE,
                UNIQUE(cookie_id, item_id)
            )
            ''')

            # 检查并添加 multi_quantity_delivery 列（用于多数量发货功能）
            try:
                self._execute_sql(cursor, "SELECT multi_quantity_delivery FROM item_info LIMIT 1")
            except sqlite3.OperationalError:
                # multi_quantity_delivery 列不存在，需要添加
                logger.info("正在为 item_info 表添加 multi_quantity_delivery 列...")
                self._execute_sql(cursor, "ALTER TABLE item_info ADD COLUMN multi_quantity_delivery BOOLEAN DEFAULT FALSE")
                logger.info("item_info 表 multi_quantity_delivery 列添加完成")

            # 创建自动发货规则表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS delivery_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT NOT NULL,
                card_id INTEGER NOT NULL,
                delivery_count INTEGER DEFAULT 1,
                enabled BOOLEAN DEFAULT TRUE,
                description TEXT,
                delivery_times INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE
            )
            ''')

            # 创建默认回复表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS default_replies (
                cookie_id TEXT PRIMARY KEY,
                enabled BOOLEAN DEFAULT FALSE,
                reply_content TEXT,
                reply_image_url TEXT,
                reply_once BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cookie_id) REFERENCES cookies(id) ON DELETE CASCADE
            )
            ''')

            # 添加 reply_once 字段（如果不存在）
            try:
                cursor.execute('ALTER TABLE default_replies ADD COLUMN reply_once BOOLEAN DEFAULT FALSE')
                self.conn.commit()
                logger.info("已添加 reply_once 字段到 default_replies 表")
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e).lower():
                    logger.warning(f"添加 reply_once 字段失败: {e}")

            # 添加 reply_image_url 字段（如果不存在）
            try:
                cursor.execute('ALTER TABLE default_replies ADD COLUMN reply_image_url TEXT')
                self.conn.commit()
                logger.info("已添加 reply_image_url 字段到 default_replies 表")
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e).lower():
                    logger.warning(f"添加 reply_image_url 字段失败: {e}")

            # 创建指定商品回复表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS item_replay (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id TEXT NOT NULL,
                    cookie_id TEXT NOT NULL,
                    reply_content TEXT NOT NULL ,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 创建默认回复记录表（记录已回复的chat_id）
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS default_reply_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cookie_id TEXT NOT NULL,
                chat_id TEXT NOT NULL,
                replied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(cookie_id, chat_id),
                FOREIGN KEY (cookie_id) REFERENCES cookies(id) ON DELETE CASCADE
            )
            ''')

            # 创建通知渠道表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS notification_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL CHECK (type IN ('qq','ding_talk','dingtalk','feishu','lark','bark','email','webhook','wechat','telegram')),
                config TEXT NOT NULL,
                enabled BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')

            # 创建系统设置表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                description TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')

            # 创建消息通知配置表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS message_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cookie_id TEXT NOT NULL,
                channel_id INTEGER NOT NULL,
                enabled BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cookie_id) REFERENCES cookies(id) ON DELETE CASCADE,
                FOREIGN KEY (channel_id) REFERENCES notification_channels(id) ON DELETE CASCADE,
                UNIQUE(cookie_id, channel_id)
            )
            ''')

            # 创建用户设置表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE(user_id, key)
            )
            ''')

            # 创建风控日志表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS risk_control_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cookie_id TEXT NOT NULL,
                event_type TEXT NOT NULL DEFAULT 'slider_captcha',
                event_description TEXT,
                processing_result TEXT,
                processing_status TEXT DEFAULT 'processing',
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cookie_id) REFERENCES cookies(id) ON DELETE CASCADE
            )
            ''')

            # 创建每日配额表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_quota (
                cookie_id TEXT NOT NULL,
                date TEXT NOT NULL,
                auto_reply_count INTEGER DEFAULT 0,
                auto_delivery_count INTEGER DEFAULT 0,
                PRIMARY KEY (cookie_id, date),
                FOREIGN KEY (cookie_id) REFERENCES cookies(id) ON DELETE CASCADE
            )
            ''')

            # 插入默认系统设置（不包括管理员密码，由reply_server.py初始化）
            cursor.execute('''
            INSERT OR IGNORE INTO system_settings (key, value, description) VALUES
            ('theme_color', 'blue', '主题颜色'),
            ('registration_enabled', 'true', '是否开启用户注册'),
            ('show_default_login_info', 'true', '是否显示默认登录信息'),
            ('login_captcha_enabled', 'true', '登录滑动验证码开关'),
            ('smtp_server', '', 'SMTP服务器地址'),
            ('smtp_port', '587', 'SMTP端口'),
            ('smtp_user', '', 'SMTP登录用户名（发件邮箱）'),
            ('smtp_password', '', 'SMTP登录密码/授权码'),
            ('smtp_from', '', '发件人显示名（留空则使用用户名）'),
            ('smtp_use_tls', 'true', '是否启用TLS'),
            ('smtp_use_ssl', 'false', '是否启用SSL'),
            ('qq_reply_secret_key', 'xianyu_qq_reply_2024', 'QQ回复消息API秘钥'),
            ('item_sync_enabled', 'true', '是否启用定时自动同步商品'),
            ('item_sync_interval', '600', '商品同步间隔时间（秒）'),
            ('item_sync_max_pages', '5', '每次最多同步的页数')
            ''')

            # 创建用户会话表（持久化token）
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                is_admin BOOLEAN DEFAULT FALSE,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            ''')

            # 创建发货失败重试队列表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS delivery_retry_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cookie_id TEXT NOT NULL,
                order_id TEXT,
                item_id TEXT,
                buyer_id TEXT,
                buyer_name TEXT DEFAULT '',
                chat_id TEXT DEFAULT '',
                quantity INTEGER DEFAULT 1,
                spec_name TEXT DEFAULT '',
                spec_value TEXT DEFAULT '',
                error_type TEXT NOT NULL DEFAULT 'no_match',
                error_message TEXT DEFAULT '',
                retry_count INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 5,
                next_retry_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cookie_id) REFERENCES cookies(id) ON DELETE CASCADE
            )
            ''')

            # 创建智能上下架计划表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS item_schedule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cookie_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                item_title TEXT DEFAULT '',
                schedule_type TEXT NOT NULL CHECK (schedule_type IN ('list', 'delist')),
                schedule_time TEXT,
                cron_expression TEXT DEFAULT '',
                enabled BOOLEAN DEFAULT TRUE,
                last_run_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cookie_id) REFERENCES cookies(id) ON DELETE CASCADE
            )
            ''')

            # 创建买家黑名单表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS buyer_blacklist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                buyer_id TEXT NOT NULL,
                buyer_name TEXT DEFAULT '',
                reason TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE(user_id, buyer_id)
            )
            ''')

            # 创建自动评价配置表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS evaluation_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cookie_id TEXT NOT NULL,
                auto_evaluate_enabled BOOLEAN DEFAULT FALSE,
                evaluate_content TEXT DEFAULT '感谢您的购买，欢迎再次光临！',
                auto_reply_review_enabled BOOLEAN DEFAULT FALSE,
                reply_review_content TEXT DEFAULT '感谢支持！',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cookie_id) REFERENCES cookies(id) ON DELETE CASCADE,
                UNIQUE(cookie_id)
            )
            ''')

            # 检查并升级数据库
            self.check_and_upgrade_db(cursor)

            # 执行数据库迁移
            self._migrate_database(cursor)

            self._create_indexes(cursor)

            self.conn.commit()
            logger.info("数据库初始化完成")
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")
            self.conn.rollback()
            raise

    def _migrate_database(self, cursor):
        """执行数据库迁移"""
        try:
            # 检查cards表是否存在image_url列
            cursor.execute("PRAGMA table_info(cards)")
            columns = [column[1] for column in cursor.fetchall()]

            if 'image_url' not in columns:
                logger.info("添加cards表的image_url列...")
                cursor.execute("ALTER TABLE cards ADD COLUMN image_url TEXT")
                logger.info("数据库迁移完成：添加image_url列")

            # 检查并更新CHECK约束（重建表以支持image类型）
            self._update_cards_table_constraints(cursor)

            # 检查cookies表是否存在remark列
            cursor.execute("PRAGMA table_info(cookies)")
            cookie_columns = [column[1] for column in cursor.fetchall()]

            if 'remark' not in cookie_columns:
                logger.info("添加cookies表的remark列...")
                cursor.execute("ALTER TABLE cookies ADD COLUMN remark TEXT DEFAULT ''")
                logger.info("数据库迁移完成：添加remark列")

            # 检查cookies表是否存在pause_duration列
            if 'pause_duration' not in cookie_columns:
                logger.info("添加cookies表的pause_duration列...")
                cursor.execute("ALTER TABLE cookies ADD COLUMN pause_duration INTEGER DEFAULT 10")
                logger.info("数据库迁移完成：添加pause_duration列")

            # 确保商品同步配置存在
            cursor.execute("SELECT key FROM system_settings WHERE key IN ('item_sync_enabled', 'item_sync_interval', 'item_sync_max_pages')")
            existing_keys = [row[0] for row in cursor.fetchall()]

            if 'item_sync_enabled' not in existing_keys:
                logger.info("添加商品同步配置：item_sync_enabled...")
                cursor.execute("INSERT INTO system_settings (key, value, description) VALUES ('item_sync_enabled', 'true', '是否启用定时自动同步商品')")
            if 'item_sync_interval' not in existing_keys:
                logger.info("添加商品同步配置：item_sync_interval...")
                cursor.execute("INSERT INTO system_settings (key, value, description) VALUES ('item_sync_interval', '600', '商品同步间隔时间（秒）')")
            if 'item_sync_max_pages' not in existing_keys:
                logger.info("添加商品同步配置：item_sync_max_pages...")
                cursor.execute("INSERT INTO system_settings (key, value, description) VALUES ('item_sync_max_pages', '5', '每次最多同步的页数')")

        except Exception as e:
            logger.error(f"数据库迁移失败: {e}")
            pass

    def _create_indexes(self, cursor):
        """创建缺失的性能索引"""
        try:
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_orders_cookie_id ON orders(cookie_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(order_status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_orders_buyer_id ON orders(buyer_id)')
            # Orders表索引（加速仪表盘查询）
            try:
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_date ON orders(DATE(created_at))")
            except Exception:
                pass
            try:
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_item_id ON orders(item_id)")
            except Exception:
                pass
            try:
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_city ON orders(receiver_city)")
            except Exception:
                pass
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_ai_conv_cookie_chat ON ai_conversations(cookie_id, chat_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_ai_conv_created ON ai_conversations(created_at)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_email_ver_email ON email_verifications(email)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_risk_control_cookie ON risk_control_logs(cookie_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_keywords_cookie ON keywords(cookie_id, id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_default_reply_records_cookie ON default_reply_records(cookie_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_delivery_retry_status ON delivery_retry_queue(status, next_retry_at)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_delivery_retry_cookie ON delivery_retry_queue(cookie_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_buyer_blacklist_user ON buyer_blacklist(user_id)')
            logger.info("数据库索引创建/检查完成")
        except Exception as e:
            logger.warning(f"创建索引时出现警告: {e}")

    def _update_cards_table_constraints(self, cursor):
        """更新cards表的CHECK约束以支持image类型"""
        try:
            # 尝试插入一个测试的image类型记录来检查约束
            cursor.execute('''
                INSERT INTO cards (name, type, user_id)
                VALUES ('__test_image_constraint__', 'image', 1)
            ''')
            # 如果插入成功，立即删除测试记录
            cursor.execute("DELETE FROM cards WHERE name = '__test_image_constraint__'")
            logger.info("cards表约束检查通过，支持image类型")
        except Exception as e:
            if "CHECK constraint failed" in str(e) or "constraint" in str(e).lower():
                logger.info("检测到旧的CHECK约束，开始更新cards表...")

                # 重建表以更新约束
                try:
                    # 1. 创建新表
                    cursor.execute('''
                    CREATE TABLE IF NOT EXISTS cards_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        type TEXT NOT NULL CHECK (type IN ('api', 'text', 'data', 'image')),
                        api_config TEXT,
                        text_content TEXT,
                        data_content TEXT,
                        image_url TEXT,
                        description TEXT,
                        enabled BOOLEAN DEFAULT TRUE,
                        delay_seconds INTEGER DEFAULT 0,
                        is_multi_spec BOOLEAN DEFAULT FALSE,
                        spec_name TEXT,
                        spec_value TEXT,
                        user_id INTEGER NOT NULL DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (id)
                    )
                    ''')

                    # 2. 复制数据
                    cursor.execute('''
                    INSERT INTO cards_new (id, name, type, api_config, text_content, data_content, image_url,
                                          description, enabled, delay_seconds, is_multi_spec, spec_name, spec_value,
                                          user_id, created_at, updated_at)
                    SELECT id, name, type, api_config, text_content, data_content, image_url,
                           description, enabled, delay_seconds, is_multi_spec, spec_name, spec_value,
                           user_id, created_at, updated_at
                    FROM cards
                    ''')

                    # 3. 删除旧表
                    cursor.execute("DROP TABLE cards")

                    # 4. 重命名新表
                    cursor.execute("ALTER TABLE cards_new RENAME TO cards")

                    logger.info("cards表约束更新完成，现在支持image类型")

                except Exception as rebuild_error:
                    logger.error(f"重建cards表失败: {rebuild_error}")
                    # 如果重建失败，尝试回滚
                    try:
                        cursor.execute("DROP TABLE IF EXISTS cards_new")
                    except Exception:
                        pass
            else:
                logger.error(f"检查cards表约束时出现未知错误: {e}")
            
    def check_and_upgrade_db(self, cursor):
        """检查数据库版本并执行必要的升级"""
        try:
            # 获取当前数据库版本
            current_version = self.get_system_setting("db_version") or "1.0"
            logger.info(f"当前数据库版本: {current_version}")

            if current_version == "1.0":
                logger.info("开始升级数据库到版本1.0...")
                self.update_admin_user_id(cursor)
                self.set_system_setting("db_version", "1.0", "数据库版本号")
                logger.info("数据库升级到版本1.0完成")
            
            # 如果版本低于需要升级的版本，执行升级
            if current_version < "1.1":
                logger.info("开始升级数据库到版本1.1...")
                self.upgrade_notification_channels_table(cursor)
                self.set_system_setting("db_version", "1.1", "数据库版本号")
                logger.info("数据库升级到版本1.1完成")

            # 升级到版本1.2 - 支持更多通知渠道类型
            if current_version < "1.2":
                logger.info("开始升级数据库到版本1.2...")
                self.upgrade_notification_channels_types(cursor)
                self.set_system_setting("db_version", "1.2", "数据库版本号")
                logger.info("数据库升级到版本1.2完成")

            # 升级到版本1.3 - 添加关键词类型和图片URL字段
            if current_version < "1.3":
                logger.info("开始升级数据库到版本1.3...")
                self.upgrade_keywords_table_for_image_support(cursor)
                self.set_system_setting("db_version", "1.3", "数据库版本号")
                logger.info("数据库升级到版本1.3完成")
            
            
            # 升级到版本1.4 - 添加关键词类型和图片URL字段
            if current_version < "1.4":
                logger.info("开始升级数据库到版本1.4...")
                self.upgrade_notification_channels_types(cursor)
                self.set_system_setting("db_version", "1.4", "数据库版本号")
                logger.info("数据库升级到版本1.4完成")

            # 升级到版本1.5 - 为cookies表添加账号登录字段
            if current_version < "1.5":
                logger.info("开始升级数据库到版本1.5...")
                self.upgrade_cookies_table_for_account_login(cursor)
                self.set_system_setting("db_version", "1.5", "数据库版本号")
                logger.info("数据库升级到版本1.5完成")

            # 升级到版本1.6 - 添加微信登录绑定字段
            if current_version < "1.6":
                logger.info("开始升级数据库到版本1.6...")
                self.upgrade_users_add_wechat_fields(cursor)
                self.set_system_setting("db_version", "1.6", "数据库版本号")
                logger.info("数据库升级到版本1.6完成")

            # 迁移遗留数据（在所有版本升级完成后执行）
            self.migrate_legacy_data(cursor)

        except Exception as e:
            logger.error(f"数据库版本检查或升级失败: {e}")
            raise
            
    def upgrade_users_add_wechat_fields(self, cursor):
        try:
            # 添加微信相关字段
            for col, col_def in [
                ('wechat_openid', 'TEXT'),
                ('wechat_unionid', 'TEXT'),
                ('wechat_nickname', "TEXT DEFAULT ''"),
                ('wechat_avatar_url', "TEXT DEFAULT ''"),
                ('wechat_bound_at', 'REAL DEFAULT 0'),
            ]:
                try:
                    cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {col_def}")
                except Exception:
                    pass

            # 为wechat_openid创建唯一索引
            try:
                cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_wechat_openid ON users(wechat_openid)")
            except Exception:
                pass

            # 创建微信登录状态表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS wechat_login_states (
                state TEXT PRIMARY KEY,
                expires_at REAL NOT NULL,
                used BOOLEAN DEFAULT FALSE,
                wechat_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            self.conn.commit()
            logger.info("微信字段和登录状态表创建成功")
        except Exception as e:
            logger.error(f"添加微信字段失败: {e}")

    def migrate_legacy_data(self, cursor):
        """迁移遗留数据到新表结构"""
        try:
            logger.info("开始检查和迁移遗留数据...")

            # 检查是否有需要迁移的老表
            legacy_tables = [
                'old_notification_channels',
                'legacy_delivery_rules',
                'old_keywords',
                'backup_cookies'
            ]

            for table_name in legacy_tables:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
                if cursor.fetchone():
                    logger.info(f"发现遗留表: {table_name}，开始迁移数据...")
                    self._migrate_table_data(cursor, table_name)

            logger.info("遗留数据迁移完成")
            return True
        except Exception as e:
            logger.error(f"迁移遗留数据失败: {e}")
            return False

    def _migrate_table_data(self, cursor, table_name: str):
        """迁移指定表的数据"""
        _validate_table_name(table_name)
        try:
            if table_name == 'old_notification_channels':
                # 迁移通知渠道数据
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = cursor.fetchone()[0]

                if count > 0:
                    cursor.execute(f"SELECT * FROM {table_name}")
                    old_data = cursor.fetchall()

                    for row in old_data:
                        # 处理数据格式转换
                        cursor.execute('''
                        INSERT OR IGNORE INTO notification_channels
                        (name, user_id, type, config, enabled)
                        VALUES (?, ?, ?, ?, ?)
                        ''', (
                            row[1] if len(row) > 1 else f"迁移渠道_{row[0]}",
                            row[2] if len(row) > 2 else 1,  # 默认admin用户
                            self._normalize_channel_type(row[3] if len(row) > 3 else 'qq'),
                            row[4] if len(row) > 4 else '{}',
                            row[5] if len(row) > 5 else True
                        ))

                    logger.info(f"成功迁移 {count} 条通知渠道数据")

                    # 迁移完成后删除老表
                    cursor.execute(f"DROP TABLE {table_name}")
                    logger.info(f"已删除遗留表: {table_name}")

        except Exception as e:
            logger.error(f"迁移表 {table_name} 数据失败: {e}")

    def _normalize_channel_type(self, old_type: str) -> str:
        """标准化通知渠道类型"""
        type_mapping = {
            'ding_talk': 'dingtalk',
            'dingtalk': 'dingtalk',
            'qq': 'qq',
            'email': 'email',
            'webhook': 'webhook',
            'wechat': 'wechat',
            'telegram': 'telegram',
            # 处理一些可能的变体
            'dingding': 'dingtalk',
            'weixin': 'wechat',
            'tg': 'telegram'
        }
        return type_mapping.get(old_type.lower(), 'qq')
    
    def _migrate_keywords_table_constraints(self, cursor):
        """迁移keywords表的约束，支持基于商品ID的唯一性校验"""
        try:
            # 检查是否已经迁移过（通过检查是否存在新的唯一索引）
            cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_keywords_unique_with_item'")
            if cursor.fetchone():
                logger.info("keywords表约束已经迁移过，跳过")
                return

            logger.info("开始迁移keywords表约束...")

            # 1. 创建临时表，不设置主键约束
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS keywords_temp (
                cookie_id TEXT,
                keyword TEXT,
                reply TEXT,
                item_id TEXT,
                FOREIGN KEY (cookie_id) REFERENCES cookies(id) ON DELETE CASCADE
            )
            ''')

            # 2. 复制现有数据到临时表
            cursor.execute('''
            INSERT INTO keywords_temp (cookie_id, keyword, reply, item_id)
            SELECT cookie_id, keyword, reply, item_id FROM keywords
            ''')

            # 3. 删除原表
            cursor.execute('DROP TABLE keywords')

            # 4. 重命名临时表
            cursor.execute('ALTER TABLE keywords_temp RENAME TO keywords')

            # 5. 创建复合唯一索引来实现我们需要的约束逻辑
            # 对于item_id为空的情况：(cookie_id, keyword)必须唯一
            cursor.execute('''
            CREATE UNIQUE INDEX idx_keywords_unique_no_item
            ON keywords(cookie_id, keyword)
            WHERE item_id IS NULL OR item_id = ''
            ''')

            # 对于item_id不为空的情况：(cookie_id, keyword, item_id)必须唯一
            cursor.execute('''
            CREATE UNIQUE INDEX idx_keywords_unique_with_item
            ON keywords(cookie_id, keyword, item_id)
            WHERE item_id IS NOT NULL AND item_id != ''
            ''')

            logger.info("keywords表约束迁移完成")

        except Exception as e:
            logger.error(f"迁移keywords表约束失败: {e}")
            # 如果迁移失败，尝试回滚
            try:
                cursor.execute('DROP TABLE IF EXISTS keywords_temp')
            except Exception:
                pass
            raise

    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            self.conn = None
    
    def get_connection(self):
        """获取数据库连接，如果已关闭则重新连接"""
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        return self.conn

    def _log_sql(self, sql: str, params: tuple = None, operation: str = "EXECUTE"):
        """记录SQL执行日志"""
        if not self.sql_log_enabled:
            return

        # 格式化参数
        params_str = ""
        if params:
            if isinstance(params, (list, tuple)):
                if len(params) > 0:
                    # 限制参数长度，避免日志过长
                    formatted_params = []
                    for param in params:
                        if isinstance(param, str) and len(param) > 100:
                            formatted_params.append(f"{param[:100]}...")
                        else:
                            formatted_params.append(repr(param))
                    params_str = f" | 参数: [{', '.join(formatted_params)}]"

        # 格式化SQL（移除多余空白）
        formatted_sql = ' '.join(sql.split())

        # 根据配置的日志级别输出
        log_message = f"🗄️ SQL {operation}: {formatted_sql}{params_str}"

        if self.sql_log_level == 'DEBUG':
            logger.debug(log_message)
        elif self.sql_log_level == 'INFO':
            logger.info(log_message)
        elif self.sql_log_level == 'WARNING':
            logger.warning(log_message)
        else:
            logger.debug(log_message)

    def _execute_sql(self, cursor, sql: str, params: tuple = None):
        """执行SQL并记录日志"""
        self._log_sql(sql, params, "EXECUTE")
        if params:
            return cursor.execute(sql, params)
        else:
            return cursor.execute(sql)

    def _executemany_sql(self, cursor, sql: str, params_list):
        """批量执行SQL并记录日志"""
        self._log_sql(sql, f"批量执行 {len(params_list)} 条记录", "EXECUTEMANY")
        return cursor.executemany(sql, params_list)
    
    # -------------------- Cookie操作 --------------------
    def update_auto_confirm(self, cookie_id: str, auto_confirm: bool) -> bool:
        """更新Cookie的自动确认发货设置"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                self._execute_sql(cursor, "UPDATE cookies SET auto_confirm = ? WHERE id = ?", (int(auto_confirm), cookie_id))
                self.conn.commit()
                logger.info(f"更新账号 {cookie_id} 自动确认发货设置: {'开启' if auto_confirm else '关闭'}")
                return True
            except Exception as e:
                logger.error(f"更新自动确认发货设置失败: {e}")
                return False

    def get_auto_confirm(self, cookie_id: str) -> bool:
        """获取Cookie的自动确认发货设置"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                self._execute_sql(cursor, "SELECT auto_confirm FROM cookies WHERE id = ?", (cookie_id,))
                result = cursor.fetchone()
                if result:
                    return bool(result[0])
                return True  # 默认开启
            except Exception as e:
                logger.error(f"获取自动确认发货设置失败: {e}")
                return True  # 出错时默认开启
    
    # -------------------- 关键字操作 --------------------
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

    def _upgrade_password_hash(self, username: str, new_hash: str) -> None:
        """静默升级用户密码哈希（内部使用）"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP
                WHERE username = ?
                ''', (new_hash, username))
                if cursor.rowcount > 0:
                    self.conn.commit()
                    logger.debug(f"用户 {username} 密码哈希已自动升级为bcrypt")
            except Exception as e:
                logger.error(f"密码哈希自动升级失败: {e}")
                self.conn.rollback()

    def generate_verification_code(self) -> str:
        """生成6位数字验证码"""
        return ''.join(random.choices(string.digits, k=6))

    def generate_captcha(self) -> Tuple[str, str]:
        """生成图形验证码
        返回: (验证码文本, base64编码的图片)
        """
        try:
            # 生成4位随机验证码（数字+字母）
            chars = string.ascii_uppercase + string.digits
            captcha_text = ''.join(random.choices(chars, k=4))

            # 创建图片
            width, height = 120, 40
            image = Image.new('RGB', (width, height), color='white')
            draw = ImageDraw.Draw(image)

            # 尝试使用系统字体，如果失败则使用默认字体
            try:
                # Windows系统字体
                font = ImageFont.truetype("arial.ttf", 20)
            except Exception:
                try:
                    # 备用字体
                    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 20)
                except Exception:
                    # 使用默认字体
                    font = ImageFont.load_default()

            # 绘制验证码文本
            for i, char in enumerate(captcha_text):
                # 随机颜色
                color = (
                    random.randint(0, 100),
                    random.randint(0, 100),
                    random.randint(0, 100)
                )

                # 随机位置（稍微偏移）
                x = 20 + i * 20 + random.randint(-3, 3)
                y = 8 + random.randint(-3, 3)

                draw.text((x, y), char, font=font, fill=color)

            # 添加干扰线
            for _ in range(3):
                start = (random.randint(0, width), random.randint(0, height))
                end = (random.randint(0, width), random.randint(0, height))
                draw.line([start, end], fill=(random.randint(100, 200), random.randint(100, 200), random.randint(100, 200)), width=1)

            # 添加干扰点
            for _ in range(20):
                x = random.randint(0, width)
                y = random.randint(0, height)
                draw.point((x, y), fill=(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)))

            # 转换为base64
            buffer = io.BytesIO()
            image.save(buffer, format='PNG')
            img_base64 = base64.b64encode(buffer.getvalue()).decode()

            return captcha_text, f"data:image/png;base64,{img_base64}"

        except Exception as e:
            logger.error(f"生成图形验证码失败: {e}")
            # 返回简单的文本验证码作为备用
            simple_code = ''.join(random.choices(string.digits, k=4))
            return simple_code, ""

    def save_captcha(self, session_id: str, captcha_text: str, expires_minutes: int = 5) -> bool:
        """保存图形验证码"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                expires_at = time.time() + (expires_minutes * 60)

                # 删除该session的旧验证码
                cursor.execute('DELETE FROM captcha_codes WHERE session_id = ?', (session_id,))

                cursor.execute('''
                INSERT INTO captcha_codes (session_id, code, expires_at)
                VALUES (?, ?, ?)
                ''', (session_id, captcha_text.upper(), expires_at))

                self.conn.commit()
                logger.debug(f"保存图形验证码成功: {session_id}")
                return True
            except Exception as e:
                logger.error(f"保存图形验证码失败: {e}")
                self.conn.rollback()
                return False

    def verify_captcha(self, session_id: str, user_input: str) -> bool:
        """验证图形验证码"""
        with self.lock:
            try:
                cursor = self.conn.cursor()
                current_time = time.time()

                # 查找有效的验证码
                cursor.execute('''
                SELECT id FROM captcha_codes
                WHERE session_id = ? AND code = ? AND expires_at > ?
                ORDER BY created_at DESC LIMIT 1
                ''', (session_id, user_input.upper(), current_time))

                row = cursor.fetchone()
                if row:
                    # 删除已使用的验证码
                    cursor.execute('DELETE FROM captcha_codes WHERE id = ?', (row[0],))
                    self.conn.commit()
                    logger.debug(f"图形验证码验证成功: {session_id}")
                    return True
                else:
                    logger.warning(f"图形验证码验证失败: {session_id} - {user_input}")
                    return False
            except Exception as e:
                logger.error(f"验证图形验证码失败: {e}")
                return False

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

您好！

感谢您使用闲鱼自动回复系统。为了确保账户安全，请使用以下验证码完成邮箱验证：

验证码：{code}

重要提醒：
• 验证码有效期为 10 分钟，请及时使用
• 请勿将验证码分享给任何人
• 如非本人操作，请忽略此邮件
• 系统不会主动索要您的验证码

如果您在使用过程中遇到任何问题，请联系我们的技术支持团队。
感谢您选择闲鱼自动回复系统！

---
此邮件由系统自动发送，请勿直接回复
© 2025 闲鱼自动回复系统"""

            # 从系统设置读取SMTP配置
            try:
                smtp_server = self.get_system_setting('smtp_server') or ''
                smtp_port = int(self.get_system_setting('smtp_port') or 0)
                smtp_user = self.get_system_setting('smtp_user') or ''
                smtp_password = self.get_system_setting('smtp_password') or ''
                smtp_from = (self.get_system_setting('smtp_from') or '').strip() or smtp_user
                smtp_use_tls = (self.get_system_setting('smtp_use_tls') or 'true').lower() == 'true'
                smtp_use_ssl = (self.get_system_setting('smtp_use_ssl') or 'false').lower() == 'true'
            except Exception as e:
                logger.error(f"读取SMTP系统设置失败: {e}")
                # 如果读取配置失败，使用API方式
                return await self._send_email_via_api(email, subject, text_content)

            # 检查SMTP配置是否完整
            if smtp_server and smtp_port and smtp_user and smtp_password:
                # 配置完整，使用SMTP方式发送
                logger.info(f"使用SMTP方式发送验证码邮件: {email}")
                return await self._send_email_via_smtp(email, subject, text_content,
                                                     smtp_server, smtp_port, smtp_user,
                                                     smtp_password, smtp_from, smtp_use_tls, smtp_use_ssl)
            else:
                # 配置不完整，使用API方式发送
                logger.info(f"SMTP配置不完整，使用API方式发送验证码邮件: {email}")
                return await self._send_email_via_api(email, subject, text_content)

        except Exception as e:
            logger.error(f"发送验证码邮件异常: {e}")
            return False

    async def _send_email_via_smtp(self, email: str, subject: str, text_content: str,
                                 smtp_server: str, smtp_port: int, smtp_user: str,
                                 smtp_password: str, smtp_from: str, smtp_use_tls: bool, smtp_use_ssl: bool) -> bool:
        """使用SMTP方式发送邮件"""
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            msg = MIMEMultipart()
            msg['Subject'] = subject
            msg['From'] = smtp_from
            msg['To'] = email

            msg.attach(MIMEText(text_content, 'plain', 'utf-8'))

            if smtp_use_ssl:
                server = smtplib.SMTP_SSL(smtp_server, smtp_port)
            else:
                server = smtplib.SMTP(smtp_server, smtp_port)

            server.ehlo()
            if smtp_use_tls and not smtp_use_ssl:
                server.starttls()
                server.ehlo()

            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, [email], msg.as_string())
            server.quit()

            logger.info(f"验证码邮件发送成功(SMTP): {email}")
            return True
        except Exception as e:
            logger.error(f"SMTP发送验证码邮件失败: {e}")
            # SMTP发送失败，尝试使用API方式
            logger.info(f"SMTP发送失败，尝试使用API方式发送: {email}")
            return await self._send_email_via_api(email, subject, text_content)

    async def _send_email_via_api(self, email: str, subject: str, text_content: str) -> bool:
        """使用API方式发送邮件"""
        try:
            import aiohttp

            # 使用GET请求发送邮件
            api_url = "https://dy.zhinianboke.com/api/emailSend"
            params = {
                'subject': subject,
                'receiveUser': email,
                'sendHtml': text_content
            }

            async with aiohttp.ClientSession() as session:
                try:
                    logger.info(f"使用API发送验证码邮件: {email}")
                    async with session.get(api_url, params=params, timeout=15) as response:
                        response_text = await response.text()
                        logger.info(f"邮件API响应: {response.status}")

                        if response.status == 200:
                            logger.info(f"验证码邮件发送成功(API): {email}")
                            return True
                        else:
                            logger.error(f"API发送验证码邮件失败: {email}, 状态码: {response.status}, 响应: {response_text[:200]}")
                            return False
                except Exception as e:
                    logger.error(f"API邮件发送异常: {email}, 错误: {e}")
                    return False
        except Exception as e:
            logger.error(f"API邮件发送方法异常: {e}")
            return False

    # ==================== 卡券管理方法 ====================

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

    def get_table_data(self, table_name: str):
        """获取指定表的所有数据"""
        _validate_table_name(table_name)
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

    def delete_table_record(self, table_name: str, record_id: str):
        """删除指定表的指定记录"""
        _validate_table_name(table_name)
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
        _validate_table_name(table_name)
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

    def get_daily_quota(self, cookie_id: str) -> dict:
        """获取当日操作计数"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                today = time.strftime('%Y-%m-%d')
                cursor.execute('''
                    SELECT auto_reply_count, auto_delivery_count
                    FROM daily_quota WHERE cookie_id = ? AND date = ?
                ''', (cookie_id, today))
                row = cursor.fetchone()
                if row:
                    return {'auto_reply_count': row[0], 'auto_delivery_count': row[1], 'date': today}
                return {'auto_reply_count': 0, 'auto_delivery_count': 0, 'date': today}
        except Exception:
            return {'auto_reply_count': 0, 'auto_delivery_count': 0, 'date': today}

    def increment_daily_quota(self, cookie_id: str, quota_type: str) -> dict:
        """增加当日操作计数"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                today = time.strftime('%Y-%m-%d')
                field = 'auto_reply_count' if quota_type == 'reply' else 'auto_delivery_count'
                cursor.execute(f'''
                    INSERT INTO daily_quota (cookie_id, date, auto_reply_count, auto_delivery_count)
                    VALUES (?, ?, 0, 0)
                    ON CONFLICT(cookie_id, date) DO UPDATE SET
                        {field} = {field} + 1
                ''', (cookie_id, today))
                self.conn.commit()
                return self.get_daily_quota(cookie_id)
        except Exception:
            return {'auto_reply_count': 0, 'auto_delivery_count': 0, 'date': today}

    def check_daily_quota(self, cookie_id: str, quota_type: str) -> tuple:
        """检查是否超出配额，返回(是否允许, 当前计数, 上限)"""
        config = self.get_quota_config()
        quota = self.get_daily_quota(cookie_id)

        if quota_type == 'reply':
            current = quota['auto_reply_count']
            limit = config['daily_reply_limit']
        else:
            current = quota['auto_delivery_count']
            limit = config['daily_delivery_limit']

        allowed = current < limit
        return (allowed, current, limit)

    def cleanup_expired_sessions(self):
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute('DELETE FROM user_sessions WHERE expires_at<?', (time.time(),))
            self.conn.commit()


# 全局单例
db_manager = DBManager()

# 确保进程结束时关闭数据库连接
import atexit
atexit.register(db_manager.close)
