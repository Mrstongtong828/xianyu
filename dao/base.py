# -*- coding: utf-8 -*-
import sqlite3
import os
import threading
import hashlib
import time
from utils.crypto import encrypt_value, decrypt_value
import json
import random
import string
import aiohttp
import io
import base64
from PIL import Image, ImageDraw, ImageFont
from typing import List, Tuple, Dict, Optional, Any
from loguru import logger

class DBManagerBase:
    """SQLite数据库管理基类，提供连接、锁和基础SQL执行能力"""
    
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
        self.sql_log_enabled = False  # 默认关闭SQL日志，生产环境避免日志膨胀
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

            # 创建主动询价记录表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS active_outreach (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cookie_id TEXT NOT NULL,
                item_url TEXT NOT NULL,
                item_title TEXT DEFAULT '',
                seller_id TEXT DEFAULT '',
                seller_name TEXT DEFAULT '',
                chat_id TEXT DEFAULT '',
                message TEXT NOT NULL DEFAULT '',
                reply TEXT DEFAULT '',
                status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'sending', 'sent', 'replied', 'failed')),
                error_message TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cookie_id) REFERENCES cookies (id) ON DELETE CASCADE
            )
            ''')

            # 创建砍价会话表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS bargain_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cookie_id TEXT NOT NULL,
                item_url TEXT NOT NULL,
                item_id TEXT DEFAULT '',
                item_title TEXT DEFAULT '',
                seller_id TEXT DEFAULT '',
                seller_name TEXT DEFAULT '',
                chat_id TEXT DEFAULT '',
                target_price REAL NOT NULL DEFAULT 0,
                current_round INTEGER NOT NULL DEFAULT 0,
                max_rounds INTEGER NOT NULL DEFAULT 5,
                initial_message TEXT DEFAULT '',
                last_seller_message TEXT DEFAULT '',
                last_buyer_message TEXT DEFAULT '',
                status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'sending', 'active', 'success', 'failed', 'cancelled')),
                result_price REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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

            # 检查并添加 receiver_city 列（用于仪表盘地区分布统计）
            try:
                self._execute_sql(cursor, "SELECT receiver_city FROM orders LIMIT 1")
            except sqlite3.OperationalError:
                logger.info("正在为 orders 表添加 receiver_city 列...")
                self._execute_sql(cursor, "ALTER TABLE orders ADD COLUMN receiver_city TEXT DEFAULT ''")
                logger.info("orders 表 receiver_city 列添加完成")

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
                    except:
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

            # 迁移遗留数据（在所有版本升级完成后执行）
            self.migrate_legacy_data(cursor)

        except Exception as e:
            logger.error(f"数据库版本检查或升级失败: {e}")
            raise
            
    def update_admin_user_id(self, cursor):
        """更新admin用户ID"""
        try:
            logger.info("开始更新admin用户ID...")
            # 创建默认admin用户（只在首次初始化时创建）
            cursor.execute('SELECT COUNT(*) FROM users WHERE username = ?', ('admin',))
            admin_exists = cursor.fetchone()[0] > 0

            if not admin_exists:
                # 首次创建admin用户，设置默认密码
                default_password_hash = hashlib.sha256("admin123".encode()).hexdigest()
                cursor.execute('''
                INSERT INTO users (username, email, password_hash) VALUES
                ('admin', 'admin@localhost', ?)
                ''', (default_password_hash,))
                logger.info("创建默认admin用户，密码: admin123")

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
            
    def upgrade_notification_channels_table(self, cursor):
        """升级notification_channels表的type字段约束"""
        try:
            logger.info("开始升级notification_channels表...")
            
            # 检查表是否存在
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='notification_channels'")
            if not cursor.fetchone():
                logger.info("notification_channels表不存在，无需升级")
                return True
                
            # 检查表中是否有数据
            cursor.execute("SELECT COUNT(*) FROM notification_channels")
            count = cursor.fetchone()[0]

            # 删除可能存在的临时表
            cursor.execute("DROP TABLE IF EXISTS notification_channels_new")

            # 创建临时表
            cursor.execute('''
            CREATE TABLE notification_channels_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                type TEXT NOT NULL CHECK (type IN ('qq','ding_talk')),
                config TEXT NOT NULL,
                enabled BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            # 复制数据，并转换不兼容的类型
            if count > 0:
                logger.info(f"复制 {count} 条通知渠道数据到新表")
                # 先查看现有数据的类型
                cursor.execute("SELECT DISTINCT type FROM notification_channels")
                existing_types = [row[0] for row in cursor.fetchall()]
                logger.info(f"现有通知渠道类型: {existing_types}")

                # 获取所有现有数据进行逐行处理
                cursor.execute("SELECT * FROM notification_channels")
                existing_data = cursor.fetchall()

                # 逐行转移数据，确保类型映射正确
                for row in existing_data:
                    old_type = row[3] if len(row) > 3 else 'qq'  # type字段，默认为qq

                    # 类型映射规则
                    type_mapping = {
                        'dingtalk': 'ding_talk',
                        'ding_talk': 'ding_talk',
                        'qq': 'qq',
                        'email': 'qq',  # 暂时映射为qq，后续版本会支持
                        'webhook': 'qq',  # 暂时映射为qq，后续版本会支持
                        'wechat': 'qq',  # 暂时映射为qq，后续版本会支持
                        'telegram': 'qq'  # 暂时映射为qq，后续版本会支持
                    }

                    new_type = type_mapping.get(old_type, 'qq')  # 默认转换为qq类型

                    if old_type != new_type:
                        logger.info(f"转换通知渠道类型: {old_type} -> {new_type}")

                    # 插入到新表
                    cursor.execute('''
                    INSERT INTO notification_channels_new
                    (id, name, user_id, type, config, enabled, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        row[0],  # id
                        row[1],  # name
                        row[2],  # user_id
                        new_type,  # type (转换后的)
                        row[4] if len(row) > 4 else '{}',  # config
                        row[5] if len(row) > 5 else True,  # enabled
                        row[6] if len(row) > 6 else None,  # created_at
                        row[7] if len(row) > 7 else None   # updated_at
                    ))
            
            # 删除旧表
            cursor.execute("DROP TABLE notification_channels")
            
            # 重命名新表
            cursor.execute("ALTER TABLE notification_channels_new RENAME TO notification_channels")
            
            logger.info("notification_channels表升级完成")
            return True
        except Exception as e:
            logger.error(f"升级notification_channels表失败: {e}")
            raise

    def upgrade_notification_channels_types(self, cursor):
        """升级notification_channels表支持更多渠道类型"""
        try:
            logger.info("开始升级notification_channels表支持更多渠道类型...")

            # 检查表是否存在
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='notification_channels'")
            if not cursor.fetchone():
                logger.info("notification_channels表不存在，无需升级")
                return True

            # 检查表中是否有数据
            cursor.execute("SELECT COUNT(*) FROM notification_channels")
            count = cursor.fetchone()[0]

            # 获取现有数据
            existing_data = []
            if count > 0:
                cursor.execute("SELECT * FROM notification_channels")
                existing_data = cursor.fetchall()
                logger.info(f"备份 {count} 条通知渠道数据")

            # 创建新表，支持所有通知渠道类型
            cursor.execute('''
            CREATE TABLE notification_channels_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                type TEXT NOT NULL CHECK (type IN ('qq','ding_talk','dingtalk','feishu','lark','bark','email','webhook','wechat','telegram')),
                config TEXT NOT NULL,
                enabled BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')

            # 复制数据，同时处理类型映射
            if existing_data:
                logger.info(f"迁移 {len(existing_data)} 条通知渠道数据到新表")
                for row in existing_data:
                    # 处理类型映射，支持更多渠道类型
                    old_type = row[3] if len(row) > 3 else 'qq'  # type字段

                    # 完整的类型映射规则，支持所有通知渠道
                    type_mapping = {
                        'ding_talk': 'dingtalk',  # 统一为dingtalk
                        'dingtalk': 'dingtalk',
                        'qq': 'qq',
                        'feishu': 'feishu',      # 飞书通知
                        'lark': 'lark',          # 飞书通知（英文名）
                        'bark': 'bark',          # Bark通知
                        'email': 'email',        # 邮件通知
                        'webhook': 'webhook',    # Webhook通知
                        'wechat': 'wechat',      # 微信通知
                        'telegram': 'telegram'   # Telegram通知
                    }

                    new_type = type_mapping.get(old_type, 'qq')  # 默认为qq

                    if old_type != new_type:
                        logger.info(f"转换通知渠道类型: {old_type} -> {new_type}")

                    # 插入到新表，确保字段完整性
                    cursor.execute('''
                    INSERT INTO notification_channels_new
                    (id, name, user_id, type, config, enabled, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        row[0],  # id
                        row[1],  # name
                        row[2],  # user_id
                        new_type,  # type (转换后的)
                        row[4] if len(row) > 4 else '{}',  # config
                        row[5] if len(row) > 5 else True,  # enabled
                        row[6] if len(row) > 6 else None,  # created_at
                        row[7] if len(row) > 7 else None   # updated_at
                    ))

            # 删除旧表
            cursor.execute("DROP TABLE notification_channels")

            # 重命名新表
            cursor.execute("ALTER TABLE notification_channels_new RENAME TO notification_channels")

            logger.info("notification_channels表类型升级完成")
            logger.info("✅ 现在支持以下所有通知渠道类型:")
            logger.info("   - qq (QQ通知)")
            logger.info("   - ding_talk/dingtalk (钉钉通知)")
            logger.info("   - feishu/lark (飞书通知)")
            logger.info("   - bark (Bark通知)")
            logger.info("   - email (邮件通知)")
            logger.info("   - webhook (Webhook通知)")
            logger.info("   - wechat (微信通知)")
            logger.info("   - telegram (Telegram通知)")
            return True
        except Exception as e:
            logger.error(f"升级notification_channels表类型失败: {e}")
            raise

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
            except:
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

