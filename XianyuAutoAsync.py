import asyncio
import json
import re
import time
import base64
import os
import random
from enum import Enum
from loguru import logger
import websockets
from utils.xianyu_utils import (
    decrypt, generate_mid, generate_uuid, trans_cookies,
    generate_device_id, generate_sign
)
from config import (
    WEBSOCKET_URL, HEARTBEAT_INTERVAL, HEARTBEAT_TIMEOUT,
    TOKEN_REFRESH_INTERVAL, TOKEN_RETRY_INTERVAL, COOKIES_STR,
    LOG_CONFIG, AUTO_REPLY, DEFAULT_HEADERS, WEBSOCKET_HEADERS,
    APP_CONFIG, API_ENDPOINTS
)
from config import config as cfg  # 导入config实例（不是模块），使用别名避免冲突
import sys
import aiohttp
from collections import defaultdict
from db_manager import db_manager
from xianyu_agent_adapter import agent_get_reply

# 滑块验证补丁已废弃，使用集成的 Playwright 登录方法
# 不再需要猴子补丁，所有功能已集成到 XianyuSliderStealth 类中

class ConnectionState(Enum):
    """WebSocket连接状态枚举"""
    DISCONNECTED = "disconnected"  # 未连接
    CONNECTING = "connecting"  # 连接中
    CONNECTED = "connected"  # 已连接
    RECONNECTING = "reconnecting"  # 重连中
    FAILED = "failed"  # 连接失败
    CLOSED = "closed"  # 已关闭


class AutoReplyPauseManager:
    """自动回复暂停管理器"""
    def __init__(self):
        # 存储每个chat_id的暂停信息 {chat_id: pause_until_timestamp}
        self.paused_chats = {}

    def pause_chat(self, chat_id: str, cookie_id: str):
        """暂停指定chat_id的自动回复，使用账号特定的暂停时间"""
        # 获取账号特定的暂停时间
        try:
            from db_manager import db_manager
            pause_minutes = db_manager.get_cookie_pause_duration(cookie_id)
        except Exception as e:
            logger.error(f"获取账号 {cookie_id} 暂停时间失败: {e}，使用默认10分钟")
            pause_minutes = 10

        # 如果暂停时间为0，表示不暂停
        if pause_minutes == 0:
            logger.info(f"【{cookie_id}】检测到手动发出消息，但暂停时间设置为0，不暂停自动回复")
            return

        pause_duration_seconds = pause_minutes * 60
        pause_until = time.time() + pause_duration_seconds
        self.paused_chats[chat_id] = pause_until

        # 计算暂停结束时间
        end_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(pause_until))
        logger.info(f"【{cookie_id}】检测到手动发出消息，chat_id {chat_id} 自动回复暂停{pause_minutes}分钟，恢复时间: {end_time}")

    def is_chat_paused(self, chat_id: str) -> bool:
        """检查指定chat_id是否处于暂停状态"""
        if chat_id not in self.paused_chats:
            return False

        current_time = time.time()
        pause_until = self.paused_chats[chat_id]

        if current_time >= pause_until:
            # 暂停时间已过，移除记录
            del self.paused_chats[chat_id]
            return False

        return True

    def get_remaining_pause_time(self, chat_id: str) -> int:
        """获取指定chat_id剩余暂停时间（秒）"""
        if chat_id not in self.paused_chats:
            return 0

        current_time = time.time()
        pause_until = self.paused_chats[chat_id]
        remaining = max(0, int(pause_until - current_time))

        return remaining

    def resume_chat(self, chat_id: str) -> bool:
        """立即恢复指定chat_id的自动回复"""
        if chat_id in self.paused_chats:
            del self.paused_chats[chat_id]
            return True
        return False

    def resume_all(self) -> int:
        """恢复所有暂停的对话，返回恢复数量"""
        count = len(self.paused_chats)
        self.paused_chats.clear()
        return count

    def get_paused_chats(self) -> list:
        """获取所有暂停中的chat_id列表"""
        self.cleanup_expired_pauses()
        return list(self.paused_chats.keys())

    def cleanup_expired_pauses(self):
        """清理已过期的暂停记录"""
        current_time = time.time()
        expired_chats = [chat_id for chat_id, pause_until in self.paused_chats.items()
                        if current_time >= pause_until]

        for chat_id in expired_chats:
            del self.paused_chats[chat_id]


# 全局暂停管理器实例
pause_manager = AutoReplyPauseManager()

def log_captcha_event(cookie_id: str, event_type: str, success: bool = None, details: str = ""):
    """
    简单记录滑块验证事件到txt文件

    Args:
        cookie_id: 账号ID
        event_type: 事件类型 (检测到/开始处理/成功/失败)
        success: 是否成功 (None表示进行中)
        details: 详细信息
    """
    try:
        log_dir = 'logs'
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, 'captcha_verification.txt')

        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        status = "成功" if success is True else "失败" if success is False else "进行中"

        log_entry = f"[{timestamp}] 【{cookie_id}】{event_type} - {status}"
        if details:
            log_entry += f" - {details}"
        log_entry += "\n"

        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(log_entry)

    except Exception as e:
        logger.error(f"记录滑块验证日志失败: {e}")

# 日志配置
log_dir = 'logs'
os.makedirs(log_dir, exist_ok=True)
log_path = os.path.join(log_dir, f"xianyu_{time.strftime('%Y-%m-%d')}.log")
logger.remove()
logger.add(
    log_path,
    rotation=LOG_CONFIG.get('rotation', '1 day'),
    retention=LOG_CONFIG.get('retention', '7 days'),
    compression=LOG_CONFIG.get('compression', 'zip'),
    level=LOG_CONFIG.get('level', 'DEBUG'),
    format=LOG_CONFIG.get('format', '<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>'),
    encoding='utf-8',
    enqueue=True
)
logger.add(
    sys.stdout,
    level=LOG_CONFIG.get('level', 'DEBUG'),
    format=LOG_CONFIG.get('format', '<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>'),
    enqueue=True
)


# XianyuLive Mixin imports
from xianyu_mixins.connection_mixin import ConnectionMixin
from xianyu_mixins.message_mixin import MessageMixin
from xianyu_mixins.order_mixin import OrderMixin
from xianyu_mixins.reply_mixin import ReplyMixin
from xianyu_mixins.item_mixin import ItemMixin


class XianyuLive:
    # 类级别的锁字典，为每个order_id维护一个锁（用于自动发货）
    _order_locks = defaultdict(lambda: asyncio.Lock())
    # 记录锁的最后使用时间，用于清理
    _lock_usage_times = {}
    # 记录锁的持有状态和释放时间 {lock_key: {'locked': bool, 'release_time': float, 'task': asyncio.Task}}
    _lock_hold_info = {}
