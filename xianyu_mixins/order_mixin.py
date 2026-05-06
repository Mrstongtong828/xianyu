"""
订单和发货管理
"""
import json
import time
import asyncio
import traceback
from typing import Optional, Dict, Any, List
from loguru import logger


class OrderMixin:
    """订单和发货管理"""

    # Methods moved from XianyuLive
    def _init_order_status_handler(self):
        """初始化订单状态处理器"""
        try:
            # 直接导入订单状态处理器
            from order_status_handler import order_status_handler
            self.order_status_handler = order_status_handler
            logger.info(f"【{self.cookie_id}】订单状态处理器已启用")
        except Exception as e:
            logger.error(f"【{self.cookie_id}】初始化订单状态处理器失败: {self._safe_str(e)}")
            self.order_status_handler = None

    def can_auto_delivery(self, order_id: str) -> bool:
        """检查是否可以进行自动发货（防重复发货）- 基于订单ID"""
        if not order_id:
            # 如果没有订单ID，则不进行冷却检查，允许发货
            return True

        current_time = time.time()
        last_delivery = self.last_delivery_time.get(order_id, 0)

        if current_time - last_delivery < self.delivery_cooldown:
            logger.info(f"【{self.cookie_id}】订单 {order_id} 在冷却期内，跳过自动发货")
            return False

        return True

    def mark_delivery_sent(self, order_id: str):
        """标记订单已发货"""
        self.delivery_sent_orders.add(order_id)
        logger.info(f"【{self.cookie_id}】订单 {order_id} 已标记为发货")
        
        # 更新订单状态为已发货
        logger.info(f"【{self.cookie_id}】检查自动发货订单状态处理器: handler_exists={self.order_status_handler is not None}")
        if self.order_status_handler:
            logger.info(f"【{self.cookie_id}】准备调用订单状态处理器.handle_auto_delivery_order_status: {order_id}")
            try:
                success = self.order_status_handler.handle_auto_delivery_order_status(
                    order_id=order_id,
                    cookie_id=self.cookie_id,
                    context="自动发货完成"
                )
                logger.info(f"【{self.cookie_id}】订单状态处理器.handle_auto_delivery_order_status返回结果: {success}")
                if success:
                    logger.info(f"【{self.cookie_id}】订单 {order_id} 状态已更新为已发货")
                else:
                    logger.warning(f"【{self.cookie_id}】订单 {order_id} 状态更新为已发货失败")
            except Exception as e:
                logger.error(f"【{self.cookie_id}】订单状态更新失败: {self._safe_str(e)}")
                import traceback
                logger.error(f"【{self.cookie_id}】详细错误信息: {traceback.format_exc()}")
        else:
            logger.warning(f"【{self.cookie_id}】订单状态处理器为None，跳过自动发货状态更新: {order_id}")

    def _is_auto_delivery_trigger(self, message: str) -> bool:
        """检查消息是否为自动发货触发关键字"""
        # 定义所有自动发货触发关键字
        auto_delivery_keywords = [
            # 系统消息
            '[我已付款，等待你发货]',
            '[已付款，待发货]',
            '我已付款，等待你发货',
            '[记得及时发货]',
        ]

        # 检查消息是否包含任何触发关键字
        for keyword in auto_delivery_keywords:
            if keyword in message:
                return True

        return False

    def _extract_order_id(self, message: dict) -> str:
        """从消息中提取订单ID"""
        try:
            order_id = None

            # 先查看消息的完整结构
            logger.warning(f"【{self.cookie_id}】🔍 完整消息结构: {message}")

            # 检查message['1']的结构，处理可能是列表、字典或字符串的情况
            message_1 = message.get('1', {})
            content_json_str = ''

            if isinstance(message_1, dict):
                logger.warning(f"【{self.cookie_id}】🔍 message['1'] 是字典，keys: {list(message_1.keys())}")

                # 检查message['1']['6']的结构
                message_1_6 = message_1.get('6', {})
                if isinstance(message_1_6, dict):
                    logger.warning(f"【{self.cookie_id}】🔍 message['1']['6'] 是字典，keys: {list(message_1_6.keys())}")
                    # 方法1: 从button的targetUrl中提取orderId
                    content_json_str = message_1_6.get('3', {}).get('5', '') if isinstance(message_1_6.get('3', {}), dict) else ''
                else:
                    logger.warning(f"【{self.cookie_id}】🔍 message['1']['6'] 不是字典: {type(message_1_6)}")

            elif isinstance(message_1, list):
                logger.warning(f"【{self.cookie_id}】🔍 message['1'] 是列表，长度: {len(message_1)}")
                # 如果message['1']是列表，跳过这种提取方式

            elif isinstance(message_1, str):
                logger.warning(f"【{self.cookie_id}】🔍 message['1'] 是字符串，长度: {len(message_1)}")
                # 如果message['1']是字符串，跳过这种提取方式

            else:
                logger.warning(f"【{self.cookie_id}】🔍 message['1'] 未知类型: {type(message_1)}")
                # 其他类型，跳过这种提取方式

            if content_json_str:
                try:
                    content_data = json.loads(content_json_str)

                    # 方法1a: 从button的targetUrl中提取orderId
                    target_url = content_data.get('dxCard', {}).get('item', {}).get('main', {}).get('exContent', {}).get('button', {}).get('targetUrl', '')
                    if target_url:
                        # 从URL中提取orderId参数
                        order_match = re.search(r'orderId=(\d+)', target_url)
                        if order_match:
                            order_id = order_match.group(1)
                            logger.info(f'【{self.cookie_id}】✅ 从button提取到订单ID: {order_id}')

                    # 方法1b: 从main的targetUrl中提取order_detail的id
                    if not order_id:
                        main_target_url = content_data.get('dxCard', {}).get('item', {}).get('main', {}).get('targetUrl', '')
                        if main_target_url:
                            order_match = re.search(r'order_detail\?id=(\d+)', main_target_url)
                            if order_match:
                                order_id = order_match.group(1)
                                logger.info(f'【{self.cookie_id}】✅ 从main targetUrl提取到订单ID: {order_id}')

                except Exception as parse_e:
                    logger.warning(f"解析内容JSON失败: {parse_e}")

            # 方法2: 从dynamicOperation中的order_detail URL提取orderId
            if not order_id and content_json_str:
                try:
                    content_data = json.loads(content_json_str)
                    dynamic_target_url = content_data.get('dynamicOperation', {}).get('changeContent', {}).get('dxCard', {}).get('item', {}).get('main', {}).get('exContent', {}).get('button', {}).get('targetUrl', '')
                    if dynamic_target_url:
                        # 从order_detail URL中提取id参数
                        order_match = re.search(r'order_detail\?id=(\d+)', dynamic_target_url)
                        if order_match:
                            order_id = order_match.group(1)
                            logger.info(f'【{self.cookie_id}】✅ 从order_detail提取到订单ID: {order_id}')
                except Exception as parse_e:
                    logger.warning(f"解析dynamicOperation JSON失败: {parse_e}")

            # 方法3: 如果前面的方法都失败，尝试在整个消息中搜索订单ID模式
            if not order_id:
                try:
                    # 将整个消息转换为字符串进行搜索
                    message_str = str(message)

                    # 搜索各种可能的订单ID模式
                    patterns = [
                        r'orderId[=:](\d{10,})',  # orderId=123456789 或 orderId:123456789
                        r'order_detail\?id=(\d{10,})',  # order_detail?id=123456789
                        r'"id"\s*:\s*"?(\d{10,})"?',  # "id":"123456789" 或 "id":123456789
                        r'bizOrderId[=:](\d{10,})',  # bizOrderId=123456789
                    ]

                    for pattern in patterns:
                        matches = re.findall(pattern, message_str)
                        if matches:
                            # 取第一个匹配的订单ID
                            order_id = matches[0]
                            logger.info(f'【{self.cookie_id}】✅ 从消息字符串中提取到订单ID: {order_id} (模式: {pattern})')
                            break

                except Exception as search_e:
                    logger.warning(f"在消息字符串中搜索订单ID失败: {search_e}")

            if order_id:
                logger.info(f'【{self.cookie_id}】🎯 最终提取到订单ID: {order_id}')
            else:
                logger.warning(f'【{self.cookie_id}】❌ 未能从消息中提取到订单ID')

            return order_id

        except Exception as e:
            logger.error(f"【{self.cookie_id}】提取订单ID失败: {self._safe_str(e)}")
            return None

    async def _handle_auto_delivery(self, websocket, message: dict, send_user_name: str, send_user_id: str,
                                   item_id: str, chat_id: str, msg_time: str):
        """统一处理自动发货逻辑"""
        try:
            if self._is_buyer_blacklisted(send_user_id):
                logger.warning(f'[{msg_time}] 【{self.cookie_id}】⚠️ 买家 {send_user_id} 在黑名单中，跳过自动发货')
                return
            # 检查商品是否属于当前cookies
            if item_id and item_id != "未知商品":
                try:
                    from db_manager import db_manager
                    item_info = db_manager.get_item_info(self.cookie_id, item_id)
                    if not item_info:
                        logger.warning(f'[{msg_time}] 【{self.cookie_id}】❌ 商品 {item_id} 不属于当前账号，跳过自动发货')
                        return
                    logger.warning(f'[{msg_time}] 【{self.cookie_id}】✅ 商品 {item_id} 归属验证通过')
                except Exception as e:
                    logger.error(f'[{msg_time}] 【{self.cookie_id}】检查商品归属失败: {self._safe_str(e)}，跳过自动发货')
                    return

            # 提取订单ID
            order_id = self._extract_order_id(message)

            # 如果order_id不存在，直接返回
            if not order_id:
                logger.warning(f'[{msg_time}] 【{self.cookie_id}】❌ 未能提取到订单ID，跳过自动发货')
                return

            # 订单ID已提取，将在自动发货时进行确认发货处理
            logger.info(f'[{msg_time}] 【{self.cookie_id}】提取到订单ID: {order_id}，将在自动发货时处理确认发货')

            # 使用订单ID作为锁的键
            lock_key = order_id

            # 第一重检查：延迟锁状态（在获取锁之前检查，避免不必要的等待）
            if self.is_lock_held(lock_key):
                logger.info(f'[{msg_time}] 【{self.cookie_id}】🔒【提前检查】订单 {lock_key} 延迟锁仍在持有状态，跳过发货')
                return

            # 第二重检查：基于时间的冷却机制
            if not self.can_auto_delivery(order_id):
                logger.info(f'[{msg_time}] 【{self.cookie_id}】订单 {order_id} 在冷却期内，跳过发货')
                return

            # 获取或创建该订单的锁
            order_lock = self._order_locks[lock_key]

            # 更新锁的使用时间
            self._lock_usage_times[lock_key] = time.time()

            # 使用异步锁防止同一订单的并发处理
            async with order_lock:
                logger.info(f'[{msg_time}] 【{self.cookie_id}】获取订单锁成功: {lock_key}，开始处理自动发货')

                # 第三重检查：获取锁后再次检查延迟锁状态（双重检查，防止在等待锁期间状态发生变化）
                if self.is_lock_held(lock_key):
                    logger.info(f'[{msg_time}] 【{self.cookie_id}】订单 {lock_key} 在获取锁后检查发现延迟锁仍持有，跳过发货')
                    return

                # 第四重检查：获取锁后再次检查冷却状态
                if not self.can_auto_delivery(order_id):
                    logger.info(f'[{msg_time}] 【{self.cookie_id}】订单 {order_id} 在获取锁后检查发现仍在冷却期，跳过发货')
                    return

                # 构造用户URL
                user_url = f'https://www.goofish.com/personal?userId={send_user_id}'

                # 自动发货逻辑
                try:
                    # 设置默认标题（将通过API获取真实商品信息）
                    item_title = "待获取商品信息"

                    logger.info(f"【{self.cookie_id}】准备自动发货: item_id={item_id}, item_title={item_title}")

                    # 检查是否需要多数量发货
                    from db_manager import db_manager
                    quantity_to_send = 1  # 默认发送1个

                    # 检查商品是否开启了多数量发货
                    multi_quantity_delivery = db_manager.get_item_multi_quantity_delivery_status(self.cookie_id, item_id)

                    if multi_quantity_delivery and order_id:
                        logger.info(f"商品 {item_id} 开启了多数量发货，获取订单详情...")
                        try:
                            # 使用现有方法获取订单详情
                            order_detail = await self.fetch_order_detail_info(order_id, item_id, send_user_id)
                            if order_detail and order_detail.get('quantity'):
                                try:
                                    order_quantity = int(order_detail['quantity'])
                                    if order_quantity > 1:
                                        quantity_to_send = order_quantity
                                        logger.info(f"从订单详情获取数量: {order_quantity}，将发送 {quantity_to_send} 个卡券")
                                    else:
                                        logger.info(f"订单数量为 {order_quantity}，发送单个卡券")
                                except (ValueError, TypeError):
                                    logger.warning(f"订单数量格式无效: {order_detail.get('quantity')}，发送单个卡券")
                            else:
                                logger.info(f"未获取到订单数量信息，发送单个卡券")
                        except Exception as e:
                            logger.error(f"获取订单详情失败: {self._safe_str(e)}，发送单个卡券")
                    elif not multi_quantity_delivery:
                        logger.info(f"商品 {item_id} 未开启多数量发货，发送单个卡券")
                    else:
                        logger.info(f"无订单ID，发送单个卡券")

                    # 检查每日发货配额
                    try:
                        from db_manager import db_manager as _dbm
                        allowed, count, limit = _dbm.check_daily_quota(self.cookie_id, 'delivery')
                        if not allowed:
                            logger.warning(f"【{self.cookie_id}】今日自动发货已达上限 ({count}/{limit})，跳过发货")
                            await self.send_delivery_failure_notification(send_user_name, send_user_id, item_id, f"今日发货已达上限({count}/{limit})", chat_id)
                            return
                        _dbm.increment_daily_quota(self.cookie_id, 'delivery')
                    except Exception as qe:
                        logger.error(f"【{self.cookie_id}】配额检查异常: {self._safe_str(qe)}")

                    # 多次调用自动发货方法，每次获取不同的内容
                    delivery_contents = []
                    success_count = 0

                    for i in range(quantity_to_send):
                        try:
                            # 每次调用都可能获取不同的内容（API卡券、批量数据等）
                            delivery_content = await self._auto_delivery(item_id, item_title, order_id, send_user_id)
                            if delivery_content:
                                delivery_contents.append(delivery_content)
                                success_count += 1
                                if quantity_to_send > 1:
                                    logger.info(f"第 {i+1}/{quantity_to_send} 个卡券内容获取成功")
                            else:
                                logger.warning(f"第 {i+1}/{quantity_to_send} 个卡券内容获取失败")
                        except Exception as e:
                            logger.error(f"第 {i+1}/{quantity_to_send} 个卡券获取异常: {self._safe_str(e)}")

                    if delivery_contents:
                        # 标记已发货（防重复）- 基于订单ID
                        self.mark_delivery_sent(order_id)

                        # 更新订单数据库，标记系统已发货
                        if order_id:
                            try:
                                from db_manager import db_manager
                                db_manager.insert_or_update_order(
                                    order_id=order_id,
                                    system_shipped=True,
                                    chat_id=chat_id
                                )
                                logger.info(f'【{self.cookie_id}】✅ 订单 {order_id} 已标记为系统已发货 (system_shipped=1)')
                            except Exception as db_e:
                                logger.error(f'【{self.cookie_id}】❌ 更新订单system_shipped状态失败: {self._safe_str(db_e)}')

                        # 标记锁为持有状态，并启动延迟释放任务
                        self._lock_hold_info[lock_key] = {
                            'locked': True,
                            'lock_time': time.time(),
                            'release_time': None,
                            'task': None
                        }

                        # 启动延迟释放锁的异步任务（10分钟后释放）
                        delay_task = asyncio.create_task(self._delayed_lock_release(lock_key, delay_minutes=10))
                        self._lock_hold_info[lock_key]['task'] = delay_task

                        # 发送所有获取到的发货内容
                        for i, delivery_content in enumerate(delivery_contents):
                            try:
                                # 检查是否是图片发送标记
                                if delivery_content.startswith("__IMAGE_SEND__"):
                                    # 提取卡券ID和图片URL
                                    image_data = delivery_content.replace("__IMAGE_SEND__", "")
                                    if "|" in image_data:
                                        card_id_str, image_url = image_data.split("|", 1)
                                        try:
                                            card_id = int(card_id_str)
                                        except ValueError:
                                            logger.error(f"无效的卡券ID: {card_id_str}")
                                            card_id = None
                                    else:
                                        # 兼容旧格式（没有卡券ID）
                                        card_id = None
                                        image_url = image_data

                                    # 发送图片消息
                                    await self.send_image_msg(websocket, chat_id, send_user_id, image_url, card_id=card_id)
                                    if len(delivery_contents) > 1:
                                        logger.info(f'[{msg_time}] 【多数量自动发货图片】第 {i+1}/{len(delivery_contents)} 张已向 {user_url} 发送图片: {image_url}')
                                    else:
                                        logger.info(f'[{msg_time}] 【自动发货图片】已向 {user_url} 发送图片: {image_url}')

                                    # 多数量发货时，消息间隔1秒
                                    if len(delivery_contents) > 1 and i < len(delivery_contents) - 1:
                                        await asyncio.sleep(self._random_delay(1.0, 0.3))

                                else:
                                    # 普通文本发货内容
                                    await self.send_msg(websocket, chat_id, send_user_id, delivery_content)
                                    if len(delivery_contents) > 1:
                                        logger.info(f'[{msg_time}] 【多数量自动发货】第 {i+1}/{len(delivery_contents)} 条已向 {user_url} 发送发货内容')
                                    else:
                                        logger.info(f'[{msg_time}] 【自动发货】已向 {user_url} 发送发货内容')

                                    # 多数量发货时，消息间隔1秒
                                    if len(delivery_contents) > 1 and i < len(delivery_contents) - 1:
                                        await asyncio.sleep(self._random_delay(1.0, 0.3))

                            except Exception as e:
                                logger.error(f"发送第 {i+1} 条消息失败: {self._safe_str(e)}")

                        # 发送成功通知
                        if len(delivery_contents) > 1:
                            await self.send_delivery_failure_notification(send_user_name, send_user_id, item_id, f"多数量发货成功，共发送 {len(delivery_contents)} 个卡券", chat_id)
                        else:
                            await self.send_delivery_failure_notification(send_user_name, send_user_id, item_id, "发货成功", chat_id)
                    else:
                        logger.warning(f'[{msg_time}] 【自动发货】未找到匹配的发货规则或获取发货内容失败')
                        # 发送自动发货失败通知
                        await self.send_delivery_failure_notification(send_user_name, send_user_id, item_id, "未找到匹配的发货规则或获取发货内容失败", chat_id)
                        # 加入发货重试队列
                        try:
                            from db_manager import db_manager
                            db_manager.add_delivery_retry(
                                cookie_id=self.cookie_id, order_id=order_id, item_id=item_id,
                                buyer_id=send_user_id, buyer_name=send_user_name, chat_id=chat_id,
                                quantity=quantity_to_send, error_type='no_match',
                                error_message='未找到匹配的发货规则或获取发货内容失败'
                            )
                        except Exception as retry_e:
                            logger.error(f"加入发货重试队列失败: {self._safe_str(retry_e)}")

                except Exception as e:
                    logger.error(f"自动发货处理异常: {self._safe_str(e)}")
                    # 发送自动发货异常通知
                    await self.send_delivery_failure_notification(send_user_name, send_user_id, item_id, f"自动发货处理异常: {str(e)}", chat_id)
                    # 加入发货重试队列
                    try:
                        from db_manager import db_manager
                        db_manager.add_delivery_retry(
                            cookie_id=self.cookie_id, order_id=order_id, item_id=item_id,
                            buyer_id=send_user_id, buyer_name=send_user_name, chat_id=chat_id,
                            quantity=quantity_to_send, error_type='exception',
                            error_message=str(e)[:500]
                        )
                    except Exception as retry_e:
                        logger.error(f"加入发货重试队列失败: {self._safe_str(retry_e)}")

                logger.info(f'[{msg_time}] 【{self.cookie_id}】订单锁释放: {lock_key}，自动发货处理完成')

        except Exception as e:
            logger.error(f"统一自动发货处理异常: {self._safe_str(e)}")



    async def delivery_retry_loop(self):
        """发货失败重试循环 - 定期检查重试队列并重试"""
        logger.info(f"【{self.cookie_id}】发货重试循环已启动")
        retry_interval = 300  # 5分钟检查一次
        
        while self._running:
            try:
                await asyncio.sleep(self._randomize_interval(retry_interval, 0.2))
                if not self._running:
                    break
                
                from db_manager import db_manager
                pending_retries = db_manager.get_pending_delivery_retries()
                cookie_retries = [r for r in pending_retries if r.get('cookie_id') == self.cookie_id]
                
                if not cookie_retries:
                    continue
                
                logger.info(f"【{self.cookie_id}】发现 {len(cookie_retries)} 条待重试发货记录")
                
                for retry in cookie_retries:
                    retry_id = retry.get('id')
                    retry_count = retry.get('retry_count', 0)
                    max_retries = retry.get('max_retries', 5)
                    order_id = retry.get('order_id')
                    item_id = retry.get('item_id')
                    send_user_id = retry.get('buyer_id')
                    send_user_name = retry.get('buyer_name', '')
                    chat_id = retry.get('chat_id', '')
                    quantity = retry.get('quantity', 1)
                    
                    if retry_count >= max_retries:
                        db_manager.update_delivery_retry_status(
                            retry_id, 'failed', f'已重试 {retry_count} 次，超过上限',
                            increment_retry=False, delay_minutes=0
                        )
                        await self.send_delivery_failure_notification(
                            send_user_name, send_user_id, item_id,
                            f"发货重试失败（已达上限 {max_retries} 次）", chat_id
                        )
                        continue
                    
                    try:
                        db_manager.update_delivery_retry_status(
                            retry_id, 'retrying', '正在重试...',
                            increment_retry=False, delay_minutes=5
                        )
                        
                        delivery_contents = []
                        for i in range(quantity):
                            try:
                                content = await self._auto_delivery(item_id, None, order_id, send_user_id)
                                if content:
                                    delivery_contents.append(content)
                            except Exception as inner_e:
                                logger.warning(f"重试发货第 {i+1}/{quantity} 个卡券失败: {self._safe_str(inner_e)}")
                        
                        if delivery_contents and self.websocket:
                            # 有WebSocket连接直接发送
                            for content in delivery_contents:
                                if content.startswith('__IMAGE_SEND__'):
                                    image_data = content.replace('__IMAGE_SEND__', '')
                                    if '|' in image_data:
                                        card_id_str, image_url = image_data.split('|', 1)
                                        try:
                                            await self.send_image_msg(self.websocket, chat_id, send_user_id, image_url, card_id=int(card_id_str))
                                        except:
                                            await self.send_image_msg(self.websocket, chat_id, send_user_id, image_url)
                                    else:
                                        await self.send_image_msg(self.websocket, chat_id, send_user_id, image_data)
                                else:
                                    await self.send_msg(self.websocket, chat_id, send_user_id, content)
                                await asyncio.sleep(self._random_delay(0.5, 0.3))
                            
                            db_manager.update_delivery_retry_status(
                                retry_id, 'success', '重试发货成功',
                                increment_retry=False, delay_minutes=0
                            )
                            self.mark_delivery_sent(order_id)
                            await self.send_delivery_failure_notification(
                                send_user_name, send_user_id, item_id,
                                f"重试发货成功（第 {retry_count + 1} 次重试）", chat_id
                            )
                            logger.info(f"【{self.cookie_id}】🎉 重试发货成功: retry_id={retry_id}, order={order_id}")
                        else:
                            error_msg = '获取发货内容失败' if not delivery_contents else 'WebSocket未连接，延迟重试'
                            retry_delay = 30 if self.websocket else 5
                            db_manager.update_delivery_retry_status(
                                retry_id, 'pending', error_msg,
                                increment_retry=True, delay_minutes=retry_delay
                            )
                            logger.warning(f"【{self.cookie_id}】重试发货失败: {error_msg}, retry_id={retry_id}")
                            
                    except Exception as retry_e:
                        db_manager.update_delivery_retry_status(
                            retry_id, 'pending', str(retry_e)[:500],
                            increment_retry=True, delay_minutes=10
                        )
                        logger.error(f"【{self.cookie_id}】重试发货异常: {self._safe_str(retry_e)}")
                
            except asyncio.CancelledError:
                logger.info(f"【{self.cookie_id}】发货重试循环被取消")
                break
            except Exception as e:
                logger.error(f"【{self.cookie_id}】发货重试循环异常: {self._safe_str(e)}")
                await asyncio.sleep(self._randomize_interval(60, 0.2))
        
        logger.info(f"【{self.cookie_id}】发货重试循环已停止")

    async def send_delivery_failure_notification(self, send_user_name: str, send_user_id: str, item_id: str, error_message: str, chat_id: str = None):
        """发送自动发货失败通知"""
        try:
            from db_manager import db_manager

            # 获取当前账号的通知配置
            notifications = db_manager.get_account_notifications(self.cookie_id)

            if not notifications:
                logger.warning("未配置消息通知，跳过自动发货通知")
                return

            # 构造通知消息
            notification_message = f"🚨 自动发货通知\n\n" \
                                 f"账号: {self.cookie_id}\n" \
                                 f"买家: {send_user_name} (ID: {send_user_id})\n" \
                                 f"商品ID: {item_id}\n" \
                                 f"聊天ID: {chat_id or '未知'}\n" \
                                 f"结果: {error_message}\n" \
                                 f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n" \
                                 f"请及时处理！"

            # 发送通知到所有已启用的通知渠道
            for notification in notifications:
                if notification.get('enabled', False):
                    channel_type = notification.get('channel_type', 'qq')
                    channel_config = notification.get('channel_config', '')

                    try:
                        # 解析配置数据
                        config_data = self._parse_notification_config(channel_config)

                        match channel_type:
                            case 'ding_talk' | 'dingtalk':
                                await self._send_dingtalk_notification(config_data, notification_message)
                                logger.info(f"已发送自动发货通知到钉钉")
                            case 'email':
                                await self._send_email_notification(config_data, notification_message)
                                logger.info(f"已发送自动发货通知到邮箱")
                            case 'webhook':
                                await self._send_webhook_notification(config_data, notification_message)
                                logger.info(f"已发送自动发货通知到Webhook")
                            case 'wechat':
                                await self._send_wechat_notification(config_data, notification_message)
                                logger.info(f"已发送自动发货通知到微信")
                            case 'telegram':
                                await self._send_telegram_notification(config_data, notification_message)
                                logger.info(f"已发送自动发货通知到Telegram")
                            case 'bark':
                                await self._send_bark_notification(config_data, notification_message)
                                logger.info(f"已发送自动发货通知到Bark")
                            case 'feishu' | 'lark':
                                await self._send_feishu_notification(config_data, notification_message)
                                logger.info(f"已发送自动发货通知到飞书")
                            case _:
                                logger.warning(f"不支持的通知渠道类型: {channel_type}")

                    except Exception as notify_error:
                        logger.error(f"发送自动发货通知失败: {self._safe_str(notify_error)}")

        except Exception as e:
            logger.error(f"发送自动发货通知异常: {self._safe_str(e)}")

    async def auto_freeshipping(self, order_id, item_id, buyer_id, retry_count=0):
        """自动免拼发货 - 使用解密模块"""
        try:
            logger.warning(f"【{self.cookie_id}】开始免拼发货，订单ID: {order_id}")

            # 导入解密后的免拼发货模块
            from secure_freeshipping_decrypted import SecureFreeshipping

            # 创建免拼发货实例
            secure_freeshipping = SecureFreeshipping(self.session, self.cookies_str, self.cookie_id)

            # 传递必要的属性
            secure_freeshipping.current_token = self.current_token
            secure_freeshipping.last_token_refresh_time = self.last_token_refresh_time
            secure_freeshipping.token_refresh_interval = self.token_refresh_interval

            # 调用免拼发货方法
            return await secure_freeshipping.auto_freeshipping(order_id, item_id, buyer_id, retry_count)

        except Exception as e:
            logger.error(f"【{self.cookie_id}】免拼发货模块调用失败: {self._safe_str(e)}")
            return {"error": f"免拼发货模块调用失败: {self._safe_str(e)}", "order_id": order_id}

    async def fetch_order_detail_info(self, order_id: str, item_id: str = None, buyer_id: str = None, debug_headless: bool = None):
        """获取订单详情信息（使用独立的锁机制，不受延迟锁影响）"""
        # 使用独立的订单详情锁，不与自动发货锁冲突
        order_detail_lock = self._order_detail_locks[order_id]

        # 记录订单详情锁的使用时间
        self._order_detail_lock_times[order_id] = time.time()

        async with order_detail_lock:
            logger.info(f"🔍 【{self.cookie_id}】获取订单详情锁 {order_id}，开始处理...")
            
            try:
                logger.info(f"【{self.cookie_id}】开始获取订单详情: {order_id}")

                # 导入订单详情获取器
                from utils.order_detail_fetcher import fetch_order_detail_simple
                from db_manager import db_manager

                # 获取当前账号的cookie字符串
                cookie_string = self.cookies_str
                logger.warning(f"【{self.cookie_id}】使用Cookie长度: {len(cookie_string) if cookie_string else 0}")

                # 确定是否使用有头模式（调试用）
                headless_mode = True if debug_headless is None else debug_headless
                if not headless_mode:
                    logger.info(f"【{self.cookie_id}】🖥️ 启用有头模式进行调试")

                # 异步获取订单详情（使用当前账号的cookie）
                result = await fetch_order_detail_simple(order_id, cookie_string, headless=headless_mode)

                if result:
                    logger.info(f"【{self.cookie_id}】订单详情获取成功: {order_id}")
                    logger.info(f"【{self.cookie_id}】页面标题: {result.get('title', '未知')}")

                    # 获取解析后的规格信息
                    spec_name = result.get('spec_name', '')
                    spec_value = result.get('spec_value', '')
                    quantity = result.get('quantity', '')
                    amount = result.get('amount', '')

                    # 获取订单时间和收货人信息
                    order_time = result.get('order_time', None)
                    receiver_name = result.get('receiver_name', None)
                    receiver_phone = result.get('receiver_phone', None)
                    receiver_address = result.get('receiver_address', None)

                    if spec_name and spec_value:
                        logger.info(f"【{self.cookie_id}】📋 规格名称: {spec_name}")
                        logger.info(f"【{self.cookie_id}】📝 规格值: {spec_value}")
                        print(f"🛍️ 【{self.cookie_id}】订单 {order_id} 规格信息: {spec_name} -> {spec_value}")
                    else:
                        logger.warning(f"【{self.cookie_id}】未获取到有效的规格信息")
                        print(f"⚠️ 【{self.cookie_id}】订单 {order_id} 规格信息获取失败")

                    # 记录订单时间和收货人信息
                    if order_time:
                        logger.info(f"【{self.cookie_id}】⏰ 订单时间: {order_time}")
                    if receiver_name:
                        logger.info(f"【{self.cookie_id}】👤 收货人: {receiver_name}")
                    if receiver_phone:
                        logger.info(f"【{self.cookie_id}】📱 手机号: {receiver_phone}")
                    if receiver_address:
                        logger.info(f"【{self.cookie_id}】📍 收货地址: {receiver_address}")

                    # 插入或更新订单信息到数据库
                    try:
                        # 检查cookie_id是否在cookies表中存在
                        cookie_info = db_manager.get_cookie_by_id(self.cookie_id)
                        if not cookie_info:
                            logger.warning(f"Cookie ID {self.cookie_id} 不存在于cookies表中，丢弃订单 {order_id}")
                        else:
                            # 先保存订单基本信息（包含时间和收货人信息）
                            success = db_manager.insert_or_update_order(
                                order_id=order_id,
                                item_id=item_id,
                                buyer_id=buyer_id,
                                spec_name=spec_name,
                                spec_value=spec_value,
                                quantity=quantity,
                                amount=amount,
                                order_status=result.get('order_status'),  # 添加订单状态
                                cookie_id=self.cookie_id,
                                created_at=order_time,
                                receiver_name=receiver_name,
                                receiver_phone=receiver_phone,
                                receiver_address=receiver_address
                            )
                            
                            # 使用订单状态处理器设置状态
                            logger.info(f"【{self.cookie_id}】检查订单状态处理器调用条件: success={success}, handler_exists={self.order_status_handler is not None}")
                            if success and self.order_status_handler:
                                logger.info(f"【{self.cookie_id}】准备调用订单状态处理器.handle_order_detail_fetched_status: {order_id}")
                                try:
                                    handler_result = self.order_status_handler.handle_order_detail_fetched_status(
                                        order_id=order_id,
                                        cookie_id=self.cookie_id,
                                        context="订单详情已拉取"
                                    )
                                    logger.info(f"【{self.cookie_id}】订单状态处理器.handle_order_detail_fetched_status返回结果: {handler_result}")
                                    
                                    # 处理待处理队列
                                    logger.info(f"【{self.cookie_id}】准备调用订单状态处理器.on_order_details_fetched: {order_id}")
                                    self.order_status_handler.on_order_details_fetched(order_id)
                                    logger.info(f"【{self.cookie_id}】订单状态处理器.on_order_details_fetched调用成功: {order_id}")
                                except Exception as e:
                                    logger.error(f"【{self.cookie_id}】订单状态处理器调用失败: {self._safe_str(e)}")
                                    import traceback
                                    logger.error(f"【{self.cookie_id}】详细错误信息: {traceback.format_exc()}")
                            else:
                                logger.warning(f"【{self.cookie_id}】订单状态处理器调用条件不满足: success={success}, handler_exists={self.order_status_handler is not None}")

                            if success:
                                logger.info(f"【{self.cookie_id}】订单信息已保存到数据库: {order_id}")
                                print(f"💾 【{self.cookie_id}】订单 {order_id} 信息已保存到数据库")
                            else:
                                logger.warning(f"【{self.cookie_id}】订单信息保存失败: {order_id}")

                    except Exception as db_e:
                        logger.error(f"【{self.cookie_id}】保存订单信息到数据库失败: {self._safe_str(db_e)}")

                    return result
                else:
                    logger.warning(f"【{self.cookie_id}】订单详情获取失败: {order_id}")
                    return None

            except Exception as e:
                logger.error(f"【{self.cookie_id}】获取订单详情异常: {self._safe_str(e)}")
                return None

    async def _auto_delivery(self, item_id: str, item_title: str = None, order_id: str = None, send_user_id: str = None):
        """自动发货功能 - 获取卡券规则，执行延时，确认发货，发送内容"""
        try:
            from db_manager import db_manager

            logger.info(f"开始自动发货检查: 商品ID={item_id}")

            # 获取商品详细信息
            item_info = None
            search_text = item_title  # 默认使用传入的标题

            if item_id and item_id != "未知商品":
                # 直接从数据库获取商品信息（发货时不再调用API）
                try:
                    logger.info(f"从数据库获取商品信息: {item_id}")
                    db_item_info = db_manager.get_item_info(self.cookie_id, item_id)
                    if db_item_info:
                        # 拼接商品标题和详情作为搜索文本
                        item_title_db = db_item_info.get('item_title', '') or ''
                        item_detail_db = db_item_info.get('item_detail', '') or ''

                        # 如果数据库中没有详情，尝试自动获取
                        if not item_detail_db.strip():
                            from config import config
                            auto_fetch_config = config.get('ITEM_DETAIL', {}).get('auto_fetch', {})

                            if auto_fetch_config.get('enabled', True):
                                logger.info(f"数据库中商品详情为空，尝试自动获取: {item_id}")
                                try:
                                    fetched_detail = await self.fetch_item_detail_from_api(item_id)
                                    if fetched_detail:
                                        # 保存获取到的详情
                                        await self.save_item_detail_only(item_id, fetched_detail)
                                        item_detail_db = fetched_detail
                                        logger.info(f"成功获取并保存商品详情: {item_id}")
                                    else:
                                        logger.warning(f"未能获取到商品详情: {item_id}")
                                except Exception as api_e:
                                    logger.warning(f"获取商品详情失败: {item_id}, 错误: {self._safe_str(api_e)}")
                            else:
                                logger.warning(f"自动获取商品详情功能已禁用，跳过: {item_id}")

                        # 组合搜索文本：商品标题 + 商品详情
                        search_parts = []
                        if item_title_db.strip():
                            search_parts.append(item_title_db.strip())
                        if item_detail_db.strip():
                            search_parts.append(item_detail_db.strip())

                        if search_parts:
                            search_text = ' '.join(search_parts)
                            logger.info(f"使用数据库商品标题+详情作为搜索文本: 标题='{item_title_db}', 详情长度={len(item_detail_db)}")
                            logger.warning(f"完整搜索文本: {search_text[:200]}...")
                        else:
                            logger.warning(f"数据库中商品标题和详情都为空: {item_id}")
                            search_text = item_title or item_id
                    else:
                        logger.warning(f"数据库中未找到商品信息: {item_id}")
                        search_text = item_title or item_id

                except Exception as db_e:
                    logger.warning(f"从数据库获取商品信息失败: {self._safe_str(db_e)}")
                    search_text = item_title or item_id

            if not search_text:
                search_text = item_id or "未知商品"

            logger.info(f"使用搜索文本匹配发货规则: {search_text[:100]}...")

            # 检查商品是否为多规格商品
            is_multi_spec = db_manager.get_item_multi_spec_status(self.cookie_id, item_id)
            spec_name = None
            spec_value = None

            # 如果是多规格商品且有订单ID，获取规格信息
            if is_multi_spec and order_id:
                logger.info(f"检测到多规格商品，获取订单规格信息: {order_id}")
                try:
                    order_detail = await self.fetch_order_detail_info(order_id, item_id, send_user_id)
                    # 确保order_detail是字典类型
                    if order_detail and isinstance(order_detail, dict):
                        spec_name = order_detail.get('spec_name', '')
                        spec_value = order_detail.get('spec_value', '')
                        if spec_name and spec_value:
                            logger.info(f"获取到规格信息: {spec_name} = {spec_value}")
                        else:
                            logger.warning(f"未能获取到规格信息，将跳过自动发货")
                            return None
                    else:
                        logger.warning(f"获取订单详情失败（返回类型: {type(order_detail).__name__}），将跳过自动发货")
                        return None
                except Exception as e:
                    logger.error(f"获取订单规格信息失败: {self._safe_str(e)}，将跳过自动发货")
                    return None

            # 智能匹配发货规则：多规格商品只匹配多规格卡券，非多规格商品只匹配非多规格卡券
            delivery_rules = []

            if is_multi_spec:
                # 多规格商品：只匹配多规格发货规则
                if spec_name and spec_value:
                    logger.info(f"多规格商品，尝试匹配多规格发货规则: {search_text[:50]}... [{spec_name}:{spec_value}]")
                    delivery_rules = db_manager.get_delivery_rules_by_keyword_and_spec(search_text, spec_name, spec_value)
                    # 过滤只保留多规格卡券
                    delivery_rules = [r for r in delivery_rules if r.get('is_multi_spec')]
                    
                    if delivery_rules:
                        logger.info(f"✅ 找到匹配的多规格发货规则: {len(delivery_rules)}个")
                    else:
                        logger.warning(f"❌ 多规格商品未找到匹配的多规格发货规则，跳过自动发货")
                        return None
                else:
                    logger.warning(f"❌ 多规格商品但无规格信息，跳过自动发货")
                    return None
            else:
                # 非多规格商品：只匹配非多规格发货规则
                logger.info(f"非多规格商品，尝试匹配普通发货规则: {search_text[:50]}...")
                delivery_rules = db_manager.get_delivery_rules_by_keyword(search_text)
                # 过滤只保留非多规格卡券
                delivery_rules = [r for r in delivery_rules if not r.get('is_multi_spec')]
                
                if delivery_rules:
                    logger.info(f"✅ 找到匹配的普通发货规则: {len(delivery_rules)}个")
                else:
                    logger.warning(f"❌ 非多规格商品未找到匹配的普通发货规则，跳过自动发货")
                    return None

            # 检查匹配到的卡券数量，只有唯一匹配时才自动发货
            if len(delivery_rules) > 1:
                rule_names = [f"{r['card_name']}({r.get('spec_name', '')}:{r.get('spec_value', '')})" if r.get('is_multi_spec') else r['card_name'] for r in delivery_rules]
                logger.warning(f"❌ 匹配到多个发货规则({len(delivery_rules)}个)，无法确定使用哪个，跳过自动发货: {', '.join(rule_names)}")
                return None

            if not delivery_rules:
                logger.warning(f"未找到匹配的发货规则: {search_text[:50]}...")
                return None

            # 使用唯一匹配的规则
            rule = delivery_rules[0]
            logger.info(f"✅ 唯一匹配发货规则: {rule['keyword']} -> {rule['card_name']} ({rule['card_type']})")

            # 保存商品信息到数据库（需要有商品标题才保存）
            # 尝试获取商品标题
            item_title_for_save = None
            try:
                from db_manager import db_manager
                db_item_info = db_manager.get_item_info(self.cookie_id, item_id)
                if db_item_info:
                    item_title_for_save = db_item_info.get('item_title', '').strip()
            except:
                pass

            # 如果有商品标题，则保存商品信息
            if item_title_for_save:
                await self.save_item_info_to_db(item_id, search_text, item_title_for_save)
            else:
                logger.warning(f"跳过保存商品信息：缺少商品标题 - {item_id}")

            # 详细的匹配结果日志
            if rule.get('is_multi_spec'):
                if spec_name and spec_value:
                    logger.info(f"🎯 精确匹配多规格发货规则: {rule['keyword']} -> {rule['card_name']} [{rule['spec_name']}:{rule['spec_value']}]")
                    logger.info(f"📋 订单规格: {spec_name}:{spec_value} ✅ 匹配卡券规格: {rule['spec_name']}:{rule['spec_value']}")
                else:
                    logger.info(f"⚠️ 使用多规格发货规则但无订单规格信息: {rule['keyword']} -> {rule['card_name']} [{rule['spec_name']}:{rule['spec_value']}]")
            else:
                if spec_name and spec_value:
                    logger.info(f"🔄 兜底匹配普通发货规则: {rule['keyword']} -> {rule['card_name']} ({rule['card_type']})")
                    logger.info(f"📋 订单规格: {spec_name}:{spec_value} ➡️ 使用普通卡券兜底")
                else:
                    logger.info(f"✅ 匹配普通发货规则: {rule['keyword']} -> {rule['card_name']} ({rule['card_type']})")

            # 获取延时设置
            delay_seconds = rule.get('card_delay_seconds', 0)

            # 执行延时（不管是否确认发货，只要有延时设置就执行）
            if delay_seconds and delay_seconds > 0:
                logger.info(f"检测到发货延时设置: {delay_seconds}秒，开始延时...")
                await asyncio.sleep(delay_seconds)
                logger.info(f"延时完成")

            # 如果有订单ID，执行确认发货
            if order_id:
                # 检查是否启用自动确认发货
                if not self.is_auto_confirm_enabled():
                    logger.info(f"自动确认发货已关闭，跳过订单 {order_id}")
                else:
                    # 检查确认发货冷却时间
                    current_time = time.time()
                    should_confirm = True

                    if order_id in self.confirmed_orders:
                        last_confirm_time = self.confirmed_orders[order_id]
                        if current_time - last_confirm_time < self.order_confirm_cooldown:
                            logger.info(f"订单 {order_id} 已在 {self.order_confirm_cooldown} 秒内确认过，跳过重复确认")
                            should_confirm = False

                    if should_confirm:
                        logger.info(f"开始自动确认发货: 订单ID={order_id}, 商品ID={item_id}")
                        confirm_result = await self.auto_confirm(order_id, item_id)
                        if confirm_result.get('success'):
                            self.confirmed_orders[order_id] = current_time
                            logger.info(f"🎉 自动确认发货成功！订单ID: {order_id}")
                        else:
                            logger.warning(f"⚠️ 自动确认发货失败: {confirm_result.get('error', '未知错误')}")
                            # 即使确认发货失败，也继续发送发货内容

            # 检查是否存在订单ID，只有存在订单ID才处理发货内容
            if order_id:
                # 保存订单基本信息到数据库（如果还没有详细信息）
                try:
                    from db_manager import db_manager

                    # 检查cookie_id是否在cookies表中存在
                    cookie_info = db_manager.get_cookie_by_id(self.cookie_id)
                    if not cookie_info:
                        logger.warning(f"Cookie ID {self.cookie_id} 不存在于cookies表中，丢弃订单 {order_id}")
                    else:
                        existing_order = db_manager.get_order_by_id(order_id)
                        if not existing_order:
                            # 插入基本订单信息
                            success = db_manager.insert_or_update_order(
                                order_id=order_id,
                                item_id=item_id,
                                buyer_id=send_user_id,
                                cookie_id=self.cookie_id
                            )
                            
                            # 使用订单状态处理器设置状态
                            if success and self.order_status_handler:
                                try:
                                    self.order_status_handler.handle_order_basic_info_status(
                                        order_id=order_id,
                                        cookie_id=self.cookie_id,
                                        context="自动发货-基本信息"
                                    )
                                except Exception as e:
                                    logger.error(f"【{self.cookie_id}】订单状态处理器调用失败: {self._safe_str(e)}")
                            
                            if success:
                                logger.info(f"保存基本订单信息到数据库: {order_id}")
                except Exception as db_e:
                    logger.error(f"保存基本订单信息失败: {self._safe_str(db_e)}")

                # 开始处理发货内容
                logger.info(f"开始处理发货内容，规则: {rule['keyword']} -> {rule['card_name']} ({rule['card_type']})")

                delivery_content = None

                # 根据卡券类型处理发货内容
                if rule['card_type'] == 'api':
                    # API类型：调用API获取内容，传入订单和商品信息用于动态参数替换
                    delivery_content = await self._get_api_card_content(rule, order_id, item_id, send_user_id, spec_name, spec_value)

                elif rule['card_type'] == 'text':
                    # 固定文字类型：直接使用文字内容
                    delivery_content = rule['text_content']

                elif rule['card_type'] == 'data':
                    # 批量数据类型：获取并消费第一条数据
                    delivery_content = db_manager.consume_batch_data(rule['card_id'])

                elif rule['card_type'] == 'image':
                    # 图片类型：返回图片发送标记，包含卡券ID
                    image_url = rule.get('image_url')
                    if image_url:
                        delivery_content = f"__IMAGE_SEND__{rule['card_id']}|{image_url}"
                        logger.info(f"准备发送图片: {image_url} (卡券ID: {rule['card_id']})")
                    else:
                        logger.error(f"图片卡券缺少图片URL: 卡券ID={rule['card_id']}")
                        delivery_content = None

                if delivery_content:
                    # 处理备注信息和变量替换
                    final_content = self._process_delivery_content_with_description(delivery_content, rule.get('card_description', ''))

                    # 增加发货次数统计
                    db_manager.increment_delivery_times(rule['id'])
                    logger.info(f"自动发货成功: 规则ID={rule['id']}, 内容长度={len(final_content)}")
                    return final_content
                else:
                    logger.warning(f"获取发货内容失败: 规则ID={rule['id']}")
                    return None
            else:
                # 没有订单ID，记录日志但不处理发货内容
                logger.info(f"⚠️ 未检测到订单ID，跳过发货内容处理。规则: {rule['keyword']} -> {rule['card_name']} ({rule['card_type']})")
                return None

        except Exception as e:
            logger.error(f"自动发货失败: {self._safe_str(e)}")
            return None



    def _process_delivery_content_with_description(self, delivery_content: str, card_description: str) -> str:
        """处理发货内容和备注信息，实现变量替换"""
        try:
            # 如果是图片发送标记，不进行备注处理，直接返回
            if delivery_content.startswith("__IMAGE_SEND__"):
                return delivery_content
            
            # 如果没有备注信息，直接返回发货内容
            if not card_description or not card_description.strip():
                return delivery_content

            # 替换备注中的变量
            processed_description = card_description.replace('{DELIVERY_CONTENT}', delivery_content)

            # 如果备注中包含变量替换，返回处理后的备注
            if '{DELIVERY_CONTENT}' in card_description:
                return processed_description
            else:
                # 如果备注中没有变量，将备注和发货内容组合
                return f"{processed_description}\n\n{delivery_content}"

        except Exception as e:
            logger.error(f"处理备注信息失败: {e}")
            # 出错时返回原始发货内容
            return delivery_content