class XianyuLive(ConnectionMixin, MessageMixin, OrderMixin, ReplyMixin, ItemMixin):
    # 独立的锁字典，用于订单详情获取（不使用延迟锁机制）
    _order_detail_locks = defaultdict(lambda: asyncio.Lock())
    # 记录订单详情锁的使用时间
    _order_detail_lock_times = {}

    # 商品详情缓存（24小时有效）
    _item_detail_cache = {}  # {item_id: {'detail': str, 'timestamp': float, 'access_time': float}}
    _item_detail_cache_lock = asyncio.Lock()
    _item_detail_cache_max_size = 1000  # 最大缓存1000个商品
    _item_detail_cache_ttl = 24 * 60 * 60  # 24小时TTL

    # 类级别的实例管理字典，用于API调用
    _instances = {}  # {cookie_id: XianyuLive实例}
    _instances_lock = asyncio.Lock()
    
    # 类级别的密码登录时间记录，用于防止重复登录
    _last_password_login_time = {}  # {cookie_id: timestamp}
    _password_login_cooldown = 60  # 密码登录冷却时间：60秒
    
    def _safe_str(self, e):
        """安全地将异常转换为字符串"""
        try:
            return str(e)
        except:
            try:
                return repr(e)
            except:
                return "未知错误"

    async def _interruptible_sleep(self, duration: float):
        """可中断的sleep，将长时间sleep拆分成多个短时间sleep，以便及时响应取消信号
        
        Args:
            duration: 总睡眠时间（秒）
        """
        # 将长时间sleep拆分成多个1秒的短sleep，这样可以及时响应取消信号
        chunk_size = 1.0  # 每次sleep 1秒
        remaining = duration
        
        while remaining > 0:
            sleep_time = min(chunk_size, remaining)
            try:
                await asyncio.sleep(sleep_time)
                remaining -= sleep_time
            except asyncio.CancelledError:
                # 如果收到取消信号，立即抛出
                raise

    def _reset_background_tasks(self):
        """直接重置后台任务引用，不等待取消（用于快速重连）
        
        注意：只重置心跳任务，因为只有心跳任务依赖WebSocket连接。
        其他任务（Token刷新、清理、Cookie刷新）不依赖WebSocket，可以继续运行。
        """
        logger.info(f"【{self.cookie_id}】准备重置后台任务引用（仅重置依赖WebSocket的任务）...")
        
        # 只处理心跳任务（依赖WebSocket，需要重启）
        if self.heartbeat_task:
            status = "已完成" if self.heartbeat_task.done() else "运行中"
            logger.info(f"【{self.cookie_id}】发现心跳任务（状态: {status}），需要重置（因为依赖WebSocket连接）")
            # 尝试取消心跳任务（但不等待）
            if not self.heartbeat_task.done():
                try:
                    self.heartbeat_task.cancel()
                    logger.debug(f"【{self.cookie_id}】已发送取消信号给心跳任务（不等待响应）")
                except Exception as e:
                    logger.warning(f"【{self.cookie_id}】取消心跳任务失败: {e}")
            # 重置心跳任务引用
            self.heartbeat_task = None
            logger.info(f"【{self.cookie_id}】心跳任务引用已重置")
        else:
            logger.info(f"【{self.cookie_id}】没有心跳任务需要重置")
        
        # 检查其他任务的状态（这些任务不依赖WebSocket，不需要重启）
        other_tasks_status = []
        if self.token_refresh_task:
            status = "已完成" if self.token_refresh_task.done() else "运行中"
            other_tasks_status.append(f"Token刷新任务({status})")
        if self.cleanup_task:
            status = "已完成" if self.cleanup_task.done() else "运行中"
            other_tasks_status.append(f"清理任务({status})")
        if self.cookie_refresh_task:
            status = "已完成" if self.cookie_refresh_task.done() else "运行中"
            other_tasks_status.append(f"Cookie刷新任务({status})")
        if self.item_sync_task:
            status = "已完成" if self.item_sync_task.done() else "运行中"
            other_tasks_status.append(f"商品同步任务({status})")
        if self.item_schedule_task:
            status = "已完成" if self.item_schedule_task.done() else "运行中"
            other_tasks_status.append(f"智能上下架任务({status})")

        if other_tasks_status:
            logger.info(f"【{self.cookie_id}】其他任务继续运行（不依赖WebSocket）: {', '.join(other_tasks_status)}")
        else:
            logger.info(f"【{self.cookie_id}】没有其他任务在运行")
        
        logger.info(f"【{self.cookie_id}】任务重置完成，可以立即创建新的心跳任务")

    async def _cancel_background_tasks(self):
        """取消并清理所有后台任务（保留此方法用于程序退出时的完整清理）"""
        try:
            tasks_to_cancel = []
            
            # 收集所有需要取消的任务（只收集未完成的任务）
            if self.heartbeat_task:
                if not self.heartbeat_task.done():
                    tasks_to_cancel.append(("心跳任务", self.heartbeat_task))
                else:
                    logger.debug(f"【{self.cookie_id}】心跳任务已完成，跳过")
                    
            if self.token_refresh_task:
                if not self.token_refresh_task.done():
                    tasks_to_cancel.append(("Token刷新任务", self.token_refresh_task))
                else:
                    logger.debug(f"【{self.cookie_id}】Token刷新任务已完成，跳过")
                    
            if self.cleanup_task:
                if not self.cleanup_task.done():
                    tasks_to_cancel.append(("清理任务", self.cleanup_task))
                else:
                    logger.debug(f"【{self.cookie_id}】清理任务已完成，跳过")
                    
            if self.cookie_refresh_task:
                if not self.cookie_refresh_task.done():
                    tasks_to_cancel.append(("Cookie刷新任务", self.cookie_refresh_task))
                else:
                    logger.debug(f"【{self.cookie_id}】Cookie刷新任务已完成，跳过")

            if self.delivery_retry_task:
                if not self.delivery_retry_task.done():
                    tasks_to_cancel.append(("发货重试任务", self.delivery_retry_task))
                else:
                    logger.debug(f"【{self.cookie_id}】发货重试任务已完成，跳过")

            if self.item_schedule_task:
                if not self.item_schedule_task.done():
                    tasks_to_cancel.append(("智能上下架任务", self.item_schedule_task))
                else:
                    logger.debug(f"【{self.cookie_id}】智能上下架任务已完成，跳过")

            if self.item_sync_task:
                if not self.item_sync_task.done():
                    tasks_to_cancel.append(("商品同步任务", self.item_sync_task))
                else:
                    logger.debug(f"【{self.cookie_id}】商品同步任务已完成，跳过")

            if not tasks_to_cancel:
                logger.info(f"【{self.cookie_id}】没有后台任务需要取消（所有任务已完成或不存在）")
                # 立即重置任务引用
                self.heartbeat_task = None
                self.token_refresh_task = None
                self.cleanup_task = None
                self.cookie_refresh_task = None
                self.delivery_retry_task = None
                self.item_schedule_task = None
                self.item_sync_task = None
                return
            
            logger.info(f"【{self.cookie_id}】开始取消 {len(tasks_to_cancel)} 个未完成的后台任务...")
            
            # 取消所有任务
            for task_name, task in tasks_to_cancel:
                try:
                    if task.done():
                        logger.info(f"【{self.cookie_id}】任务已完成，跳过取消: {task_name}")
                    else:
                        task.cancel()
                        logger.info(f"【{self.cookie_id}】已发送取消信号: {task_name}")
                except Exception as e:
                    logger.warning(f"【{self.cookie_id}】取消任务失败 {task_name}: {e}")
            
            # 等待所有任务完成取消，使用合理的超时时间
            # 现在任务中已经添加了 await asyncio.sleep(0) 来让出控制权，应该能够响应取消信号
            tasks = [task for _, task in tasks_to_cancel]
            logger.info(f"【{self.cookie_id}】等待 {len(tasks)} 个任务响应取消信号...")
            
            wait_timeout = 5.0  # 增加超时时间到5秒，给任务更多时间响应取消信号
            
            start_time = time.time()
            try:
                # 只等待未完成的任务
                pending_tasks_list = [task for task in tasks if not task.done()]
                
                # 记录每个任务的状态
                for task_name, task in tasks_to_cancel:
                    status = "已完成" if task.done() else "运行中"
                    logger.info(f"【{self.cookie_id}】任务状态: {task_name} - {status}")
                
                if not pending_tasks_list:
                    logger.info(f"【{self.cookie_id}】所有任务已完成，无需等待")
                else:
                    logger.info(f"【{self.cookie_id}】等待 {len(pending_tasks_list)} 个未完成任务响应（超时时间: {wait_timeout}秒）...")
                    try:
                        # 使用 wait 等待任务完成，设置超时
                        logger.debug(f"【{self.cookie_id}】开始调用 asyncio.wait()...")
                        done, pending = await asyncio.wait(
                            pending_tasks_list,
                            timeout=wait_timeout,
                            return_when=asyncio.ALL_COMPLETED
                        )
                        elapsed = time.time() - start_time
                        logger.info(f"【{self.cookie_id}】asyncio.wait() 返回，耗时 {elapsed:.3f}秒，已完成: {len(done)}，未完成: {len(pending)}")
                        
                        # 检查已完成的任务，并记录详细信息
                        for task_name, task in tasks_to_cancel:
                            if task in done:
                                try:
                                    task.result()
                                    logger.warning(f"【{self.cookie_id}】⚠️ 任务正常完成（非取消）: {task_name}")
                                except asyncio.CancelledError:
                                    logger.info(f"【{self.cookie_id}】✅ 任务已成功取消: {task_name}")
                                except Exception as e:
                                    logger.warning(f"【{self.cookie_id}】⚠️ 任务取消时出现异常 {task_name}: {e}")
                        
                        if pending:
                            # 找出未完成的任务名称和详细信息
                            pending_names = []
                            for task_name, task in tasks_to_cancel:
                                if task in pending:
                                    pending_names.append(task_name)
                                    # 记录未完成任务的状态
                                    if task.done():
                                        try:
                                            task.result()
                                            logger.warning(f"【{self.cookie_id}】任务在等待期间完成: {task_name}")
                                        except asyncio.CancelledError:
                                            logger.info(f"【{self.cookie_id}】任务在等待期间被取消: {task_name}")
                                        except Exception as e:
                                            logger.warning(f"【{self.cookie_id}】任务在等待期间异常 {task_name}: {e}")
                                    else:
                                        logger.warning(f"【{self.cookie_id}】任务仍未完成: {task_name} (done={task.done()})")
                            
                            logger.warning(f"【{self.cookie_id}】等待超时 ({elapsed:.3f}秒)，以下任务可能仍在运行: {', '.join(pending_names)}")
                            
                            # 强制取消所有未完成的任务（再次尝试）
                            for task_name, task in tasks_to_cancel:
                                if task in pending and not task.done():
                                    try:
                                        task.cancel()
                                        logger.warning(f"【{self.cookie_id}】强制取消任务: {task_name}")
                                    except Exception as e:
                                        logger.warning(f"【{self.cookie_id}】强制取消任务失败 {task_name}: {e}")
                            
                            # 再等待一小段时间，看是否有任务响应
                            if pending:
                                try:
                                    done2, pending2 = await asyncio.wait(pending, timeout=1.0, return_when=asyncio.ALL_COMPLETED)
                                    for task_name, task in tasks_to_cancel:
                                        if task in done2:
                                            try:
                                                task.result()
                                            except asyncio.CancelledError:
                                                logger.info(f"【{self.cookie_id}】任务在二次等待期间被取消: {task_name}")
                                            except Exception as e:
                                                logger.warning(f"【{self.cookie_id}】任务在二次等待期间异常 {task_name}: {e}")
                                except Exception as e:
                                    logger.warning(f"【{self.cookie_id}】二次等待任务时出错: {e}")
                            
                            logger.warning(f"【{self.cookie_id}】强制继续重连流程，未完成的任务将在后台继续运行（但已标记为取消）")
                        else:
                            logger.info(f"【{self.cookie_id}】所有后台任务已取消 (耗时 {elapsed:.3f}秒)")
                            
                    except Exception as e:
                        elapsed = time.time() - start_time
                        logger.warning(f"【{self.cookie_id}】等待任务时出错 (耗时 {elapsed:.3f}秒): {e}")
                        import traceback
                        logger.warning(f"【{self.cookie_id}】等待任务异常堆栈:\n{traceback.format_exc()}")
                        
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error(f"【{self.cookie_id}】等待任务取消时出错 (耗时 {elapsed:.3f}秒): {e}")
                import traceback
                logger.error(f"【{self.cookie_id}】等待任务取消异常堆栈:\n{traceback.format_exc()}")
            
            logger.info(f"【{self.cookie_id}】任务取消流程完成，继续重连流程")
            
            # 最后检查一次所有任务的状态
            for task_name, task in tasks_to_cancel:
                if task and not task.done():
                    logger.warning(f"【{self.cookie_id}】⚠️ 任务取消流程完成后，任务仍未完成: {task_name} (done={task.done()})")
                elif task and task.done():
                    logger.debug(f"【{self.cookie_id}】✅ 任务已完成: {task_name}")
        
        finally:
            # 使用 finally 确保无论发生什么情况都会重置任务引用
            # 这样可以保证下次重连时所有任务都会被重新创建
            self.heartbeat_task = None
            self.token_refresh_task = None
            self.cleanup_task = None
            self.cookie_refresh_task = None
            self.delivery_retry_task = None
            self.item_schedule_task = None
            self.item_sync_task = None
            logger.info(f"【{self.cookie_id}】后台任务引用已全部重置")

    def _calculate_retry_delay(self, error_msg: str) -> int:
        """根据错误类型和失败次数计算重试延迟"""
        # WebSocket意外断开 - 短延迟
        if "no close frame received or sent" in error_msg:
            return min(3 * self.connection_failures, 15)
        
        # 网络连接问题 - 长延迟
        elif "Connection refused" in error_msg or "timeout" in error_msg.lower():
            return min(10 * self.connection_failures, 60)
        
        # 其他未知错误 - 中等延迟
        else:
            return min(5 * self.connection_failures, 30)

    def _cleanup_instance_caches(self):
        """清理实例级别的缓存，防止内存泄漏"""
        try:
            current_time = time.time()
            cleaned_total = 0
            
            # 清理过期的通知记录（保留30分钟内的，从1小时优化）
            max_notification_age = 1800  # 30分钟（从3600优化）
            expired_notifications = [
                key for key, last_time in self.last_notification_time.items()
                if current_time - last_time > max_notification_age
            ]
            for key in expired_notifications:
                del self.last_notification_time[key]
            if expired_notifications:
                cleaned_total += len(expired_notifications)
                logger.warning(f"【{self.cookie_id}】清理了 {len(expired_notifications)} 个过期通知记录")
            
            # 清理过期的发货记录（保留30分钟内的）
            max_delivery_age = 1800  # 30分钟
            expired_deliveries = [
                order_id for order_id, last_time in self.last_delivery_time.items()
                if current_time - last_time > max_delivery_age
            ]
            for order_id in expired_deliveries:
                del self.last_delivery_time[order_id]
            if expired_deliveries:
                cleaned_total += len(expired_deliveries)
                logger.warning(f"【{self.cookie_id}】清理了 {len(expired_deliveries)} 个过期发货记录")
            
            # 清理过期的订单确认记录（保留30分钟内的）
            max_confirm_age = 1800  # 30分钟
            expired_confirms = [
                order_id for order_id, last_time in self.confirmed_orders.items()
                if current_time - last_time > max_confirm_age
            ]
            for order_id in expired_confirms:
                del self.confirmed_orders[order_id]
            if expired_confirms:
                cleaned_total += len(expired_confirms)
                logger.warning(f"【{self.cookie_id}】清理了 {len(expired_confirms)} 个过期订单确认记录")
            
            # 只有实际清理了内容才记录总数日志
            if cleaned_total > 0:
                logger.info(f"【{self.cookie_id}】实例缓存清理完成，共清理 {cleaned_total} 条记录")
                logger.warning(f"【{self.cookie_id}】当前缓存数量 - 通知: {len(self.last_notification_time)}, 发货: {len(self.last_delivery_time)}, 确认: {len(self.confirmed_orders)}")
        
        except Exception as e:
            logger.error(f"【{self.cookie_id}】清理实例缓存时出错: {self._safe_str(e)}")
    
    async def _cleanup_playwright_cache(self):
        """清理Playwright浏览器临时文件和缓存（Docker环境专用）"""
        try:
            import shutil
            import glob
            
            # 定义需要清理的临时目录路径
            temp_paths = [
                '/tmp/playwright-*',  # Playwright临时会话
                '/tmp/chromium-*',    # Chromium临时文件
                '/ms-playwright/chromium-*/Default/Cache',  # 浏览器缓存
                '/ms-playwright/chromium-*/Default/Code Cache',  # 代码缓存
                '/ms-playwright/chromium-*/Default/GPUCache',  # GPU缓存
            ]
            
            total_cleaned = 0
            total_size_mb = 0
            
            for pattern in temp_paths:
                try:
                    matching_paths = glob.glob(pattern)
                    for path in matching_paths:
                        try:
                            if os.path.exists(path):
                                # 计算大小
                                if os.path.isdir(path):
                                    size = sum(
                                        os.path.getsize(os.path.join(dirpath, filename))
                                        for dirpath, _, filenames in os.walk(path)
                                        for filename in filenames
                                    )
                                    shutil.rmtree(path, ignore_errors=True)
                                else:
                                    size = os.path.getsize(path)
                                    os.remove(path)
                                
                                total_size_mb += size / (1024 * 1024)
                                total_cleaned += 1
                        except Exception as e:
                            logger.warning(f"清理路径 {path} 时出错: {e}")
                except Exception as e:
                    logger.warning(f"匹配路径 {pattern} 时出错: {e}")
            
            if total_cleaned > 0:
                logger.info(f"【{self.cookie_id}】Playwright缓存清理完成: 删除了 {total_cleaned} 个文件/目录，释放 {total_size_mb:.2f} MB")
            else:
                logger.warning(f"【{self.cookie_id}】Playwright缓存清理: 没有需要清理的临时文件")
                
        except Exception as e:
            logger.warning(f"【{self.cookie_id}】清理Playwright缓存时出错: {self._safe_str(e)}")

    async def _cleanup_old_logs(self, retention_days: int = 7):
        """清理过期的日志文件
        
        Args:
            retention_days: 保留的天数，默认7天
            
        Returns:
            清理的文件数量
        """
        try:
            import glob
            from datetime import datetime, timedelta
            
            logs_dir = "logs"
            if not os.path.exists(logs_dir):
                logger.warning(f"【{self.cookie_id}】日志目录不存在: {logs_dir}")
                return 0
            
            # 计算过期时间点
            cutoff_time = datetime.now() - timedelta(days=retention_days)
            
            # 查找所有日志文件（包括.log和.log.zip）
            log_patterns = [
                os.path.join(logs_dir, "xianyu_*.log"),
                os.path.join(logs_dir, "xianyu_*.log.zip"),
                os.path.join(logs_dir, "app_*.log"),
                os.path.join(logs_dir, "app_*.log.zip"),
            ]
            
            total_cleaned = 0
            total_size_mb = 0
            
            for pattern in log_patterns:
                log_files = glob.glob(pattern)
                for log_file in log_files:
                    try:
                        # 获取文件修改时间
                        file_mtime = datetime.fromtimestamp(os.path.getmtime(log_file))
                        
                        # 如果文件早于保留期限，则删除
                        if file_mtime < cutoff_time:
                            file_size = os.path.getsize(log_file)
                            os.remove(log_file)
                            total_size_mb += file_size / (1024 * 1024)
                            total_cleaned += 1
                            logger.debug(f"【{self.cookie_id}】删除过期日志文件: {log_file} (修改时间: {file_mtime})")
                    except Exception as e:
                        logger.warning(f"【{self.cookie_id}】删除日志文件失败 {log_file}: {self._safe_str(e)}")
            
            if total_cleaned > 0:
                logger.info(f"【{self.cookie_id}】日志清理完成: 删除了 {total_cleaned} 个日志文件，释放 {total_size_mb:.2f} MB (保留 {retention_days} 天内的日志)")
            else:
                logger.debug(f"【{self.cookie_id}】日志清理: 没有需要清理的过期日志文件 (保留 {retention_days} 天)")
            
            return total_cleaned
            
        except Exception as e:
            logger.error(f"【{self.cookie_id}】清理日志文件时出错: {self._safe_str(e)}")
            return 0

    def __init__(self, cookies_str=None, cookie_id: str = "default", user_id: int = None):
        """初始化闲鱼直播类"""
        logger.info(f"【{cookie_id}】开始初始化XianyuLive...")

        if not cookies_str:
            cookies_str = COOKIES_STR
        if not cookies_str:
            raise ValueError("未提供cookies，请在global_config.yml中配置COOKIES_STR或通过参数传入")

        logger.info(f"【{cookie_id}】解析cookies...")
        self.cookies = trans_cookies(cookies_str)
        logger.info(f"【{cookie_id}】cookies解析完成，包含字段: {list(self.cookies.keys())}")

        self.cookie_id = cookie_id  # 唯一账号标识
        self.cookies_str = cookies_str  # 保存原始cookie字符串
        self.user_id = user_id  # 保存用户ID，用于token刷新时保持正确的所有者关系
        self.base_url = WEBSOCKET_URL

        if 'unb' not in self.cookies:
            raise ValueError(f"【{cookie_id}】Cookie中缺少必需的'unb'字段，当前字段: {list(self.cookies.keys())}")

        self.myid = self.cookies['unb']
        logger.info(f"【{cookie_id}】用户ID: {self.myid}")
        self.device_id = generate_device_id(self.myid)

        # 心跳相关配置
        self.heartbeat_interval = HEARTBEAT_INTERVAL
        self.heartbeat_timeout = HEARTBEAT_TIMEOUT
        self.last_heartbeat_time = 0
        self.last_heartbeat_response = 0
        self.heartbeat_task = None
        self.ws = None

        # Token刷新相关配置
        self.token_refresh_interval = TOKEN_REFRESH_INTERVAL
        self.token_retry_interval = TOKEN_RETRY_INTERVAL
        self.last_token_refresh_time = 0
        self.current_token = None
        self.token_refresh_task = None
        self.connection_restart_flag = False  # 连接重启标志

        # 通知防重复机制
        self.last_notification_time = {}  # 记录每种通知类型的最后发送时间
        self.notification_cooldown = 300  # 5分钟内不重复发送相同类型的通知
        self.token_refresh_notification_cooldown = 18000  # Token刷新异常通知冷却时间：3小时
        self.notification_lock = asyncio.Lock()  # 通知防重复机制的异步锁

        # 自动发货防重复机制
        self.last_delivery_time = {}  # 记录每个商品的最后发货时间
        self.delivery_cooldown = 600  # 10分钟内不重复发货

        # 自动确认发货防重复机制
        self.confirmed_orders = {}  # 记录已确认发货的订单，防止重复确认
        self.order_confirm_cooldown = 600  # 10分钟内不重复确认同一订单

        # 自动发货已发送订单记录
        self.delivery_sent_orders = set()  # 记录已发货的订单ID，防止重复发货

        self.session = None  # 用于API调用的aiohttp session

        # 启动定期清理过期暂停记录的任务
        self.cleanup_task = None

        # Cookie刷新定时任务
        self.cookie_refresh_task = None
        self.cookie_refresh_interval = 1200  # 1小时 = 3600秒

        # 发货失败重试任务
        self.delivery_retry_task = None

        # 智能上下架定时任务
        self.item_schedule_task = None

        self.last_cookie_refresh_time = 0
        self.cookie_refresh_lock = asyncio.Lock()  # 使用Lock防止重复执行Cookie刷新
        self.cookie_refresh_enabled = True  # 是否启用Cookie刷新功能

        # 商品同步定时任务
        self.item_sync_task = None
        self.item_sync_enabled = cfg.get('ITEM_SYNC', {}).get('enabled', True)
        self.item_sync_interval = cfg.get('ITEM_SYNC', {}).get('interval', 3600)  # 默认1小时
        self.item_sync_max_pages = cfg.get('ITEM_SYNC', {}).get('max_pages', 5)
        self.last_item_sync_time = 0
        self.item_sync_lock = asyncio.Lock()  # 使用Lock防止重复执行商品同步

        # 扫码登录Cookie刷新标志
        self.last_qr_cookie_refresh_time = 0  # 记录上次扫码登录Cookie刷新时间
        self.qr_cookie_refresh_cooldown = 600  # 扫码登录Cookie刷新后的冷却时间：10分钟

        # 消息接收标识 - 用于控制Cookie刷新
        self.last_message_received_time = 0  # 记录上次收到消息的时间
        self.message_cookie_refresh_cooldown = 300  # 收到消息后5分钟内不执行Cookie刷新

        # 浏览器Cookie刷新成功标志
        self.browser_cookie_refreshed = False  # 标记_refresh_cookies_via_browser是否成功更新过数据库
        self.restarted_in_browser_refresh = False  # 刷新流程内部是否已触发重启（用于去重）


        # 滑块验证相关
        self.captcha_verification_count = 0  # 滑块验证次数计数器
        self.max_captcha_verification_count = 3  # 最大滑块验证次数，防止无限递归

        # WebSocket连接监控
        self.connection_state = ConnectionState.DISCONNECTED  # 连接状态
        self.connection_failures = 0  # 连续连接失败次数
        self.max_connection_failures = 5  # 最大连续失败次数
        self.last_successful_connection = 0  # 上次成功连接时间
        self.last_state_change_time = time.time()  # 上次状态变化时间

        # 后台任务追踪（用于清理未等待的任务）
        self.background_tasks = set()  # 追踪所有后台任务
        
        # 消息处理并发控制（防止内存泄漏）
        self.message_semaphore = asyncio.Semaphore(100)  # 最多100个并发消息处理任务
        self.active_message_tasks = 0  # 当前活跃的消息处理任务数

        # 消息防抖管理器：用于处理用户连续发送消息的情况
        # {chat_id: {'task': asyncio.Task, 'last_message': dict, 'timer': float}}
        self.message_debounce_tasks = {}  # 存储每个chat_id的防抖任务
        self.message_debounce_delay = 1  # 防抖延迟时间（秒）：用户停止发送消息1秒后才回复
        self.message_debounce_lock = asyncio.Lock()  # 防抖任务管理的锁
        
        # 消息去重机制：防止同一条消息被处理多次
        self.processed_message_ids = {}  # 存储已处理的消息ID和时间戳 {message_id: timestamp}
        self.processed_message_ids_lock = asyncio.Lock()  # 消息ID去重的锁
        self.processed_message_ids_max_size = 10000  # 最大保存10000个消息ID，防止内存泄漏
        self.message_expire_time = 3600  # 消息过期时间（秒），默认1小时后可以重复回复

        # 初始化订单状态处理器
        self._init_order_status_handler()

        # 注册实例到类级别字典（用于API调用）
        self._register_instance()

    def _randomize_interval(self, base_seconds: float, jitter_percent: float = 0.3) -> float:
        """在基准值基础上添加随机偏移，模拟真人操作节奏"""
        jitter = base_seconds * jitter_percent
        return base_seconds + random.uniform(-jitter, jitter)

    def _random_delay(self, base_seconds: float = 1.0, jitter_percent: float = 0.5) -> float:
        """在基准延迟上添加随机偏移（偏上半分布，避免太快）"""
        jitter = base_seconds * jitter_percent
        return base_seconds + random.uniform(0, jitter)

    def _register_instance(self):
        """注册当前实例到类级别字典"""
        try:
            # 使用同步方式注册，避免在__init__中使用async
            XianyuLive._instances[self.cookie_id] = self
            logger.warning(f"【{self.cookie_id}】实例已注册到全局字典")
        except Exception as e:
            logger.error(f"【{self.cookie_id}】注册实例失败: {self._safe_str(e)}")

    def _unregister_instance(self):
        """从类级别字典中注销当前实例"""
        try:
            if self.cookie_id in XianyuLive._instances:
                del XianyuLive._instances[self.cookie_id]
                logger.warning(f"【{self.cookie_id}】实例已从全局字典中注销")
        except Exception as e:
            logger.error(f"【{self.cookie_id}】注销实例失败: {self._safe_str(e)}")

    @classmethod
    def get_instance(cls, cookie_id: str):
        """获取指定cookie_id的XianyuLive实例"""
        return cls._instances.get(cookie_id)

    @classmethod
    def get_all_instances(cls):
        """获取所有活跃的XianyuLive实例"""
        return dict(cls._instances)

    @classmethod
    def get_instance_count(cls):
        """获取当前活跃实例数量"""
        return len(cls._instances)
    
    def _create_tracked_task(self, coro):
        """创建并追踪后台任务，确保异常不会被静默忽略"""
        task = asyncio.create_task(coro)
        self.background_tasks.add(task)
        task.add_done_callback(self.background_tasks.discard)
        return task

    def is_auto_confirm_enabled(self) -> bool:
        """检查当前账号是否启用自动确认发货"""
        try:
            from db_manager import db_manager
            return db_manager.get_auto_confirm(self.cookie_id)
        except Exception as e:
            logger.error(f"【{self.cookie_id}】获取自动确认发货设置失败: {self._safe_str(e)}")
            return True  # 出错时默认启用



    async def _delayed_lock_release(self, lock_key: str, delay_minutes: int = 10):
        """
        延迟释放锁的异步任务

        Args:
            lock_key: 锁的键
            delay_minutes: 延迟时间（分钟），默认10分钟
        """
        try:
            delay_seconds = delay_minutes * 60
            logger.info(f"【{self.cookie_id}】订单锁 {lock_key} 将在 {delay_minutes} 分钟后释放")

            # 等待指定时间
            await asyncio.sleep(delay_seconds)

            # 检查锁是否仍然存在且需要释放
            if lock_key in self._lock_hold_info:
                lock_info = self._lock_hold_info[lock_key]
                if lock_info.get('locked', False):
                    # 释放锁
                    lock_info['locked'] = False
                    lock_info['release_time'] = time.time()
                    logger.info(f"【{self.cookie_id}】订单锁 {lock_key} 延迟释放完成")

                    # 清理锁信息（可选，也可以保留用于统计）
                    # del self._lock_hold_info[lock_key]

        except asyncio.CancelledError:
            logger.info(f"【{self.cookie_id}】订单锁 {lock_key} 延迟释放任务被取消")
            raise
        except Exception as e:
            logger.error(f"【{self.cookie_id}】订单锁 {lock_key} 延迟释放失败: {self._safe_str(e)}")

    def is_lock_held(self, lock_key: str) -> bool:
        """
        检查指定的锁是否仍在持有状态

        Args:
            lock_key: 锁的键

        Returns:
            bool: True表示锁仍在持有，False表示锁已释放或不存在
        """
        if lock_key not in self._lock_hold_info:
            return False

        lock_info = self._lock_hold_info[lock_key]
        return lock_info.get('locked', False)

    def cleanup_expired_locks(self, max_age_hours: int = 24):
        """
        清理过期的锁（包括自动发货锁和订单详情锁）

        Args:
            max_age_hours: 锁的最大保留时间（小时），默认24小时
        """
        try:
            current_time = time.time()
            max_age_seconds = max_age_hours * 3600

            # 清理自动发货锁
            expired_delivery_locks = []
            for order_id, last_used in self._lock_usage_times.items():
                if current_time - last_used > max_age_seconds:
                    expired_delivery_locks.append(order_id)

            # 清理过期的自动发货锁
            for order_id in expired_delivery_locks:
                if order_id in self._order_locks:
                    del self._order_locks[order_id]
                if order_id in self._lock_usage_times:
                    del self._lock_usage_times[order_id]
                # 清理锁持有信息
                if order_id in self._lock_hold_info:
                    lock_info = self._lock_hold_info[order_id]
                    # 取消延迟释放任务
                    if 'task' in lock_info and lock_info['task']:
                        lock_info['task'].cancel()
                    del self._lock_hold_info[order_id]

            # 清理订单详情锁
            expired_detail_locks = []
            for order_id, last_used in self._order_detail_lock_times.items():
                if current_time - last_used > max_age_seconds:
                    expired_detail_locks.append(order_id)

            # 清理过期的订单详情锁
            for order_id in expired_detail_locks:
                if order_id in self._order_detail_locks:
                    del self._order_detail_locks[order_id]
                if order_id in self._order_detail_lock_times:
                    del self._order_detail_lock_times[order_id]

            total_expired = len(expired_delivery_locks) + len(expired_detail_locks)
            if total_expired > 0:
                logger.info(f"【{self.cookie_id}】清理了 {total_expired} 个过期锁 (发货锁: {len(expired_delivery_locks)}, 详情锁: {len(expired_detail_locks)})")
                logger.warning(f"【{self.cookie_id}】当前锁数量 - 发货锁: {len(self._order_locks)}, 详情锁: {len(self._order_detail_locks)}")

        except Exception as e:
            logger.error(f"【{self.cookie_id}】清理过期锁时发生错误: {self._safe_str(e)}")

    

    def _is_buyer_blacklisted(self, buyer_id: str) -> bool:
        try:
            from db_manager import db_manager
            from config import config
            user_id = self.cookie_user_id if hasattr(self, 'cookie_user_id') else None
            if not user_id:
                cookie_info = db_manager.get_cookie_by_id(self.cookie_id)
                if cookie_info:
                    user_id = cookie_info.get('user_id')
            if user_id:
                return db_manager.is_buyer_blacklisted(user_id, buyer_id)
        except Exception as e:
            logger.error(f"黑名单检查失败: {self._safe_str(e)}")
        return False

    async def refresh_token(self, captcha_retry_count: int = 0):
        """刷新token

        Args:
            captcha_retry_count: 滑块验证重试次数，用于防止无限递归
        """
        # 初始化通知发送标志，避免重复发送通知
        notification_sent = False
        
        try:
            logger.info(f"【{self.cookie_id}】开始刷新token... (滑块验证重试次数: {captcha_retry_count})")
            # 标记本次刷新状态
            self.last_token_refresh_status = "started"
            # 重置“刷新流程内已重启”标记，避免多次重启
            self.restarted_in_browser_refresh = False

            # 检查滑块验证重试次数，防止无限递归
            if captcha_retry_count >= self.max_captcha_verification_count:
                logger.error(f"【{self.cookie_id}】滑块验证重试次数已达上限 ({self.max_captcha_verification_count})，停止重试")
                await self.send_token_refresh_notification(
                    f"滑块验证重试次数已达上限，请手动处理",
                    "captcha_max_retries_exceeded"
                )
                notification_sent = True
                return None

            # 【消息接收检查】检查是否在消息接收后的冷却时间内，与 cookie_refresh_loop 保持一致
            current_time = time.time()
            time_since_last_message = current_time - self.last_message_received_time
            if self.last_message_received_time > 0 and time_since_last_message < self.message_cookie_refresh_cooldown:
                remaining_time = self.message_cookie_refresh_cooldown - time_since_last_message
                remaining_minutes = int(remaining_time // 60)
                remaining_seconds = int(remaining_time % 60)
                logger.info(f"【{self.cookie_id}】收到消息后冷却中，放弃本次token刷新，还需等待 {remaining_minutes}分{remaining_seconds}秒")
                # 标记为因冷却而跳过（正常情况）
                self.last_token_refresh_status = "skipped_cooldown"
                return None

            # 【重要】在刷新token前，先从数据库重新加载最新的cookie
            # 这样即使用户已经手动更新了cookie，代码也会使用最新的cookie
            logger.info(f"【{self.cookie_id}】开始执行Cookie刷新任务...")
            # await self._execute_cookie_refresh(time.time())
            try:
                from db_manager import db_manager
                account_info = db_manager.get_cookie_details(self.cookie_id)
                if account_info and account_info.get('cookie_value'):
                    new_cookies_str = account_info.get('cookie_value')
                    if new_cookies_str != self.cookies_str:
                        logger.info(f"【{self.cookie_id}】检测到数据库中的cookie已更新，重新加载cookie")
                        self.cookies_str = new_cookies_str
                        # 更新cookies字典
                        self.cookies = trans_cookies(self.cookies_str)
                        logger.warning(f"【{self.cookie_id}】Cookie已从数据库重新加载")
            except Exception as reload_e:
                logger.warning(f"【{self.cookie_id}】从数据库重新加载cookie失败，继续使用当前cookie: {self._safe_str(reload_e)}")

            # 生成更精确的时间戳
            timestamp = str(int(time.time() * 1000))

            params = {
                'jsv': '2.7.2',
                'appKey': '34839810',
                't': timestamp,
                'sign': '',
                'v': '1.0',
                'type': 'originaljson',
                'accountSite': 'xianyu',
                'dataType': 'json',
                'timeout': '20000',
                'api': 'mtop.taobao.idlemessage.pc.login.token',
                'sessionOption': 'AutoLoginOnly',
                'dangerouslySetWindvaneParams': '%5Bobject%20Object%5D',
                'smToken': 'token',
                'queryToken': 'sm',
                'sm': 'sm',
                'spm_cnt': 'a21ybx.im.0.0',
                'spm_pre': 'a21ybx.home.sidebar.1.4c053da6vYwnmf',
                'log_id': '4c053da6vYwnmf'
            }
            data_val = '{"appKey":"444e9908a51d1cb236a27862abc769c9","deviceId":"' + self.device_id + '"}'
            data = {
                'data': data_val,
            }

            # 获取token
            token = None
            token = trans_cookies(self.cookies_str).get('_m_h5_tk', '').split('_')[0] if trans_cookies(self.cookies_str).get('_m_h5_tk') else ''

            sign = generate_sign(params['t'], token, data_val)
            params['sign'] = sign

            # 发送请求 - 使用与浏览器完全一致的请求头
            headers = {
                'accept': 'application/json',
                'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'cache-control': 'no-cache',
                'content-type': 'application/x-www-form-urlencoded',
                'pragma': 'no-cache',
                'priority': 'u=1, i',
                'sec-ch-ua': '"Not;A=Brand";v="99", "Google Chrome";v="139", "Chromium";v="139"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"',
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'same-site',
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
                'referer': 'https://www.goofish.com/',
                'origin': 'https://www.goofish.com',
                'cookie': self.cookies_str
            }

            # 打印所有请求参数（用于调试）
            api_url = API_ENDPOINTS.get('token')
            logger.info(f"【{self.cookie_id}】正在刷新token... (API: {api_url}, cookie长度: {len(self.cookies_str)})")

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    api_url,
                    params=params,
                    data=data,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    res_json = await response.json()
                    logger.debug(f"【{self.cookie_id}】Token刷新响应: 状态码={response.status}, 内容={json.dumps(res_json, ensure_ascii=False)[:500]}")

                    # 检查并更新Cookie
                    if 'set-cookie' in response.headers:
                        new_cookies = {}
                        for cookie in response.headers.getall('set-cookie', []):
                            if '=' in cookie:
                                name, value = cookie.split(';')[0].split('=', 1)
                                new_cookies[name.strip()] = value.strip()

                        # 更新cookies
                        if new_cookies:
                            self.cookies.update(new_cookies)
                            # 生成新的cookie字符串
                            self.cookies_str = '; '.join([f"{k}={v}" for k, v in self.cookies.items()])
                            # 更新数据库中的Cookie
                            await self.update_config_cookies()
                            logger.warning("已更新Cookie到数据库")

                    if isinstance(res_json, dict):
                        ret_value = res_json.get('ret', [])
                        # 检查ret是否包含成功信息
                        if any('SUCCESS::调用成功' in ret for ret in ret_value):
                            if 'data' in res_json and 'accessToken' in res_json['data']:
                                new_token = res_json['data']['accessToken']
                                self.current_token = new_token
                                self.last_token_refresh_time = time.time()

                                # 【消息接收时间重置】Token刷新成功后重置消息接收标志，与 cookie_refresh_loop 保持一致
                                self.last_message_received_time = 0
                                logger.warning(f"【{self.cookie_id}】Token刷新成功，已重置消息接收时间标识")

                                logger.info(f"【{self.cookie_id}】Token刷新成功")
                                # 标记为成功
                                self.last_token_refresh_status = "success"
                                return new_token

                    # 检查是否需要滑块验证
                    if self._need_captcha_verification(res_json):
                        logger.warning(f"【{self.cookie_id}】检测到需要滑块验证，开始处理...")

                        # 记录滑块验证检测到日志文件
                        verification_url = res_json.get('data', {}).get('url', 'Token刷新时检测')
                        log_captcha_event(self.cookie_id, "检测到滑块验证", None, f"触发场景: Token刷新, URL: {verification_url}")

                        # 添加风控日志记录
                        log_id = None
                        try:
                            from db_manager import db_manager
                            success = db_manager.add_risk_control_log(
                                cookie_id=self.cookie_id,
                                event_type='slider_captcha',
                                event_description=f"检测到需要滑块验证，触发场景: Token刷新, URL: {verification_url}",
                                processing_status='processing'
                            )
                            if success:
                                # 获取刚插入的记录ID（简单方式，实际应该返回ID）
                                logs = db_manager.get_risk_control_logs(cookie_id=self.cookie_id, limit=1)
                                if logs:
                                    log_id = logs[0].get('id')
                                logger.info(f"【{self.cookie_id}】风控日志记录成功，ID: {log_id}")
                        except Exception as log_e:
                            logger.error(f"【{self.cookie_id}】记录风控日志失败: {log_e}")

                        try:
                            # 尝试通过滑块验证获取新的cookies
                            captcha_start_time = time.time()
                            new_cookies_str = await self._handle_captcha_verification(res_json)
                            captcha_duration = time.time() - captcha_start_time

                            if new_cookies_str:
                                logger.info(f"【{self.cookie_id}】滑块验证成功，准备重启实例...")

                                # 更新风控日志为成功状态
                                if 'log_id' in locals() and log_id:
                                    try:
                                        from db_manager import db_manager
                                        db_manager.update_risk_control_log(
                                            log_id=log_id,
                                            processing_result=f"滑块验证成功，耗时: {captcha_duration:.2f}秒, cookies长度: {len(new_cookies_str)}",
                                            processing_status='success'
                                        )
                                    except Exception as update_e:
                                        logger.error(f"【{self.cookie_id}】更新风控日志失败: {update_e}")

                                # 重启实例（cookies已在_handle_captcha_verification中更新到数据库）
                                # await self._restart_instance()
                                
                                # 重新尝试刷新token（递归调用，但有深度限制）
                                return await self.refresh_token(captcha_retry_count + 1)
                            else:
                                logger.error(f"【{self.cookie_id}】滑块验证失败")

                                # 更新风控日志为失败状态
                                if 'log_id' in locals() and log_id:
                                    try:
                                        from db_manager import db_manager
                                        db_manager.update_risk_control_log(
                                            log_id=log_id,
                                            processing_result=f"滑块验证失败，耗时: {captcha_duration:.2f}秒, 原因: 未获取到新cookies",
                                            processing_status='failed'
                                        )
                                    except Exception as update_e:
                                        logger.error(f"【{self.cookie_id}】更新风控日志失败: {update_e}")
                                
                                # 标记已发送通知（通知已在_handle_captcha_verification中发送）
                                notification_sent = True
                        except Exception as captcha_e:
                            logger.error(f"【{self.cookie_id}】滑块验证处理异常: {self._safe_str(captcha_e)}")

                            # 更新风控日志为异常状态
                            captcha_duration = time.time() - captcha_start_time if 'captcha_start_time' in locals() else 0
                            if 'log_id' in locals() and log_id:
                                try:
                                    from db_manager import db_manager
                                    db_manager.update_risk_control_log(
                                        log_id=log_id,
                                        processing_result=f"滑块验证处理异常，耗时: {captcha_duration:.2f}秒",
                                        processing_status='failed',
                                        error_message=str(captcha_e)
                                    )
                                except Exception as update_e:
                                    logger.error(f"【{self.cookie_id}】更新风控日志失败: {update_e}")
                            
                            # 标记已发送通知（通知已在_handle_captcha_verification中发送）
                            notification_sent = True

                    # 检查是否包含"令牌过期"或"Session过期"
                    if isinstance(res_json, dict):
                        res_json_str = json.dumps(res_json, ensure_ascii=False, separators=(',', ':'))
                        if '令牌过期' in res_json_str or 'Session过期' in res_json_str:
                            # 调用统一的密码登录刷新方法
                            refresh_success = await self._try_password_login_refresh("令牌/Session过期")
                            
                            if not refresh_success:
                                # 标记已发送通知，避免重复通知
                                notification_sent = True
                                # 返回None，让调用者知道刷新失败
                                return None
                            else:
                                # 刷新成功后，重新尝试获取token
                                return await self.refresh_token(captcha_retry_count)
                                
                                # 刷新失败时继续执行原有的失败处理逻辑

                    logger.error(f"【{self.cookie_id}】Token刷新失败: {res_json}")

                    # 清空当前token，确保下次重试时重新获取
                    self.current_token = None

                    # 只有在没有发送过通知的情况下才发送Token刷新失败通知
                    # 并且WebSocket未连接时才发送（已连接说明只是暂时失败）
                    if not notification_sent:
                        # 检查WebSocket连接状态
                        is_ws_connected = (
                            self.connection_state == ConnectionState.CONNECTED and 
                            self.ws and 
                            not self.ws.closed
                        )
                        
                        if is_ws_connected:
                            logger.info(f"【{self.cookie_id}】WebSocket连接正常，Token刷新失败可能是暂时的，跳过失败通知")
                        else:
                            logger.warning(f"【{self.cookie_id}】WebSocket未连接，发送Token刷新失败通知")
                            await self.send_token_refresh_notification(f"Token刷新失败: {res_json}", "token_refresh_failed")
                    else:
                        logger.info(f"【{self.cookie_id}】已发送滑块验证相关通知，跳过Token刷新失败通知")
                    return None

        except Exception as e:
            logger.error(f"Token刷新异常: {self._safe_str(e)}")

            # 清空当前token，确保下次重试时重新获取
            self.current_token = None

            # 只有在没有发送过通知的情况下才发送Token刷新异常通知
            # 并且WebSocket未连接时才发送（已连接说明只是暂时失败）
            if not notification_sent:
                # 检查WebSocket连接状态
                is_ws_connected = (
                    self.connection_state == ConnectionState.CONNECTED and 
                    self.ws and 
                    not self.ws.closed
                )
                
                if is_ws_connected:
                    logger.info(f"【{self.cookie_id}】WebSocket连接正常，Token刷新异常可能是暂时的，跳过失败通知")
                else:
                    logger.warning(f"【{self.cookie_id}】WebSocket未连接，发送Token刷新异常通知")
                    await self.send_token_refresh_notification(f"Token刷新异常: {str(e)}", "token_refresh_exception")
            else:
                logger.info(f"【{self.cookie_id}】已发送滑块验证相关通知，跳过Token刷新异常通知")
            return None

    def _need_captcha_verification(self, res_json: dict) -> bool:
        """检查响应是否需要滑块验证"""
        try:
            if not isinstance(res_json, dict):
                return False

            # 记录res_json内容到日志文件
            import json
            res_json_str = json.dumps(res_json, ensure_ascii=False, separators=(',', ':'))
            log_captcha_event(self.cookie_id, "检查滑块验证响应", None, f"res_json内容: {res_json_str}")

            # 检查返回的错误信息
            ret_value = res_json.get('ret', [])
            if not ret_value:
                return False

            # 检查是否包含需要验证的关键词
            captcha_keywords = [
                'FAIL_SYS_USER_VALIDATE',  # 用户验证失败
                'RGV587_ERROR',            # 风控错误
                '哎哟喂,被挤爆啦',          # 被挤爆了
                '哎哟喂，被挤爆啦',         # 被挤爆了（中文逗号）
                '挤爆了',                  # 挤爆了
                '请稍后重试',              # 请稍后重试
                'punish?x5secdata',        # 惩罚页面
                'captcha',                 # 验证码
            ]

            error_msg = str(ret_value[0]) if ret_value else ''

            # 检查错误信息是否包含需要验证的关键词
            for keyword in captcha_keywords:
                if keyword in error_msg:
                    logger.info(f"【{self.cookie_id}】检测到需要滑块验证的关键词: {keyword}")
                    return True

            # 检查data字段中是否包含验证URL
            data = res_json.get('data', {})
            if isinstance(data, dict) and 'url' in data:
                url = data.get('url', '')
                if 'punish' in url or 'captcha' in url or 'validate' in url:
                    logger.info(f"【{self.cookie_id}】检测到验证URL: {url}")
                    return True

            return False

        except Exception as e:
            logger.error(f"【{self.cookie_id}】检查是否需要滑块验证时出错: {self._safe_str(e)}")
            return False

    async def _handle_captcha_verification(self, res_json: dict) -> str:
        """处理滑块验证，返回新的cookies字符串"""
        try:
            logger.info(f"【{self.cookie_id}】开始处理滑块验证...")

            # 获取验证URL
            verification_url = None

            # 从data字段获取URL
            data = res_json.get('data', {})
            if isinstance(data, dict) and 'url' in data:
                verification_url = data.get('url')

            # 如果没有找到URL，使用默认的验证页面
            if not verification_url:
                logger.info(f"【{self.cookie_id}】未找到验证URL，认为不需要滑块验证，返回正常")
                return None

            logger.info(f"【{self.cookie_id}】验证URL: {verification_url}")

            # 使用滑块验证器（独立实例，解决并发冲突）
            try:
                # 使用集成的滑块验证方法（无需猴子补丁）
                from utils.xianyu_slider_stealth import XianyuSliderStealth
                logger.info(f"【{self.cookie_id}】XianyuSliderStealth导入成功，使用滑块验证")

                # 创建独立的滑块验证实例（每个用户独立实例，避免并发冲突）
                slider_stealth = XianyuSliderStealth(
                    # user_id=f"{self.cookie_id}_{int(time.time() * 1000)}",  # 使用唯一ID避免冲突
                    user_id=f"{self.cookie_id}",  # 使用唯一ID避免冲突
                    enable_learning=True,  # 启用学习功能
                    headless=True  # 使用无头模式
                )

                # 在线程池中执行滑块验证
                import asyncio
                import concurrent.futures

                loop = asyncio.get_event_loop()
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    # 执行滑块验证
                    success, cookies = await loop.run_in_executor(
                        executor,
                        slider_stealth.run,
                        verification_url
                    )

                if success and cookies:
                    logger.info(f"【{self.cookie_id}】滑块验证成功，获取到新的cookies")

                    # 只提取x5sec相关的cookie值进行更新
                    updated_cookies = self.cookies.copy()  # 复制现有cookies
                    new_cookie_count = 0
                    updated_cookie_count = 0
                    x5sec_cookies = {}

                    # 筛选出x5相关的cookies（包括x5sec, x5step等）
                    for cookie_name, cookie_value in cookies.items():
                        cookie_name_lower = cookie_name.lower()
                        if cookie_name_lower.startswith('x5') or 'x5sec' in cookie_name_lower:
                            x5sec_cookies[cookie_name] = cookie_value

                    logger.info(f"【{self.cookie_id}】找到{len(x5sec_cookies)}个x5相关cookies: {list(x5sec_cookies.keys())}")

                    # 只更新x5相关的cookies
                    for cookie_name, cookie_value in x5sec_cookies.items():
                        if cookie_name in updated_cookies:
                            if updated_cookies[cookie_name] != cookie_value:
                                logger.warning(f"【{self.cookie_id}】更新x5 cookie: {cookie_name}")
                                updated_cookies[cookie_name] = cookie_value
                                updated_cookie_count += 1
                            else:
                                logger.warning(f"【{self.cookie_id}】x5 cookie值未变: {cookie_name}")
                        else:
                            logger.warning(f"【{self.cookie_id}】新增x5 cookie: {cookie_name}")
                            updated_cookies[cookie_name] = cookie_value
                            new_cookie_count += 1

                    # 将合并后的cookies字典转换为字符串格式
                    cookies_str = "; ".join([f"{k}={v}" for k, v in updated_cookies.items()])

                    logger.info(f"【{self.cookie_id}】x5 Cookie更新完成: 新增{new_cookie_count}个, 更新{updated_cookie_count}个, 总计{len(updated_cookies)}个")

                    # 自动更新数据库中的cookie
                    try:
                        # 备份原有cookies
                        old_cookies_str = self.cookies_str
                        old_cookies_dict = self.cookies.copy()

                        # 更新当前实例的cookies（使用合并后的cookies）
                        self.cookies_str = cookies_str
                        self.cookies = updated_cookies

                        # 更新数据库中的cookies
                        await self.update_config_cookies()
                        logger.info(f"【{self.cookie_id}】滑块验证成功后，数据库cookies已自动更新")

                            
                        # 记录成功更新到日志文件，包含x5相关的cookie信息
                        x5sec_cookies_str = "; ".join([f"{k}={v}" for k, v in x5sec_cookies.items()]) if x5sec_cookies else "无"
                        log_captcha_event(self.cookie_id, "滑块验证成功并自动更新数据库", True,
                            f"cookies长度: {len(cookies_str)}, 新增{new_cookie_count}个x5, 更新{updated_cookie_count}个x5, 总计{len(updated_cookies)}个cookie项, x5 cookies: {x5sec_cookies_str}")

                        # 发送成功通知
                        await self.send_token_refresh_notification(
                            f"滑块验证成功，cookies已自动更新到数据库",
                            "captcha_success_auto_update"
                        )

                    except Exception as update_e:
                        logger.error(f"【{self.cookie_id}】自动更新数据库cookies失败: {self._safe_str(update_e)}")

                        # 回滚cookies
                        self.cookies_str = old_cookies_str
                        self.cookies = old_cookies_dict

                        # 记录更新失败到日志文件，包含获取到的x5 cookies
                        x5sec_cookies_str = "; ".join([f"{k}={v}" for k, v in x5sec_cookies.items()]) if x5sec_cookies else "无"
                        log_captcha_event(self.cookie_id, "滑块验证成功但数据库更新失败", False,
                            f"更新异常: {self._safe_str(update_e)[:100]}, 获取到的x5 cookies: {x5sec_cookies_str}")

                        # 发送更新失败通知
                        await self.send_token_refresh_notification(
                            f"滑块验证成功但数据库更新失败: {self._safe_str(update_e)}",
                            "captcha_success_db_update_failed"
                        )

                    return cookies_str
                else:
                    logger.error(f"【{self.cookie_id}】滑块验证失败")

                    # 记录滑块验证失败到日志文件
                    log_captcha_event(self.cookie_id, "滑块验证失败", False,
                        f"XianyuSliderStealth执行失败, 环境: {'Docker' if os.getenv('DOCKER_ENV') else '本地'}")

                    # 发送通知（检查WebSocket连接状态）
                    # 只有在WebSocket未连接时才发送通知，已连接说明可能是暂时性问题
                    is_ws_connected = (
                        self.connection_state == ConnectionState.CONNECTED and 
                        self.ws and 
                        not self.ws.closed
                    )
                    
                    if is_ws_connected:
                        logger.info(f"【{self.cookie_id}】WebSocket连接正常，滑块验证失败可能是暂时的，跳过通知")
                    else:
                        logger.warning(f"【{self.cookie_id}】WebSocket未连接，发送滑块验证失败通知")
                        await self.send_token_refresh_notification(
                            f"滑块验证失败，需要手动处理。验证URL: {verification_url}",
                            "captcha_verification_failed"
                        )
                    return None

            except ImportError as import_e:
                logger.error(f"【{self.cookie_id}】XianyuSliderStealth导入失败: {import_e}")
                logger.error(f"【{self.cookie_id}】请安装Playwright库: pip install playwright")

                # 记录导入失败到日志文件
                log_captcha_event(self.cookie_id, "XianyuSliderStealth导入失败", False,
                    f"Playwright未安装, 错误: {import_e}")

                # 发送通知
                await self.send_token_refresh_notification(
                    f"滑块验证功能不可用，请安装Playwright。验证URL: {verification_url}",
                    "captcha_dependency_missing"
                )
                return None

            except Exception as stealth_e:
                logger.error(f"【{self.cookie_id}】滑块验证异常: {self._safe_str(stealth_e)}")

                # 记录异常到日志文件
                log_captcha_event(self.cookie_id, "滑块验证异常", False,
                    f"执行异常, 错误: {self._safe_str(stealth_e)[:100]}")

                # 发送通知（检查WebSocket连接状态）
                # 只有在WebSocket未连接时才发送通知，已连接说明可能是暂时性问题
                is_ws_connected = (
                    self.connection_state == ConnectionState.CONNECTED and 
                    self.ws and 
                    not self.ws.closed
                )
                
                if is_ws_connected:
                    logger.info(f"【{self.cookie_id}】WebSocket连接正常，滑块验证执行异常可能是暂时的，跳过通知")
                else:
                    logger.warning(f"【{self.cookie_id}】WebSocket未连接，发送滑块验证执行异常通知")
                    await self.send_token_refresh_notification(
                        f"滑块验证执行异常，需要手动处理。验证URL: {verification_url}",
                        "captcha_execution_error"
                    )
                return None



        except Exception as e:
            logger.error(f"【{self.cookie_id}】处理滑块验证时出错: {self._safe_str(e)}")
            return None

    async def _restart_instance(self):
        """重启XianyuLive实例
        
        ⚠️ 注意：此方法会触发当前任务被取消！
        调用此方法后，当前任务会立即被 CookieManager 取消，
        因此不要在此方法后执行任何重要操作。
        """
        try:
            logger.info(f"【{self.cookie_id}】准备重启实例...")

            # 导入CookieManager
            from cookie_manager import manager as cookie_manager

            if cookie_manager:
                # 通过CookieManager重启实例
                logger.info(f"【{self.cookie_id}】通过CookieManager重启实例...")
                
                # ⚠️ 重要：不要等待重启完成！
                # cookie_manager.update_cookie() 会立即取消当前任务
                # 如果我们等待它完成，会导致 CancelledError 中断等待
                # 正确的做法是：触发重启后立即返回，让任务自然退出
                
                import asyncio as _asyncio_mod

                async def trigger_restart():
                    await _asyncio_mod.sleep(0.5)
                    try:
                        cookie_manager.update_cookie(self.cookie_id, self.cookies_str, save_to_db=False)
                        logger.info(f"【{self.cookie_id}】实例重启请求已触发")
                    except Exception as e:
                        logger.error(f"【{self.cookie_id}】触发实例重启失败: {e}")
                        import traceback
                        logger.error(f"【{self.cookie_id}】重启失败详情:\n{traceback.format_exc()}")

                _task = asyncio.create_task(trigger_restart())
                
                logger.info(f"【{self.cookie_id}】实例重启已触发，当前任务即将退出...")
                logger.warning(f"【{self.cookie_id}】注意：重启请求已发送，CookieManager将在0.5秒后取消当前任务并启动新实例")
                    
            else:
                logger.warning(f"【{self.cookie_id}】CookieManager不可用，无法重启实例")

        except Exception as e:
            logger.error(f"【{self.cookie_id}】重启实例失败: {self._safe_str(e)}")
            import traceback
            logger.error(f"【{self.cookie_id}】重启失败堆栈:\n{traceback.format_exc()}")
            # 发送重启失败通知
            try:
                await self.send_token_refresh_notification(f"实例重启失败: {str(e)}", "instance_restart_failed")
            except Exception as notify_e:
                logger.error(f"【{self.cookie_id}】发送重启失败通知时出错: {self._safe_str(notify_e)}")

    @classmethod
    def _is_cdn_url(self, url: str) -> bool:
        """检查URL是否是闲鱼CDN链接"""
        if not url:
            return False

        # 闲鱼CDN域名列表
        cdn_domains = [
            'gw.alicdn.com',
            'img.alicdn.com',
            'cloud.goofish.com',
            'goofish.com',
            'taobaocdn.com',
            'tbcdn.cn',
            'aliimg.com'
        ]

        # 检查是否包含CDN域名
        url_lower = url.lower()
        for domain in cdn_domains:
            if domain in url_lower:
                return True

        # 检查是否是HTTPS链接且包含图片特征
        if url_lower.startswith('https://') and any(ext in url_lower for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
            return True

        return False

    async def _get_image_size_from_url(self, image_url: str) -> tuple:
        """从URL获取图片尺寸
        
        Args:
            image_url: 图片URL
            
        Returns:
            (width, height) 元组，失败返回 (None, None)
        """
        import aiohttp
        from io import BytesIO
        
        try:
            logger.info(f"【{self.cookie_id}】开始从URL获取图片尺寸: {image_url[:80]}...")
            
            # 不接受AVIF格式（PIL默认不支持），让CDN返回WEBP/JPEG等格式
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'image/jpeg,image/png,image/gif,image/webp,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Referer': 'https://www.goofish.com/',
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        from PIL import Image
                        with Image.open(BytesIO(image_data)) as img:
                            width, height = img.size
                            logger.info(f"【{self.cookie_id}】解析图片尺寸成功: {width}x{height}")
                            return (width, height)
                    else:
                        logger.warning(f"【{self.cookie_id}】下载图片失败，HTTP状态码: {response.status}")
        except Exception as e:
            logger.warning(f"【{self.cookie_id}】从URL获取图片尺寸失败: {e}")
        
        return (None, None)

    async def _update_card_image_url(self, card_id: int, new_image_url: str):
        """更新卡券的图片URL"""
        try:
            from db_manager import db_manager
            success = db_manager.update_card_image_url(card_id, new_image_url)
            if success:
                logger.info(f"卡券图片URL已更新: 卡券ID={card_id} -> {new_image_url}")
            else:
                logger.warning(f"卡券图片URL更新失败: 卡券ID={card_id}")
        except Exception as e:
            logger.error(f"更新卡券图片URL失败: {e}")

    def _parse_price(self, price_str: str) -> float:
        """解析价格字符串为数字"""
        try:
            if not price_str:
                return 0.0
            # 移除非数字字符，保留小数点
            price_clean = re.sub(r'[^\d.]', '', str(price_str))
            return float(price_clean) if price_clean else 0.0
        except:
            return 0.0

    async def send_notification(self, send_user_name: str, send_user_id: str, send_message: str, item_id: str = None, chat_id: str = None):
        """发送消息通知"""
        try:
            from db_manager import db_manager
            import aiohttp
            import hashlib

            # 过滤系统默认消息，不发送通知
            system_messages = [
                '发来一条消息',
                '发来一条新消息'
            ]

            if send_message in system_messages:
                logger.warning(f"📱 系统消息不发送通知: {send_message}")
                return

            # 生成通知的唯一标识（基于消息内容、chat_id、send_user_id）
            # 用于防重复发送
            notification_key = f"{chat_id or 'unknown'}_{send_user_id}_{send_message}"
            notification_hash = hashlib.md5(notification_key.encode('utf-8')).hexdigest()
            
            # 使用异步锁保护防重复检查，确保并发安全
            async with self.notification_lock:
                # 检查是否在冷却时间内已发送过相同的通知
                current_time = time.time()
                if notification_hash in self.last_notification_time:
                    time_since_last = current_time - self.last_notification_time[notification_hash]
                    if time_since_last < self.notification_cooldown:
                        remaining_seconds = int(self.notification_cooldown - time_since_last)
                        logger.warning(f"📱 通知在冷却期内（剩余 {remaining_seconds} 秒），跳过重复发送 - 账号: {self.cookie_id}, 买家: {send_user_name}, 消息: {send_message[:30]}...")
                        return
                
                # 更新通知发送时间
                self.last_notification_time[notification_hash] = current_time
                
                # 清理过期的通知记录（超过1小时的记录）
                expired_keys = [
                    key for key, timestamp in self.last_notification_time.items()
                    if current_time - timestamp > 3600  # 1小时
                ]
                for key in expired_keys:
                    del self.last_notification_time[key]

            logger.info(f"📱 开始发送消息通知 - 账号: {self.cookie_id}, 买家: {send_user_name}")

            # 获取当前账号的通知配置
            notifications = db_manager.get_account_notifications(self.cookie_id)

            if not notifications:
                logger.warning(f"📱 账号 {self.cookie_id} 未配置消息通知，跳过通知发送")
                return

            logger.info(f"📱 找到 {len(notifications)} 个通知渠道配置")

            # 构建通知消息
            notification_msg = f"🚨 接收消息通知\n\n" \
                             f"账号: {self.cookie_id}\n" \
                             f"买家: {send_user_name} (ID: {send_user_id})\n" \
                             f"商品ID: {item_id or '未知'}\n" \
                             f"聊天ID: {chat_id or '未知'}\n" \
                             f"消息内容: {send_message}\n" \
                             f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"

            # 发送通知到各个渠道
            for i, notification in enumerate(notifications, 1):
                logger.info(f"📱 处理第 {i} 个通知渠道: {notification.get('channel_name', 'Unknown')}")

                if not notification.get('enabled', True):
                    logger.warning(f"📱 通知渠道 {notification.get('channel_name')} 已禁用，跳过")
                    continue

                channel_type = notification.get('channel_type')
                channel_config = notification.get('channel_config')

                logger.info(f"📱 渠道类型: {channel_type}, 配置: {channel_config}")

                try:
                    # 解析配置数据
                    config_data = self._parse_notification_config(channel_config)
                    logger.info(f"📱 解析后的配置数据: {config_data}")

                    match channel_type:
                        case 'ding_talk' | 'dingtalk':
                            logger.info(f"📱 开始发送钉钉通知...")
                            await self._send_dingtalk_notification(config_data, notification_msg)
                        case 'feishu' | 'lark':
                            logger.info(f"📱 开始发送飞书通知...")
                            await self._send_feishu_notification(config_data, notification_msg)
                        case 'bark':
                            logger.info(f"📱 开始发送Bark通知...")
                            await self._send_bark_notification(config_data, notification_msg)
                        case 'email':
                            logger.info(f"📱 开始发送邮件通知...")
                            await self._send_email_notification(config_data, notification_msg)
                        case 'webhook':
                            logger.info(f"📱 开始发送Webhook通知...")
                            await self._send_webhook_notification(config_data, notification_msg)
                        case 'wechat':
                            logger.info(f"📱 开始发送微信通知...")
                            await self._send_wechat_notification(config_data, notification_msg)
                        case 'telegram':
                            logger.info(f"📱 开始发送Telegram通知...")
                            await self._send_telegram_notification(config_data, notification_msg)
                        case _:
                            logger.warning(f"📱 不支持的通知渠道类型: {channel_type}")

                except Exception as notify_error:
                    logger.error(f"📱 发送通知失败 ({notification.get('channel_name', 'Unknown')}): {self._safe_str(notify_error)}")
                    import traceback
                    logger.error(f"📱 详细错误信息: {traceback.format_exc()}")

        except Exception as e:
            logger.error(f"📱 处理消息通知失败: {self._safe_str(e)}")
            import traceback
            logger.error(f"📱 详细错误信息: {traceback.format_exc()}")

    async def send_image_to_manual_notification(self, send_user_name: str, send_user_id: str, ocr_text: str, image_url: str, item_id: str = None, chat_id: str = None):
        """买家发图片时发送转人工通知"""
        try:
            from db_manager import db_manager
            import hashlib

            notification_key = hashlib.md5(f"image_{chat_id}_{send_user_id}_{image_url[-50:]}".encode()).hexdigest()

            async with self.notification_lock:
                current_time = time.time()
                if notification_key in self.last_notification_time:
                    if current_time - self.last_notification_time[notification_key] < self.notification_cooldown:
                        logger.warning(f"📱 图片转人工通知在冷却期内，跳过")
                        return
                self.last_notification_time[notification_key] = current_time

                expired_keys = [k for k, t in self.last_notification_time.items() if current_time - t > 3600]
                for k in expired_keys:
                    del self.last_notification_time[k]

            notifications = db_manager.get_account_notifications(self.cookie_id)
            if not notifications:
                logger.warning(f"📱 账号 {self.cookie_id} 未配置通知渠道，跳过图片转人工通知")
                return

            user_url = f"https://www.goofish.com/personal?userId={send_user_id}"
            notification_msg = (
                f"🖼 图片消息 - 请转人工处理\n\n"
                f"账号ID: {self.cookie_id}\n"
                f"买家: {send_user_name}\n"
                f"买家ID: {send_user_id}\n"
                f"买家链接: {user_url}\n"
                f"商品ID: {item_id or '未知'}\n"
                f"OCR识别: {ocr_text or '未识别出文字'}\n"
                f"图片链接: {image_url[:200]}\n"
                f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"机器人自动回复已暂停，处理完毕后发送:\n"
                f"  「恢复全部」- 恢复所有对话\n"
                f"  「状态」- 查看当前暂停状态"
            )

            logger.info(f"📱 发送图片转人工通知 - 账号: {self.cookie_id}, 买家: {send_user_name}")

            for notification in notifications:
                if not notification.get('enabled', True):
                    continue
                try:
                    config_data = self._parse_notification_config(notification.get('channel_config'))
                    channel_type = notification.get('channel_type')

                    if channel_type in ('feishu', 'lark'):
                        await self._send_feishu_notification(config_data, notification_msg)
                        logger.info(f"✅ 图片转人工通知已发送到飞书")
                    elif channel_type in ('ding_talk', 'dingtalk'):
                        await self._send_dingtalk_notification(config_data, notification_msg)
                    elif channel_type == 'email':
                        await self._send_email_notification(config_data, notification_msg)
                    elif channel_type == 'webhook':
                        await self._send_webhook_notification(config_data, notification_msg)
                    elif channel_type == 'wechat':
                        await self._send_wechat_notification(config_data, notification_msg)
                    elif channel_type == 'telegram':
                        await self._send_telegram_notification(config_data, notification_msg)
                    elif channel_type == 'bark':
                        await self._send_bark_notification(config_data, notification_msg)

                except Exception as e:
                    logger.error(f"📱 图片转人工通知发送失败: {self._safe_str(e)}")

        except Exception as e:
            logger.error(f"📱 图片转人工通知异常: {self._safe_str(e)}")

    def _parse_notification_config(self, config: str) -> dict:
        """解析通知配置数据"""
        try:
            import json
            # 尝试解析JSON格式的配置
            return json.loads(config)
        except (json.JSONDecodeError, TypeError):
            # 兼容旧格式（直接字符串）
            return {"config": config}

    async def _send_dingtalk_notification(self, config_data: dict, message: str):
        """发送钉钉通知"""
        try:
            import aiohttp
            import json
            import hmac
            import hashlib
            import base64
            import time

            # 解析配置
            webhook_url = config_data.get('webhook_url') or config_data.get('config', '')
            secret = config_data.get('secret', '')

            webhook_url = webhook_url.strip() if webhook_url else ''
            if not webhook_url:
                logger.warning("钉钉通知配置为空")
                return

            # 如果有加签密钥，生成签名
            if secret:
                timestamp = str(round(time.time() * 1000))
                secret_enc = secret.encode('utf-8')
                string_to_sign = f'{timestamp}\n{secret}'
                string_to_sign_enc = string_to_sign.encode('utf-8')
                hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
                sign = base64.b64encode(hmac_code).decode('utf-8')
                webhook_url += f'&timestamp={timestamp}&sign={sign}'

            data = {
                "msgtype": "markdown",
                "markdown": {
                    "title": "闲鱼自动回复通知",
                    "text": message
                }
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=data, timeout=10) as response:
                    if response.status == 200:
                        logger.info(f"钉钉通知发送成功")
                    else:
                        logger.warning(f"钉钉通知发送失败: {response.status}")

        except Exception as e:
            logger.error(f"发送钉钉通知异常: {self._safe_str(e)}")

    async def _send_feishu_notification(self, config_data: dict, message: str):
        """发送飞书通知"""
        try:
            import aiohttp
            import json
            import hmac
            import hashlib
            import base64

            logger.info(f"📱 飞书通知 - 开始处理配置数据: {config_data}")

            # 解析配置
            webhook_url = config_data.get('webhook_url', '')
            secret = config_data.get('secret', '')

            logger.info(f"📱 飞书通知 - Webhook URL: {webhook_url[:50]}...")
            logger.info(f"📱 飞书通知 - 是否有签名密钥: {'是' if secret else '否'}")

            if not webhook_url:
                logger.warning("📱 飞书通知 - Webhook URL配置为空，无法发送通知")
                return

            # 如果有加签密钥，生成签名
            timestamp = str(int(time.time()))
            sign = ""

            if secret:
                string_to_sign = f'{timestamp}\n{secret}'
                hmac_code = hmac.new(
                    string_to_sign.encode('utf-8'),
                    ''.encode('utf-8'),
                    digestmod=hashlib.sha256
                ).digest()
                sign = base64.b64encode(hmac_code).decode('utf-8')
                logger.info(f"📱 飞书通知 - 已生成签名")

            # 构建请求数据
            data = {
                "msg_type": "text",
                "content": {
                    "text": message
                },
                "timestamp": timestamp
            }

            # 如果有签名，添加到请求数据中
            if sign:
                data["sign"] = sign

            logger.info(f"📱 飞书通知 - 请求数据构建完成")

            # 发送POST请求
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=data, timeout=10) as response:
                    response_text = await response.text()
                    logger.info(f"📱 飞书通知 - 响应状态: {response.status}")
                    logger.info(f"📱 飞书通知 - 响应内容: {response_text}")

                    if response.status == 200:
                        try:
                            response_json = json.loads(response_text)
                            if response_json.get('code') == 0:
                                logger.info(f"📱 飞书通知发送成功")
                            else:
                                logger.warning(f"📱 飞书通知发送失败: {response_json.get('msg', '未知错误')}")
                        except json.JSONDecodeError:
                            logger.info(f"📱 飞书通知发送成功（响应格式异常）")
                    else:
                        logger.warning(f"📱 飞书通知发送失败: HTTP {response.status}, 响应: {response_text}")

        except Exception as e:
            logger.error(f"📱 发送飞书通知异常: {self._safe_str(e)}")
            import traceback
            logger.error(f"📱 飞书通知异常详情: {traceback.format_exc()}")

    async def _send_bark_notification(self, config_data: dict, message: str):
        """发送Bark通知"""
        try:
            import aiohttp
            import json
            from urllib.parse import quote

            logger.info(f"📱 Bark通知 - 开始处理配置数据: {config_data}")

            # 解析配置
            server_url = config_data.get('server_url', 'https://api.day.app').rstrip('/')
            device_key = config_data.get('device_key', '')
            title = config_data.get('title', '闲鱼自动回复通知')
            sound = config_data.get('sound', 'default')
            icon = config_data.get('icon', '')
            group = config_data.get('group', 'xianyu')
            url = config_data.get('url', '')

            logger.info(f"📱 Bark通知 - 服务器: {server_url}")
            logger.info(f"📱 Bark通知 - 设备密钥: {device_key[:10]}..." if device_key else "📱 Bark通知 - 设备密钥: 未设置")
            logger.info(f"📱 Bark通知 - 标题: {title}")

            if not device_key:
                logger.warning("📱 Bark通知 - 设备密钥配置为空，无法发送通知")
                return

            # 构建请求URL和数据
            # Bark支持两种方式：URL路径方式和POST JSON方式
            # 这里使用POST JSON方式，更灵活且支持更多参数

            api_url = f"{server_url}/push"

            # 构建请求数据
            data = {
                "device_key": device_key,
                "title": title,
                "body": message,
                "sound": sound,
                "group": group
            }

            # 可选参数
            if icon:
                data["icon"] = icon
            if url:
                data["url"] = url

            logger.info(f"📱 Bark通知 - API地址: {api_url}")
            logger.info(f"📱 Bark通知 - 请求数据构建完成")

            # 发送POST请求
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, json=data, timeout=10) as response:
                    response_text = await response.text()
                    logger.info(f"📱 Bark通知 - 响应状态: {response.status}")
                    logger.info(f"📱 Bark通知 - 响应内容: {response_text}")

                    if response.status == 200:
                        try:
                            response_json = json.loads(response_text)
                            if response_json.get('code') == 200:
                                logger.info(f"📱 Bark通知发送成功")
                            else:
                                logger.warning(f"📱 Bark通知发送失败: {response_json.get('message', '未知错误')}")
                        except json.JSONDecodeError:
                            # 某些Bark服务器可能返回纯文本
                            if 'success' in response_text.lower() or 'ok' in response_text.lower():
                                logger.info(f"📱 Bark通知发送成功")
                            else:
                                logger.warning(f"📱 Bark通知响应格式异常: {response_text}")
                    else:
                        logger.warning(f"📱 Bark通知发送失败: HTTP {response.status}, 响应: {response_text}")

        except Exception as e:
            logger.error(f"📱 发送Bark通知异常: {self._safe_str(e)}")
            import traceback
            logger.error(f"📱 Bark通知异常详情: {traceback.format_exc()}")

    async def _send_webhook_notification(self, config_data: dict, message: str):
        """发送Webhook通知"""
        try:
            import aiohttp
            import json

            # 解析配置
            webhook_url = config_data.get('webhook_url', '')
            http_method = config_data.get('http_method', 'POST').upper()
            headers_str = config_data.get('headers', '{}')

            if not webhook_url:
                logger.warning("Webhook通知配置为空")
                return

            # 解析自定义请求头
            try:
                custom_headers = json.loads(headers_str) if headers_str else {}
            except json.JSONDecodeError:
                custom_headers = {}

            # 设置默认请求头
            headers = {'Content-Type': 'application/json'}
            headers.update(custom_headers)

            # 构建请求数据
            data = {
                'message': message,
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'source': 'xianyu-auto-reply'
            }

            async with aiohttp.ClientSession() as session:
                if http_method == 'POST':
                    async with session.post(webhook_url, json=data, headers=headers, timeout=10) as response:
                        if response.status == 200:
                            logger.info(f"Webhook通知发送成功")
                        else:
                            logger.warning(f"Webhook通知发送失败: {response.status}")
                elif http_method == 'PUT':
                    async with session.put(webhook_url, json=data, headers=headers, timeout=10) as response:
                        if response.status == 200:
                            logger.info(f"Webhook通知发送成功")
                        else:
                            logger.warning(f"Webhook通知发送失败: {response.status}")
                else:
                    logger.warning(f"不支持的HTTP方法: {http_method}")

        except Exception as e:
            logger.error(f"发送Webhook通知异常: {self._safe_str(e)}")

    async def _send_telegram_notification(self, config_data: dict, message: str):
        """发送Telegram通知"""
        try:
            import aiohttp

            # 解析配置
            bot_token = config_data.get('bot_token', '')
            chat_id = config_data.get('chat_id', '')

            if not all([bot_token, chat_id]):
                logger.warning("Telegram通知配置不完整")
                return

            # 构建API URL
            api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

            data = {
                'chat_id': chat_id,
                'text': message,
                'parse_mode': 'HTML'
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, json=data, timeout=10) as response:
                    if response.status == 200:
                        logger.info(f"Telegram通知发送成功")
                    else:
                        logger.warning(f"Telegram通知发送失败: {response.status}")

        except Exception as e:
            logger.error(f"发送Telegram通知异常: {self._safe_str(e)}")

    async def send_token_refresh_notification(self, error_message: str, notification_type: str = "token_refresh", chat_id: str = None, attachment_path: str = None, verification_url: str = None):
        """发送Token刷新异常通知（带防重复机制，支持附件）
        
        Args:
            error_message: 错误消息
            notification_type: 通知类型
            chat_id: 聊天ID（可选）
            attachment_path: 附件路径（可选，用于发送截图）
        """
        try:
            # 检查是否是正常的令牌过期，这种情况不需要发送通知
            if self._is_normal_token_expiry(error_message):
                logger.warning(f"检测到正常的令牌过期，跳过通知: {error_message}")
                return

            # 检查是否在冷却期内
            current_time = time.time()
            last_time = self.last_notification_time.get(notification_type, 0)

            # 为Token刷新异常通知使用特殊的3小时冷却时间
            # 基于错误消息内容判断是否为Token相关异常
            if self._is_token_related_error(error_message):
                cooldown_time = self.token_refresh_notification_cooldown
                cooldown_desc = "3小时"
            else:
                cooldown_time = self.notification_cooldown
                cooldown_desc = f"{self.notification_cooldown // 60}分钟"

            if current_time - last_time < cooldown_time:
                remaining_time = cooldown_time - (current_time - last_time)
                remaining_hours = int(remaining_time // 3600)
                remaining_minutes = int((remaining_time % 3600) // 60)
                remaining_seconds = int(remaining_time % 60)

                if remaining_hours > 0:
                    time_desc = f"{remaining_hours}小时{remaining_minutes}分钟"
                elif remaining_minutes > 0:
                    time_desc = f"{remaining_minutes}分钟{remaining_seconds}秒"
                else:
                    time_desc = f"{remaining_seconds}秒"

                logger.warning(f"Token刷新通知在冷却期内，跳过发送: {notification_type} (还需等待 {time_desc})")
                return

            from db_manager import db_manager

            # 获取当前账号的通知配置
            notifications = db_manager.get_account_notifications(self.cookie_id)

            if not notifications:
                logger.warning("未配置消息通知，跳过Token刷新通知")
                return

            # 构造通知消息
            # 判断异常信息中是否包含"滑块验证成功"
            if "滑块验证成功" in error_message:
                notification_msg = f"{error_message}\n\n" \
                                  f"账号: {self.cookie_id}\n" \
                                  f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            elif verification_url:
                # 如果有验证链接，添加到消息中
                notification_msg = f"{error_message}\n\n" \
                                  f"账号: {self.cookie_id}\n" \
                                  f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n" \
                                  f"验证链接: {verification_url}\n"
            else:
                notification_msg = f"Token刷新异常\n\n" \
                                  f"账号ID: {self.cookie_id}\n" \
                                  f"异常时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}\n" \
                                  f"异常信息: {error_message}\n\n" \
                                  f"请检查账号Cookie是否过期，如有需要请及时更新Cookie配置。\n"

            logger.info(f"准备发送Token刷新异常通知: {self.cookie_id}")

            # 发送通知到各个渠道
            notification_sent = False
            for notification in notifications:
                if not notification.get('enabled', True):
                    continue

                channel_type = notification.get('channel_type')
                channel_config = notification.get('channel_config')

                try:
                    # 解析配置数据
                    config_data = self._parse_notification_config(channel_config)

                    match channel_type:
                        case 'ding_talk' | 'dingtalk':
                            await self._send_dingtalk_notification(config_data, notification_msg)
                            notification_sent = True
                        case 'feishu' | 'lark':
                            await self._send_feishu_notification(config_data, notification_msg)
                            notification_sent = True
                        case 'bark':
                            await self._send_bark_notification(config_data, notification_msg)
                            notification_sent = True
                        case 'email':
                            # 邮件支持附件
                            await self._send_email_notification(config_data, notification_msg, attachment_path)
                            notification_sent = True
                        case 'webhook':
                            await self._send_webhook_notification(config_data, notification_msg)
                            notification_sent = True
                        case 'wechat':
                            await self._send_wechat_notification(config_data, notification_msg)
                            notification_sent = True
                        case 'telegram':
                            await self._send_telegram_notification(config_data, notification_msg)
                            notification_sent = True
                        case _:
                            logger.warning(f"不支持的通知渠道类型: {channel_type}")

                except Exception as notify_error:
                    logger.error(f"发送Token刷新通知失败 ({notification.get('channel_name', 'Unknown')}): {self._safe_str(notify_error)}")

            # 如果成功发送了通知，更新最后发送时间
            if notification_sent:
                self.last_notification_time[notification_type] = current_time

                # 根据错误消息内容使用不同的冷却时间
                if self._is_token_related_error(error_message):
                    next_send_time = current_time + self.token_refresh_notification_cooldown
                    cooldown_desc = "3小时"
                else:
                    next_send_time = current_time + self.notification_cooldown
                    cooldown_desc = f"{self.notification_cooldown // 60}分钟"

                next_send_time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(next_send_time))
                logger.info(f"Token刷新通知已发送，下次可发送时间: {next_send_time_str} (冷却时间: {cooldown_desc})")

        except Exception as e:
            logger.error(f"处理Token刷新通知失败: {self._safe_str(e)}")

    def _is_normal_token_expiry(self, error_message: str) -> bool:
        """检查是否是正常的令牌过期或其他不需要通知的情况"""
        # 不需要发送通知的关键词
        no_notification_keywords = [
            # 正常的令牌过期
            'FAIL_SYS_TOKEN_EXOIRED::令牌过期',
            'FAIL_SYS_TOKEN_EXPIRED::令牌过期',
            'FAIL_SYS_TOKEN_EXOIRED',
            'FAIL_SYS_TOKEN_EXPIRED',
            '令牌过期',
            # Session过期（正常情况）
            'FAIL_SYS_SESSION_EXPIRED::Session过期',
            'FAIL_SYS_SESSION_EXPIRED',
            'Session过期',
            # Token定时刷新失败（会自动重试）
            'Token定时刷新失败，将自动重试',
            'Token定时刷新失败'
        ]

        # 检查错误消息是否包含不需要通知的关键词
        for keyword in no_notification_keywords:
            if keyword in error_message:
                return True

        return False

    def _is_token_related_error(self, error_message: str) -> bool:
        """检查是否是Token相关的错误，需要使用3小时冷却时间"""
        # Token相关错误的关键词
        token_error_keywords = [
            # Token刷新失败相关
            'Token刷新失败',
            'Token刷新异常',
            'token刷新失败',
            'token刷新异常',
            'TOKEN刷新失败',
            'TOKEN刷新异常',
            # 具体的Token错误信息
            'FAIL_SYS_USER_VALIDATE',
            'RGV587_ERROR',
            '哎哟喂,被挤爆啦',
            '请稍后重试',
            'punish?x5secdata',
            'captcha',
            # Token获取失败
            '无法获取有效token',
            '无法获取有效Token',
            'Token获取失败',
            'token获取失败',
            'TOKEN获取失败',
            # Token定时刷新失败
            'Token定时刷新失败',
            'token定时刷新失败',
            'TOKEN定时刷新失败',
            # 初始化Token失败
            '初始化时无法获取有效Token',
            '初始化时无法获取有效token',
            # 其他Token相关错误
            'accessToken',
            'access_token',
            '_m_h5_tk',
            'mtop.taobao.idlemessage.pc.login.token'
        ]

        # 检查错误消息是否包含Token相关的关键词
        error_message_lower = error_message.lower()
        for keyword in token_error_keywords:
            if keyword.lower() in error_message_lower:
                return True

        return False

    async def auto_confirm(self, order_id, item_id=None, retry_count=0):
        """自动确认发货 - 使用加密模块，不包含延时处理（延时已在_auto_delivery中处理）"""
        try:
            logger.warning(f"【{self.cookie_id}】开始确认发货，订单ID: {order_id}")

            # 导入解密后的确认发货模块
            from secure_confirm_decrypted import SecureConfirm

            # 创建确认实例，传入主界面类实例
            secure_confirm = SecureConfirm(self.session, self.cookies_str, self.cookie_id, self)

            # 传递必要的属性
            secure_confirm.current_token = self.current_token
            secure_confirm.last_token_refresh_time = self.last_token_refresh_time
            secure_confirm.token_refresh_interval = self.token_refresh_interval

            # 调用确认方法，传入item_id用于token刷新
            result = await secure_confirm.auto_confirm(order_id, item_id, retry_count)

            # 同步更新后的cookies和token
            if secure_confirm.cookies_str != self.cookies_str:
                self.cookies_str = secure_confirm.cookies_str
                self.cookies = secure_confirm.cookies
                logger.warning(f"【{self.cookie_id}】已同步确认发货模块更新的cookies")

            if secure_confirm.current_token != self.current_token:
                self.current_token = secure_confirm.current_token
                self.last_token_refresh_time = secure_confirm.last_token_refresh_time
                logger.warning(f"【{self.cookie_id}】已同步确认发货模块更新的token")

            return result

        except Exception as e:
            logger.error(f"【{self.cookie_id}】加密确认模块调用失败: {self._safe_str(e)}")
            return {"error": f"加密确认模块调用失败: {self._safe_str(e)}", "order_id": order_id}

    async def auto_evaluate(self, order_id: str, item_id: str = None, buyer_id: str = None):
        """自动评价买家"""
        try:
            from db_manager import db_manager
            config = db_manager.get_evaluation_config(self.cookie_id)
            if not config.get('auto_evaluate_enabled', False):
                return {'success': False, 'error': '自动评价未启用'}
            
            evaluate_content = config.get('evaluate_content', '感谢您的购买，欢迎再次光临！')
            
            evaluate_api = 'mtop.taobao.idle.rate.write'
            data = {
                'api': evaluate_api,
                'data': {
                    'bizOrderId': order_id,
                    'content': evaluate_content,
                    'score': 5,
                }
            }
            
            url = 'https://h5api.m.goofish.com/h5/' + evaluate_api + '/1.0/'
            async with self.session.post(url, json=data, headers=self._get_headers()) as response:
                res_json = await response.json()
                ret = res_json.get('ret', [])
                if ret and len(ret) > 0:
                    ret_msg = ret[0]
                    if ret_msg.get('code') == 'SUCCESS':
                        logger.info(f"【{self.cookie_id}】✅ 自动评价成功: {order_id}")
                        return {'success': True, 'message': '评价成功'}
                    else:
                        error_msg = ret_msg.get('msg', '未知错误')
                        logger.warning(f"【{self.cookie_id}】❌ 自动评价失败: {order_id}, {error_msg}")
                        return {'success': False, 'error': error_msg}
                return {'success': False, 'error': 'API响应异常'}
        except Exception as e:
            logger.error(f"【{self.cookie_id}】自动评价异常: {self._safe_str(e)}")
            return {'success': False, 'error': str(e)}

    async def _get_api_card_content(self, rule, order_id=None, item_id=None, buyer_id=None, spec_name=None, spec_value=None, retry_count=0):
        """调用API获取卡券内容，支持动态参数替换和重试机制"""
        max_retries = 4

        if retry_count >= max_retries:
            logger.error(f"API调用失败，已达到最大重试次数({max_retries})")
            return None

        try:
            import aiohttp
            import json

            api_config = rule.get('api_config')
            if not api_config:
                logger.error(f"API配置为空，规则ID: {rule.get('id')}, 卡券名称: {rule.get('card_name')}")
                logger.warning(f"规则详情: {rule}")
                return None

            # 解析API配置
            if isinstance(api_config, str):
                api_config = json.loads(api_config)

            url = api_config.get('url')
            method = api_config.get('method', 'GET').upper()
            timeout = api_config.get('timeout', 10)
            headers = api_config.get('headers', '{}')
            params = api_config.get('params', '{}')

            # 解析headers和params
            if isinstance(headers, str):
                headers = json.loads(headers)
            if isinstance(params, str):
                params = json.loads(params)

            # 如果是POST请求且有动态参数，进行参数替换
            if method == 'POST' and params:
                params = await self._replace_api_dynamic_params(params, order_id, item_id, buyer_id, spec_name, spec_value)

            retry_info = f" (重试 {retry_count + 1}/{max_retries})" if retry_count > 0 else ""
            logger.info(f"调用API获取卡券: {method} {url}{retry_info}")
            if method == 'POST' and params:
                logger.warning(f"POST请求参数: {json.dumps(params, ensure_ascii=False)}")

            # 确保session存在
            if not self.session:
                await self.create_session()

            # 发起HTTP请求
            timeout_obj = aiohttp.ClientTimeout(total=timeout)

            if method == 'GET':
                async with self.session.get(url, headers=headers, params=params, timeout=timeout_obj) as response:
                    status_code = response.status
                    response_text = await response.text()
            elif method == 'POST':
                async with self.session.post(url, headers=headers, json=params, timeout=timeout_obj) as response:
                    status_code = response.status
                    response_text = await response.text()
            else:
                logger.error(f"不支持的HTTP方法: {method}")
                return None

            if status_code == 200:
                # 尝试解析JSON响应，如果失败则使用原始文本
                try:
                    result = json.loads(response_text)
                    # 如果返回的是对象，尝试提取常见的内容字段
                    if isinstance(result, dict):
                        content = result.get('data') or result.get('content') or result.get('card') or str(result)
                    else:
                        content = str(result)
                except:
                    content = response_text

                logger.info(f"API调用成功，返回内容长度: {len(content)}")
                return content
            else:
                logger.warning(f"API调用失败: {status_code} - {response_text[:200]}...")

                # 如果是服务器错误(5xx)或请求超时，进行重试
                if status_code >= 500 or status_code == 408:
                    if retry_count < max_retries - 1:
                        wait_time = (retry_count + 1) * 2  # 递增等待时间: 2s, 4s, 6s
                        logger.info(f"等待 {wait_time} 秒后重试...")
                        await asyncio.sleep(self._random_delay(wait_time, 0.3))
                        return await self._get_api_card_content(rule, order_id, item_id, buyer_id, spec_name, spec_value, retry_count + 1)

                return None

        except (aiohttp.ClientTimeout, aiohttp.ClientError) as e:
            logger.warning(f"API调用网络异常: {self._safe_str(e)}")

            # 网络异常也进行重试
            if retry_count < max_retries - 1:
                wait_time = (retry_count + 1) * 2  # 递增等待时间
                logger.info(f"等待 {wait_time} 秒后重试...")
                await asyncio.sleep(self._random_delay(wait_time, 0.3))
                return await self._get_api_card_content(rule, order_id, item_id, buyer_id, spec_name, spec_value, retry_count + 1)
            else:
                logger.error(f"API调用网络异常，已达到最大重试次数: {self._safe_str(e)}")
                return None

        except Exception as e:
            logger.error(f"API调用异常: {self._safe_str(e)}")
            return None

    async def _replace_api_dynamic_params(self, params, order_id=None, item_id=None, buyer_id=None, spec_name=None, spec_value=None):
        """替换API请求参数中的动态参数"""
        try:
            if not params or not isinstance(params, dict):
                return params

            # 获取订单和商品信息
            order_info = None
            item_info = None

            # 如果有订单ID，获取订单信息
            if order_id:
                try:
                    from db_manager import db_manager
                    # 尝试从数据库获取订单信息
                    order_info = db_manager.get_order_by_id(order_id)
                    if not order_info:
                        # 如果数据库中没有，尝试通过API获取
                        order_detail = await self.fetch_order_detail_info(order_id, item_id, buyer_id)
                        if order_detail:
                            order_info = order_detail
                            logger.warning(f"通过API获取到订单信息: {order_id}")
                        else:
                            logger.warning(f"无法获取订单信息: {order_id}")
                    else:
                        logger.warning(f"从数据库获取到订单信息: {order_id}")
                except Exception as e:
                    logger.warning(f"获取订单信息失败: {self._safe_str(e)}")

            # 如果有商品ID，获取商品信息
            if item_id:
                try:
                    from db_manager import db_manager
                    item_info = db_manager.get_item_info(self.cookie_id, item_id)
                    if item_info:
                        logger.warning(f"从数据库获取到商品信息: {item_id}")
                    else:
                        logger.warning(f"无法获取商品信息: {item_id}")
                except Exception as e:
                    logger.warning(f"获取商品信息失败: {self._safe_str(e)}")

            # 构建参数映射
            param_mapping = {
                'order_id': order_id or '',
                'item_id': item_id or '',
                'buyer_id': buyer_id or '',
                'cookie_id': self.cookie_id or '',
                'spec_name': spec_name or '',
                'spec_value': spec_value or '',
            }

            # 从订单信息中提取参数
            if order_info:
                param_mapping.update({
                    'order_amount': str(order_info.get('amount', '')),
                    'order_quantity': str(order_info.get('quantity', '')),
                })

            # 从商品信息中提取参数
            if item_info:
                # 处理商品详情，如果是JSON字符串则提取detail字段
                item_detail = item_info.get('item_detail', '')
                if item_detail:
                    try:
                        # 尝试解析JSON
                        import json
                        detail_data = json.loads(item_detail)
                        if isinstance(detail_data, dict) and 'detail' in detail_data:
                            item_detail = detail_data['detail']
                    except (json.JSONDecodeError, TypeError):
                        # 如果不是JSON或解析失败，使用原始字符串
                        pass

                param_mapping.update({
                    'item_detail': item_detail,
                })

            # 递归替换参数
            replaced_params = self._recursive_replace_params(params, param_mapping)

            # 记录替换的参数
            replaced_keys = []
            for key, value in replaced_params.items():
                if isinstance(value, str) and '{' in str(params.get(key, '')):
                    replaced_keys.append(key)

            if replaced_keys:
                logger.info(f"API动态参数替换完成，替换的参数: {replaced_keys}")
                logger.warning(f"参数映射: {param_mapping}")

            return replaced_params

        except Exception as e:
            logger.error(f"替换API动态参数失败: {self._safe_str(e)}")
            return params

    def _recursive_replace_params(self, obj, param_mapping):
        """递归替换参数中的占位符"""
        if isinstance(obj, dict):
            result = {}
            for key, value in obj.items():
                result[key] = self._recursive_replace_params(value, param_mapping)
            return result
        elif isinstance(obj, list):
            return [self._recursive_replace_params(item, param_mapping) for item in obj]
        elif isinstance(obj, str):
            # 替换字符串中的占位符
            result = obj
            for param_key, param_value in param_mapping.items():
                placeholder = f"{{{param_key}}}"
                if placeholder in result:
                    result = result.replace(placeholder, str(param_value))
            return result
        else:
            return obj

    async def token_refresh_loop(self):
        """Token刷新循环"""
        try:
            while True:
                try:
                    # 检查账号是否启用
                    from cookie_manager import manager as cookie_manager
                    if cookie_manager and not cookie_manager.get_cookie_status(self.cookie_id):
                        logger.info(f"【{self.cookie_id}】账号已禁用，停止Token刷新循环")
                        break

                    current_time = time.time()
                    if current_time - self.last_token_refresh_time >= self.token_refresh_interval:
                        logger.info("Token即将过期，准备刷新...")
                        new_token = await self.refresh_token()
                        if new_token:
                            logger.info(f"【{self.cookie_id}】Token刷新成功，将关闭WebSocket以使用新Token重连")
                            
                            # Token刷新成功后，需要关闭WebSocket连接，让它用新Token重新连接
                            # 原因：WebSocket连接建立时使用的是旧Token，新Token需要重新建立连接才能生效
                            # 注意：只关闭WebSocket，不重启整个实例（后台任务继续运行）
                            
                            # 关闭当前WebSocket连接
                            if self.ws and not self.ws.closed:
                                try:
                                    logger.info(f"【{self.cookie_id}】关闭当前WebSocket连接以使用新Token重连...")
                                    await self.ws.close()
                                    logger.info(f"【{self.cookie_id}】WebSocket连接已关闭，将自动重连")
                                except Exception as close_e:
                                    logger.warning(f"【{self.cookie_id}】关闭WebSocket时出错: {self._safe_str(close_e)}")
                            
                            # 退出Token刷新循环，让main循环重新建立连接
                            # 后台任务（心跳、清理等）继续运行
                            logger.info(f"【{self.cookie_id}】Token刷新完成，WebSocket将使用新Token重新连接")
                            break
                        else:
                            # 根据上一次刷新状态决定日志级别（冷却/已重启为正常情况）
                            if getattr(self, 'last_token_refresh_status', None) in ("skipped_cooldown", "restarted_after_cookie_refresh"):
                                logger.info(f"【{self.cookie_id}】Token刷新未执行或已重启（正常），将在{self.token_retry_interval // 60}分钟后重试")
                            else:
                                logger.error(f"【{self.cookie_id}】Token刷新失败，将在{self.token_retry_interval // 60}分钟后重试")

                            # 清空当前token，确保下次重试时重新获取
                            self.current_token = None

                            # 发送Token刷新失败通知
                            await self.send_token_refresh_notification("Token定时刷新失败，将自动重试", "token_scheduled_refresh_failed")
                            await self._interruptible_sleep(self._randomize_interval(self.token_retry_interval, 0.2))
                            continue
                    await self._interruptible_sleep(self._randomize_interval(60, 0.2))
                except asyncio.CancelledError:
                    # 收到取消信号，立即退出循环
                    logger.info(f"【{self.cookie_id}】Token刷新循环收到取消信号，准备退出")
                    raise
                except Exception as e:
                    logger.error(f"Token刷新循环出错: {self._safe_str(e)}")
                    # 出错后也等待1分钟再重试，使用可中断的sleep
                    try:
                        await self._interruptible_sleep(self._randomize_interval(60, 0.2))
                    except asyncio.CancelledError:
                        logger.info(f"【{self.cookie_id}】Token刷新循环在重试等待时收到取消信号，准备退出")
                        raise
        except asyncio.CancelledError:
            # 确保CancelledError被正确传播
            logger.info(f"【{self.cookie_id}】Token刷新循环已取消，正在退出...")
            raise
        finally:
            # 确保任务能正常结束
            logger.info(f"【{self.cookie_id}】Token刷新循环已退出")

    async def init(self, ws):
        # 如果没有token或者token过期，获取新token
        token_refresh_attempted = False
        if not self.current_token or (time.time() - self.last_token_refresh_time) >= self.token_refresh_interval:
            logger.info(f"【{self.cookie_id}】获取初始token...")
            token_refresh_attempted = True

            await self.refresh_token()

        if not self.current_token:
            logger.error("无法获取有效token，初始化失败")
            # 只有在没有尝试刷新token的情况下才发送通知，避免与refresh_token中的通知重复
            if not token_refresh_attempted:
                await self.send_token_refresh_notification("初始化时无法获取有效Token", "token_init_failed")
            else:
                logger.info("由于刚刚尝试过token刷新，跳过重复的初始化失败通知")
            raise Exception("Token获取失败")

        msg = {
            "lwp": "/reg",
            "headers": {
                "cache-header": "app-key token ua wv",
                "app-key": APP_CONFIG.get('app_key'),
                "token": self.current_token,
                "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 DingTalk(2.1.5) OS(Windows/10) Browser(Chrome/133.0.0.0) DingWeb/2.1.5 IMPaaS DingWeb/2.1.5",
                "dt": "j",
                "wv": "im:3,au:3,sy:6",
                "sync": "0,0;0;0;",
                "did": self.device_id,
                "mid": generate_mid()
            }
        }
        await ws.send(json.dumps(msg))
        await asyncio.sleep(self._random_delay(1.0, 0.3))
        current_time = int(time.time() * 1000)
        msg = {
            "lwp": "/r/SyncStatus/ackDiff",
            "headers": {"mid": generate_mid()},
            "body": [
                {
                    "pipeline": "sync",
                    "tooLong2Tag": "PNM,1",
                    "channel": "sync",
                    "topic": "sync",
                    "highPts": 0,
                    "pts": current_time * 1000,
                    "seq": 0,
                    "timestamp": current_time
                }
            ]
        }
        await ws.send(json.dumps(msg))
        logger.info(f'【{self.cookie_id}】连接注册完成')

    async def send_heartbeat(self, ws):
        """发送心跳包"""
        # 检查WebSocket连接状态，如果已关闭则不发送
        if ws.closed:
            raise ConnectionError("WebSocket连接已关闭，无法发送心跳")
        
        msg = {
            "lwp": "/!",
            "headers": {
                "mid": generate_mid()
            }
        }
        # 添加超时保护，避免在WebSocket关闭时阻塞
        try:
            await asyncio.wait_for(ws.send(json.dumps(msg)), timeout=2.0)
            self.last_heartbeat_time = time.time()
            logger.warning(f"【{self.cookie_id}】心跳包已发送")
        except asyncio.TimeoutError:
            raise ConnectionError("心跳发送超时，WebSocket可能已断开")
        except asyncio.CancelledError:
            # 如果被取消，立即重新抛出，不执行后续操作
            raise

    async def heartbeat_loop(self, ws):
        """心跳循环"""
        consecutive_failures = 0
        max_failures = 3  # 连续失败3次后停止心跳

        try:
            while True:
                try:
                    # 检查账号是否启用
                    from cookie_manager import manager as cookie_manager
                    if cookie_manager and not cookie_manager.get_cookie_status(self.cookie_id):
                        logger.info(f"【{self.cookie_id}】账号已禁用，停止心跳循环")
                        break

                    # 检查WebSocket连接状态
                    if ws.closed:
                        logger.warning(f"【{self.cookie_id}】WebSocket连接已关闭，停止心跳循环")
                        break

                    await self.send_heartbeat(ws)
                    consecutive_failures = 0  # 重置失败计数

                    await self._interruptible_sleep(self._randomize_interval(self.heartbeat_interval, 0.2))

                except asyncio.CancelledError:
                    # 收到取消信号，立即退出循环
                    logger.info(f"【{self.cookie_id}】心跳循环收到取消信号，准备退出")
                    raise  # 重新抛出，让任务正常结束
                except Exception as e:
                    consecutive_failures += 1
                    logger.error(f"心跳发送失败 ({consecutive_failures}/{max_failures}): {self._safe_str(e)}")

                    if consecutive_failures >= max_failures:
                        logger.error(f"【{self.cookie_id}】心跳连续失败{max_failures}次，停止心跳循环")
                        break

                    # 失败后短暂等待再重试，使用可中断的sleep
                    try:
                        await self._interruptible_sleep(self._randomize_interval(5, 0.2))
                    except asyncio.CancelledError:
                        # 在等待重试时收到取消信号，立即退出
                        logger.info(f"【{self.cookie_id}】心跳循环在重试等待时收到取消信号，准备退出")
                        raise
        except asyncio.CancelledError:
            # 确保CancelledError被正确传播
            logger.info(f"【{self.cookie_id}】心跳循环已取消，正在退出...")
            raise
        finally:
            # 确保任务能正常结束
            logger.info(f"【{self.cookie_id}】心跳循环已退出")

    async def handle_heartbeat_response(self, message_data):
        """处理心跳响应"""
        try:
            if message_data.get("code") == 200:
                self.last_heartbeat_response = time.time()
                logger.warning("心跳响应正常")
                return True
        except Exception as e:
            logger.error(f"处理心跳响应出错: {self._safe_str(e)}")
        return False

    async def pause_cleanup_loop(self):
        """定期清理过期的暂停记录、锁和缓存"""
        try:
            while True:
                try:
                    # 检查账号是否启用
                    from cookie_manager import manager as cookie_manager
                    if cookie_manager and not cookie_manager.get_cookie_status(self.cookie_id):
                        logger.info(f"【{self.cookie_id}】账号已禁用，停止清理循环")
                        break

                    # 清理过期的暂停记录
                    pause_manager.cleanup_expired_pauses()
                    await asyncio.sleep(0)  # 让出控制权，允许检查取消信号

                    # 清理过期的锁（每5分钟清理一次，保留24小时内的锁）
                    self.cleanup_expired_locks(max_age_hours=24)
                    await asyncio.sleep(0)  # 让出控制权，允许检查取消信号

                    # 清理过期的商品详情缓存
                    try:
                        cleaned_count = await self._cleanup_item_cache()
                        if cleaned_count > 0:
                            logger.info(f"【{self.cookie_id}】清理了 {cleaned_count} 个过期的商品详情缓存")
                    except asyncio.CancelledError:
                        raise
                    except Exception as cache_clean_e:
                        logger.warning(f"【{self.cookie_id}】清理商品详情缓存时出错: {cache_clean_e}")

                    # 清理过期的通知、发货和订单确认记录（防止内存泄漏）
                    self._cleanup_instance_caches()
                    await asyncio.sleep(0)  # 让出控制权，允许检查取消信号

                    # 清理QR登录过期会话（每5分钟检查一次）
                    try:
                        from utils.qr_login import qr_login_manager
                        qr_login_manager.cleanup_expired_sessions()
                        await asyncio.sleep(0)  # 让出控制权，允许检查取消信号
                    except asyncio.CancelledError:
                        raise
                    except Exception as qr_clean_e:
                        logger.warning(f"【{self.cookie_id}】清理QR登录会话时出错: {qr_clean_e}")
                    
                    # 清理Playwright浏览器临时文件和缓存（每5分钟检查一次）
                    try:
                        await self._cleanup_playwright_cache()
                    except asyncio.CancelledError:
                        raise
                    except Exception as pw_clean_e:
                        logger.warning(f"【{self.cookie_id}】清理Playwright缓存时出错: {pw_clean_e}")
                    
                    # 清理过期的日志文件（每5分钟检查一次，保留7天）
                    try:
                        cleaned_logs = await self._cleanup_old_logs(retention_days=7)
                        await asyncio.sleep(0)  # 让出控制权，允许检查取消信号
                    except asyncio.CancelledError:
                        raise
                    except Exception as log_clean_e:
                        logger.warning(f"【{self.cookie_id}】清理日志文件时出错: {log_clean_e}")
                    
                    # 清理数据库历史数据（每天一次，保留90天数据）
                    # 为避免所有实例同时执行，只让第一个实例执行
                    try:
                        if hasattr(self.__class__, '_last_db_cleanup_time'):
                            last_cleanup = self.__class__._last_db_cleanup_time
                        else:
                            self.__class__._last_db_cleanup_time = 0
                            last_cleanup = 0
                        
                        current_time = time.time()
                        # 每24小时清理一次
                        if current_time - last_cleanup > 86400:
                            logger.info(f"【{self.cookie_id}】开始执行数据库历史数据清理...")
                            # 数据库清理可能很耗时，使用线程池执行，避免阻塞事件循环
                            # 这样即使清理操作很慢，也能响应取消信号
                            try:
                                stats = await asyncio.to_thread(db_manager.cleanup_old_data, days=90)
                                if 'error' not in stats:
                                    logger.info(f"【{self.cookie_id}】数据库清理完成: {stats}")
                                    self.__class__._last_db_cleanup_time = current_time
                                else:
                                    logger.error(f"【{self.cookie_id}】数据库清理失败: {stats['error']}")
                            except asyncio.CancelledError:
                                logger.warning(f"【{self.cookie_id}】数据库清理被取消")
                                raise
                    except asyncio.CancelledError:
                        raise  # 重新抛出取消信号
                    except Exception as db_clean_e:
                        logger.error(f"【{self.cookie_id}】清理数据库历史数据时出错: {db_clean_e}")

                    # 每5分钟清理一次
                    await self._interruptible_sleep(self._randomize_interval(300, 0.2))
                except asyncio.CancelledError:
                    # 收到取消信号，立即退出循环
                    logger.info(f"【{self.cookie_id}】清理循环收到取消信号，准备退出")
                    raise
                except Exception as e:
                    logger.error(f"【{self.cookie_id}】清理任务失败: {self._safe_str(e)}")
                    # 出错后也等待5分钟再重试，使用可中断的sleep
                    try:
                        await self._interruptible_sleep(self._randomize_interval(300, 0.2))
                    except asyncio.CancelledError:
                        logger.info(f"【{self.cookie_id}】清理循环在重试等待时收到取消信号，准备退出")
                        raise
        except asyncio.CancelledError:
            # 确保CancelledError被正确传播
            logger.info(f"【{self.cookie_id}】清理循环已取消，正在退出...")
            raise
        finally:
            # 确保任务能正常结束
            logger.info(f"【{self.cookie_id}】清理循环已退出")


    async def _normal_close_resources(self, browser, playwright):
        """正常关闭资源：浏览器+Playwright短超时关闭"""
        try:
            # 先关闭浏览器，再关闭Playwright
            if browser:
                try:
                    # 关闭浏览器，设置超时
                    await asyncio.wait_for(browser.close(), timeout=5.0)
                    logger.info(f"【{self.cookie_id}】浏览器关闭完成")
                except asyncio.TimeoutError:
                    logger.warning(f"【{self.cookie_id}】浏览器关闭超时，尝试强制关闭")
                    try:
                        # 尝试强制关闭
                        if hasattr(browser, '_connection'):
                            browser._connection.dispose()
                    except Exception:
                        pass
                except Exception as e:
                    logger.warning(f"【{self.cookie_id}】关闭浏览器时出错: {e}")
            
            # 关闭Playwright：使用短超时，如果超时就放弃
            if playwright:
                try:
                    logger.info(f"【{self.cookie_id}】正在关闭Playwright...")
                    # 增加超时时间，确保Playwright有足够时间清理资源
                    await asyncio.wait_for(playwright.stop(), timeout=5.0)
                    logger.info(f"【{self.cookie_id}】Playwright关闭完成")
                except asyncio.TimeoutError:
                    logger.warning(f"【{self.cookie_id}】Playwright关闭超时，将自动清理")
                    # 尝试强制清理Playwright的内部连接
                    try:
                        if hasattr(playwright, '_connection'):
                            playwright._connection.dispose()
                    except Exception:
                        pass
                except Exception as e:
                    logger.warning(f"【{self.cookie_id}】关闭Playwright时出错: {e}")
                
        except Exception as e:
            logger.error(f"【{self.cookie_id}】正常关闭时出现异常: {e}")
            raise

    
    async def _force_close_resources(self, browser, playwright):
        """强制关闭资源：强制关闭浏览器+Playwright超时等待"""
        try:
            logger.warning(f"【{self.cookie_id}】开始强制关闭资源...")
            
            # 强制关闭浏览器+Playwright，设置短超时
            force_tasks = []
            if browser:
                force_tasks.append(asyncio.wait_for(browser.close(), timeout=3.0))
            if playwright:
                force_tasks.append(asyncio.wait_for(playwright.stop(), timeout=3.0))
            
            if force_tasks:
                # 使用gather执行，所有失败都会被忽略
                results = await asyncio.gather(*force_tasks, return_exceptions=True)
                
                # 检查是否有超时或异常，尝试强制清理
                for i, result in enumerate(results):
                    if isinstance(result, (asyncio.TimeoutError, Exception)):
                        resource_name = "浏览器" if i == 0 and browser else "Playwright"
                        logger.warning(f"【{self.cookie_id}】{resource_name}强制关闭失败，尝试直接清理连接")
                        try:
                            if i == 0 and browser and hasattr(browser, '_connection'):
                                browser._connection.dispose()
                            elif playwright and hasattr(playwright, '_connection'):
                                playwright._connection.dispose()
                        except Exception:
                            pass
                
                logger.info(f"【{self.cookie_id}】强制关闭完成")
            else:
                logger.info(f"【{self.cookie_id}】没有需要强制关闭的资源")
            
        except Exception as e:
            logger.warning(f"【{self.cookie_id}】强制关闭时出现异常（已忽略）: {e}")

    def is_sync_package(self, message_data):
        """判断是否为同步包消息"""
        try:
            return (
                isinstance(message_data, dict)
                and "body" in message_data
                and "syncPushPackage" in message_data["body"]
                and "data" in message_data["body"]["syncPushPackage"]
                and len(message_data["body"]["syncPushPackage"]["data"]) > 0
            )
        except Exception:
            return False

    async def create_session(self):
        """创建aiohttp session"""
        if not self.session:
            # 创建带有cookies和headers的session
            headers = DEFAULT_HEADERS.copy()
            headers['cookie'] = self.cookies_str

            self.session = aiohttp.ClientSession(
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            )

    async def close_session(self):
        """关闭aiohttp session"""
        if self.session:
            await self.session.close()
            self.session = None

    async def send_image_from_file(self, ws, cid, toid, image_path):
        """从本地文件发送图片"""
        try:
            # 上传图片到闲鱼CDN
            logger.info(f"【{self.cookie_id}】开始上传图片: {image_path}")

            from utils.image_uploader import ImageUploader
            uploader = ImageUploader(self.cookies_str)

            async with uploader:
                image_url = await uploader.upload_image(image_path)

            if image_url:
                # 获取图片信息
                from utils.image_utils import image_manager
                try:
                    from PIL import Image
                    with Image.open(image_path) as img:
                        width, height = img.size
                except Exception as e:
                    logger.warning(f"无法获取图片尺寸，使用默认值: {e}")
                    width, height = 800, 600

                # 发送图片消息
                await self.send_image_msg(ws, cid, toid, image_url, width, height)
                logger.info(f"【{self.cookie_id}】图片发送完成: {image_path} -> {image_url}")
                return True
            else:
                logger.error(f"【{self.cookie_id}】图片上传失败: {image_path}")
                logger.error(f"【{self.cookie_id}】❌ Cookie可能已失效！请检查配置并更新Cookie")
                return False

        except Exception as e:
            logger.error(f"【{self.cookie_id}】从文件发送图片失败: {self._safe_str(e)}")
            return False

if __name__ == '__main__':
    cookies_str = os.getenv('COOKIES_STR')
    xianyuLive = XianyuLive(cookies_str)
    asyncio.run(xianyuLive.main())
