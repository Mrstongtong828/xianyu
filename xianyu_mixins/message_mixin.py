"""
消息处理
"""
import json
import time
import asyncio
import traceback
from typing import Optional, Dict, Any, List
from loguru import logger


class MessageMixin:
    """消息处理"""

    # Methods moved from XianyuLive
    def _extract_image_url_from_message(self, message_10: dict):
        """从消息中提取图片 URL，支持多种消息格式"""
        if not isinstance(message_10, dict):
            return None
        try:
            for field_key in ('reminderContent', 'content', 'image'):
                raw = message_10.get(field_key, '')
                if isinstance(raw, str) and raw.strip():
                    try:
                        parsed = json.loads(raw)
                        if isinstance(parsed, dict) and parsed.get('contentType') == 2:
                            pics = parsed.get('image', {}).get('pics', [])
                            if pics and isinstance(pics, list):
                                url = pics[0].get('url', '')
                                if url:
                                    return url
                    except (json.JSONDecodeError, TypeError):
                        pass

            image_obj = message_10.get('image')
            if isinstance(image_obj, dict):
                pics = image_obj.get('pics', [])
                if pics and isinstance(pics, list):
                    url = pics[0].get('url', '')
                    if url:
                        return url

            for key in ('picUrl', 'imageUrl', 'imgUrl', 'url'):
                val = message_10.get(key, '')
                if isinstance(val, str) and val.startswith('http'):
                    return val

        except Exception:
            pass
        return None

    def extract_item_id_from_message(self, message):
        """从消息中提取商品ID的辅助方法"""
        try:
            # 方法1: 从message["1"]中提取（如果是字符串格式）
            message_1 = message.get('1')
            if isinstance(message_1, str):
                # 尝试从字符串中提取数字ID
                id_match = re.search(r'(\d{10,})', message_1)
                if id_match:
                    logger.info(f"从message[1]字符串中提取商品ID: {id_match.group(1)}")
                    return id_match.group(1)

            # 方法2: 从message["3"]中提取
            message_3 = message.get('3', {})
            if isinstance(message_3, dict):

                # 从extension中提取
                if 'extension' in message_3:
                    extension = message_3['extension']
                    if isinstance(extension, dict):
                        item_id = extension.get('itemId') or extension.get('item_id')
                        if item_id:
                            logger.info(f"从extension中提取商品ID: {item_id}")
                            return item_id

                # 从bizData中提取
                if 'bizData' in message_3:
                    biz_data = message_3['bizData']
                    if isinstance(biz_data, dict):
                        item_id = biz_data.get('itemId') or biz_data.get('item_id')
                        if item_id:
                            logger.info(f"从bizData中提取商品ID: {item_id}")
                            return item_id

                # 从其他可能的字段中提取
                for key, value in message_3.items():
                    if isinstance(value, dict):
                        item_id = value.get('itemId') or value.get('item_id')
                        if item_id:
                            logger.info(f"从{key}字段中提取商品ID: {item_id}")
                            return item_id

                # 从消息内容中提取数字ID
                content = message_3.get('content', '')
                if isinstance(content, str) and content:
                    id_match = re.search(r'(\d{10,})', content)
                    if id_match:
                        logger.info(f"【{self.cookie_id}】从消息内容中提取商品ID: {id_match.group(1)}")
                        return id_match.group(1)

            # 方法3: 遍历整个消息结构查找可能的商品ID
            def find_item_id_recursive(obj, path=""):
                if isinstance(obj, dict):
                    # 直接查找itemId字段
                    for key in ['itemId', 'item_id', 'id']:
                        if key in obj and isinstance(obj[key], (str, int)):
                            value = str(obj[key])
                            if len(value) >= 10 and value.isdigit():
                                logger.info(f"从{path}.{key}中提取商品ID: {value}")
                                return value

                    # 递归查找
                    for key, value in obj.items():
                        result = find_item_id_recursive(value, f"{path}.{key}" if path else key)
                        if result:
                            return result

                elif isinstance(obj, str):
                    # 从字符串中提取可能的商品ID
                    id_match = re.search(r'(\d{10,})', obj)
                    if id_match:
                        logger.info(f"从{path}字符串中提取商品ID: {id_match.group(1)}")
                        return id_match.group(1)

                return None

            result = find_item_id_recursive(message)
            if result:
                return result

            logger.warning("所有方法都未能提取到商品ID")
            return None

        except Exception as e:
            logger.error(f"提取商品ID失败: {self._safe_str(e)}")
            return None

    def debug_message_structure(self, message, context=""):
        """调试消息结构的辅助方法"""
        try:
            logger.warning(f"[{context}] 消息结构调试:")
            logger.warning(f"  消息类型: {type(message)}")

            if isinstance(message, dict):
                for key, value in message.items():
                    logger.warning(f"  键 '{key}': {type(value)} - {str(value)[:100]}...")

                    # 特别关注可能包含商品ID的字段
                    if key in ["1", "3"] and isinstance(value, dict):
                        logger.warning(f"    详细结构 '{key}':")
                        for sub_key, sub_value in value.items():
                            logger.warning(f"      '{sub_key}': {type(sub_value)} - {str(sub_value)[:50]}...")
            else:
                logger.warning(f"  消息内容: {str(message)[:200]}...")

        except Exception as e:
            logger.error(f"调试消息结构时发生错误: {self._safe_str(e)}")

    async def _send_wechat_notification(self, config_data: dict, message: str):
        """发送微信通知"""
        try:
            import aiohttp
            import json

            # 解析配置
            webhook_url = config_data.get('webhook_url', '')

            if not webhook_url:
                logger.warning("微信通知配置为空")
                return

            data = {
                "msgtype": "text",
                "text": {
                    "content": message
                }
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=data, timeout=10) as response:
                    if response.status == 200:
                        logger.info(f"微信通知发送成功")
                    else:
                        logger.warning(f"微信通知发送失败: {response.status}")

        except Exception as e:
            logger.error(f"发送微信通知异常: {self._safe_str(e)}")

    async def create_chat(self, ws, toid, item_id='891198795482'):
        msg = {
            "lwp": "/r/SingleChatConversation/create",
            "headers": {
                "mid": generate_mid()
            },
            "body": [
                {
                    "pairFirst": f"{toid}@goofish",
                    "pairSecond": f"{self.myid}@goofish",
                    "bizType": "1",
                    "extension": {
                        "itemId": item_id
                    },
                    "ctx": {
                        "appVersion": "1.0",
                        "platform": "web"
                    }
                }
            ]
        }
        await ws.send(json.dumps(msg))

    async def send_msg(self, ws, cid, toid, text):
        text = {
            "contentType": 1,
            "text": {
                "text": text
            }
        }
        text_base64 = str(base64.b64encode(json.dumps(text).encode('utf-8')), 'utf-8')
        msg = {
            "lwp": "/r/MessageSend/sendByReceiverScope",
            "headers": {
                "mid": generate_mid()
            },
            "body": [
                {
                    "uuid": generate_uuid(),
                    "cid": f"{cid}@goofish",
                    "conversationType": 1,
                    "content": {
                        "contentType": 101,
                        "custom": {
                            "type": 1,
                            "data": text_base64
                        }
                    },
                    "redPointPolicy": 0,
                    "extension": {
                        "extJson": "{}"
                    },
                    "ctx": {
                        "appVersion": "1.0",
                        "platform": "web"
                    },
                    "mtags": {},
                    "msgReadStatusSetting": 1
                },
                {
                    "actualReceivers": [
                        f"{toid}@goofish",
                        f"{self.myid}@goofish"
                    ]
                }
            ]
        }
        await ws.send(json.dumps(msg))

    async def send_msg_once(self, toid, item_id, text):
        headers = {
            "Cookie": self.cookies_str,
            "Host": "wss-goofish.dingtalk.com",
            "Connection": "Upgrade",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            "Origin": "https://www.goofish.com",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        # 兼容不同版本的websockets库
        try:
            async with websockets.connect(
                self.base_url,
                extra_headers=headers
            ) as websocket:
                await self._handle_websocket_connection(websocket, toid, item_id, text)
        except TypeError as e:
            # 安全地检查异常信息
            error_msg = self._safe_str(e)

            if "extra_headers" in error_msg:
                logger.warning("websockets库不支持extra_headers参数，使用兼容模式")
                # 使用兼容模式，通过subprotocols传递部分头信息
                async with websockets.connect(
                    self.base_url,
                    additional_headers=headers
                ) as websocket:
                    await self._handle_websocket_connection(websocket, toid, item_id, text)
            else:
                raise

    def is_chat_message(self, message):
        """判断是否为用户聊天消息（支持文本和图片消息）"""
        try:
            if not (isinstance(message, dict) and "1" in message and isinstance(message["1"], dict)):
                return False
            msg_content = message["1"].get("10", None)
            if isinstance(msg_content, dict):
                if "reminderContent" in msg_content or "image" in msg_content or "content" in msg_content:
                    return True
            if isinstance(msg_content, str):
                try:
                    parsed = json.loads(msg_content)
                    if isinstance(parsed, dict):
                        if parsed.get("contentType") in (1, 2):
                            return True
                except (json.JSONDecodeError, TypeError):
                    pass
            return False
        except Exception:
            return False

    async def _handle_message_with_semaphore(self, message_data, websocket):
        """带信号量的消息处理包装器，防止并发任务过多"""
        async with self.message_semaphore:
            self.active_message_tasks += 1
            try:
                await self.handle_message(message_data, websocket)
            finally:
                self.active_message_tasks -= 1
                # 定期记录活跃任务数（每100个任务记录一次）
                if self.active_message_tasks % 100 == 0 and self.active_message_tasks > 0:
                    logger.info(f"【{self.cookie_id}】当前活跃消息处理任务数: {self.active_message_tasks}")

    def _extract_message_id(self, message_data: dict) -> str:
        """
        从消息数据中提取消息ID，用于去重
        
        Args:
            message_data: 原始消息数据
            
        Returns:
            消息ID字符串，如果无法提取则返回None
        """
        try:
            # 尝试从 message['1']['10']['bizTag'] 中提取 messageId
            if isinstance(message_data, dict) and "1" in message_data:
                message_1 = message_data.get("1")
                if isinstance(message_1, dict) and "10" in message_1:
                    message_10 = message_1.get("10")
                    if isinstance(message_10, dict) and "bizTag" in message_10:
                        biz_tag = message_10.get("bizTag", "")
                        if isinstance(biz_tag, str):
                            # bizTag 是 JSON 字符串，格式如: '{"sourceId":"S:1","messageId":"984f323c719d4cd0a7b993a0769a33b6"}'
                            try:
                                import json
                                biz_tag_dict = json.loads(biz_tag)
                                if isinstance(biz_tag_dict, dict) and "messageId" in biz_tag_dict:
                                    return biz_tag_dict.get("messageId")
                            except (json.JSONDecodeError, TypeError):
                                pass
                        
                        # 如果 bizTag 解析失败，尝试从 extJson 中提取
                        if "extJson" in message_10:
                            ext_json = message_10.get("extJson", "")
                            if isinstance(ext_json, str):
                                try:
                                    import json
                                    ext_json_dict = json.loads(ext_json)
                                    if isinstance(ext_json_dict, dict) and "messageId" in ext_json_dict:
                                        return ext_json_dict.get("messageId")
                                except (json.JSONDecodeError, TypeError):
                                    pass
        except Exception as e:
            logger.debug(f"【{self.cookie_id}】提取消息ID失败: {self._safe_str(e)}")
        
        return None

    async def _process_chat_message_reply(self, message_data: dict, websocket, send_user_name: str,
                                         send_user_id: str, send_message: str, item_id: str,
                                         chat_id: str, msg_time: str):
        """
        处理聊天消息的回复逻辑（从handle_message中提取出来的核心回复逻辑）
        
        Args:
            message_data: 原始消息数据
            websocket: WebSocket连接
            send_user_name: 发送者用户名
            send_user_id: 发送者用户ID
            send_message: 消息内容
            item_id: 商品ID
            chat_id: 聊天ID
            msg_time: 消息时间
        """
        try:
            if self._is_buyer_blacklisted(send_user_id):
                logger.warning(f"[{msg_time}] 【{self.cookie_id}】⚠️ 买家 {send_user_id} 在黑名单中，跳过自动回复")
                return

            # 自动回复消息
            if not AUTO_REPLY.get('enabled', True):
                logger.info(f"[{msg_time}] 【{self.cookie_id}】【系统】自动回复已禁用")
                return

            # 检查该chat_id是否处于暂停状态
            if pause_manager.is_chat_paused(chat_id):
                remaining_time = pause_manager.get_remaining_pause_time(chat_id)
                remaining_minutes = remaining_time // 60
                remaining_seconds = remaining_time % 60
                logger.info(f"[{msg_time}] 【{self.cookie_id}】【系统】chat_id {chat_id} 自动回复已暂停，剩余时间: {remaining_minutes}分{remaining_seconds}秒")
                return

            # 构造用户URL
            user_url = f'https://www.goofish.com/personal?userId={send_user_id}'

            reply = None
            # 判断是否启用API回复
            if AUTO_REPLY.get('api', {}).get('enabled', False):
                reply = await self.get_api_reply(
                    msg_time, user_url, send_user_id, send_user_name,
                    item_id, send_message, chat_id
                )
                if not reply:
                    logger.error(f"[{msg_time}] 【API调用失败】用户: {send_user_name} (ID: {send_user_id}), 商品({item_id}): {send_message}")

            # 记录回复来源
            reply_source = 'API'  # 默认假设是API回复

            # 如果API回复失败或未启用API，按新的优先级顺序处理
            if not reply:
                # 1. 首先尝试关键词匹配（传入商品ID）
                reply = await self.get_keyword_reply(send_user_name, send_user_id, send_message, item_id)
                if reply == "EMPTY_REPLY":
                    # 匹配到关键词但回复内容为空，不进行任何回复
                    logger.info(f"[{msg_time}] 【{self.cookie_id}】匹配到空回复关键词，跳过自动回复")
                    return
                elif reply:
                    reply_source = '关键词'  # 标记为关键词回复
                else:
                    # 2. 关键词匹配失败，如果AI开关打开，尝试AI回复
                    reply = await self.get_ai_reply(send_user_name, send_user_id, send_message, item_id, chat_id)
                    if reply:
                        reply_source = 'AI'  # 标记为AI回复
                    else:
                        # 3. 最后使用默认回复
                        default_reply_result = await self.get_default_reply(send_user_name, send_user_id, send_message, chat_id, item_id)
                        if default_reply_result == "EMPTY_REPLY":
                            # 默认回复内容为空，不进行任何回复
                            logger.info(f"[{msg_time}] 【{self.cookie_id}】默认回复内容为空，跳过自动回复")
                            return
                        
                        # 处理默认回复（可能包含图片和文字）
                        if default_reply_result and isinstance(default_reply_result, dict):
                            reply_source = '默认'  # 标记为默认回复
                            default_image_url = default_reply_result.get('image_url')
                            default_text = default_reply_result.get('text')
                            
                            # 如果存在图片，先发送图片
                            if default_image_url:
                                try:
                                    # 处理图片URL（上传到CDN如果需要）
                                    final_image_url = default_image_url
                                    image_width, image_height = 800, 600  # 默认尺寸
                                    
                                    if self._is_cdn_url(default_image_url):
                                        # 已经是CDN链接，获取真实尺寸
                                        logger.info(f"【{self.cookie_id}】默认回复使用CDN图片: {default_image_url}")
                                        width, height = await self._get_image_size_from_url(default_image_url)
                                        if width and height:
                                            image_width, image_height = width, height
                                    elif default_image_url.startswith('/static/uploads/') or default_image_url.startswith('static/uploads/'):
                                        # 本地图片，需要上传到闲鱼CDN
                                        local_image_path = default_image_url.replace('/static/uploads/', 'static/uploads/')
                                        if os.path.exists(local_image_path):
                                            logger.info(f"【{self.cookie_id}】准备上传默认回复本地图片到闲鱼CDN: {local_image_path}")
                                            
                                            from utils.image_uploader import ImageUploader
                                            uploader = ImageUploader(self.cookies_str)
                                            
                                            async with uploader:
                                                cdn_url = await uploader.upload_image(local_image_path)
                                                if cdn_url:
                                                    logger.info(f"【{self.cookie_id}】默认回复图片上传成功，CDN URL: {cdn_url}")
                                                    final_image_url = cdn_url
                                                    
                                                    # 更新数据库中的图片URL为CDN URL
                                                    await self._update_default_reply_image_url(cdn_url)
                                                    
                                                    # 获取实际图片尺寸
                                                    from utils.image_utils import image_manager
                                                    try:
                                                        actual_width, actual_height = image_manager.get_image_size(local_image_path)
                                                        if actual_width and actual_height:
                                                            image_width, image_height = actual_width, actual_height
                                                    except Exception as e:
                                                        logger.warning(f"【{self.cookie_id}】获取图片尺寸失败，使用默认尺寸: {e}")
                                                else:
                                                    logger.error(f"【{self.cookie_id}】默认回复图片上传失败: {local_image_path}")
                                                    final_image_url = None
                                        else:
                                            logger.error(f"【{self.cookie_id}】默认回复本地图片文件不存在: {local_image_path}")
                                            final_image_url = None
                                    else:
                                        # 其他类型的URL，获取真实尺寸
                                        width, height = await self._get_image_size_from_url(default_image_url)
                                        if width and height:
                                            image_width, image_height = width, height
                                    
                                    # 发送图片
                                    if final_image_url:
                                        await self.send_image_msg(websocket, chat_id, send_user_id, final_image_url, image_width, image_height)
                                        msg_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                                        logger.info(f"[{msg_time}] 【{reply_source}图片发出】用户: {send_user_name} (ID: {send_user_id}), 商品({item_id}): 图片 {final_image_url}")
                                except Exception as e:
                                    logger.error(f"【{self.cookie_id}】默认回复图片发送失败: {self._safe_str(e)}")
                            
                            # 然后发送文字（如果有）
                            if default_text and default_text.strip():
                                reply = default_text
                            else:
                                # 只有图片没有文字，已经发送完毕
                                if default_image_url:
                                    return
                                reply = None
                        else:
                            reply = None

            # 注意：这里只有商品ID，没有标题和详情，根据新的规则不保存到数据库
            # 商品信息会在其他有完整信息的地方保存（如发货规则匹配时）
            # 消息通知已在收到消息时立即发送，此处不再重复发送

            # 如果有回复内容，发送消息
            if reply:
                # 检查每日回复配额
                try:
                    from db_manager import db_manager as _dbm
                    allowed, count, limit = _dbm.check_daily_quota(self.cookie_id, 'reply')
                    if not allowed:
                        logger.warning(f"【{self.cookie_id}】今日自动回复已达上限 ({count}/{limit})，跳过回复")
                        return
                    _dbm.increment_daily_quota(self.cookie_id, 'reply')
                except Exception as qe:
                    logger.error(f"【{self.cookie_id}】配额检查异常: {self._safe_str(qe)}")
                # 检查是否是图片发送标记
                if reply.startswith("__IMAGE_SEND__"):
                    # 提取图片URL（关键词回复不包含卡券ID）
                    image_url = reply.replace("__IMAGE_SEND__", "")
                    # 发送图片消息
                    try:
                        await self.send_image_msg(websocket, chat_id, send_user_id, image_url)
                        # 记录发出的图片消息
                        msg_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                        logger.info(f"[{msg_time}] 【{reply_source}图片发出】用户: {send_user_name} (ID: {send_user_id}), 商品({item_id}): 图片 {image_url}")
                    except Exception as e:
                        # 图片发送失败，发送错误提示
                        logger.error(f"图片发送失败: {self._safe_str(e)}")
                        await self.send_msg(websocket, chat_id, send_user_id, "抱歉，图片发送失败，请稍后重试。")
                        msg_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                        logger.error(f"[{msg_time}] 【{reply_source}图片发送失败】用户: {send_user_name} (ID: {send_user_id}), 商品({item_id})")
                else:
                    # 普通文本消息
                    await self.send_msg(websocket, chat_id, send_user_id, reply)
                    # 记录发出的消息
                    msg_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                    logger.info(f"[{msg_time}] 【{reply_source}发出】用户: {send_user_name} (ID: {send_user_id}), 商品({item_id}): {reply}")
            else:
                msg_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                logger.info(f"[{msg_time}] 【{self.cookie_id}】【系统】未找到匹配的回复规则，不回复")
        except Exception as e:
            logger.error(f"处理聊天消息回复时发生错误: {self._safe_str(e)}")

    async def handle_message(self, message_data, websocket):
        """处理所有类型的消息"""
        try:
            # 检查账号是否启用
            from cookie_manager import manager as cookie_manager
            if cookie_manager and not cookie_manager.get_cookie_status(self.cookie_id):
                logger.warning(f"【{self.cookie_id}】账号已禁用，跳过消息处理")
                return

            # 发送确认消息
            try:
                message = message_data
                ack = {
                    "code": 200,
                    "headers": {
                        "mid": message["headers"]["mid"] if "mid" in message["headers"] else generate_mid(),
                        "sid": message["headers"]["sid"] if "sid" in message["headers"] else '',
                    }
                }
                if 'app-key' in message["headers"]:
                    ack["headers"]["app-key"] = message["headers"]["app-key"]
                if 'ua' in message["headers"]:
                    ack["headers"]["ua"] = message["headers"]["ua"]
                if 'dt' in message["headers"]:
                    ack["headers"]["dt"] = message["headers"]["dt"]
                await websocket.send(json.dumps(ack))
            except Exception as e:
                pass

            # 如果不是同步包消息，直接返回
            if not self.is_sync_package(message_data):
                # 添加调试日志，记录非同步包消息
                logger.debug(f"【{self.cookie_id}】非同步包消息，跳过处理")
                return

            # 获取并解密数据
            sync_data = message_data["body"]["syncPushPackage"]["data"][0]

            # 检查是否有必要的字段
            if "data" not in sync_data:
                logger.warning("同步包中无data字段")
                return

            # 解密数据
            message = None
            try:
                data = sync_data["data"]
                try:
                    data = base64.b64decode(data).decode("utf-8")
                    parsed_data = json.loads(data)
                    # 处理未加密的消息（如系统提示等）
                    msg_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                    if isinstance(parsed_data, dict) and 'chatType' in parsed_data:
                        if 'operation' in parsed_data and 'content' in parsed_data['operation']:
                            content = parsed_data['operation']['content']
                            if 'sessionArouse' in content:
                                # 处理系统引导消息
                                logger.info(f"[{msg_time}] 【{self.cookie_id}】【系统】小闲鱼智能提示:")
                                if 'arouseChatScriptInfo' in content['sessionArouse']:
                                    for qa in content['sessionArouse']['arouseChatScriptInfo']:
                                        logger.info(f"  - {qa['chatScrip']}")
                            elif 'contentType' in content:
                                # 其他类型的未加密消息
                                logger.warning(f"[{msg_time}] 【{self.cookie_id}】【系统】其他类型消息: {content}")
                        return
                    else:
                        # 如果不是系统消息，将解析的数据作为message
                        message = parsed_data
                except Exception as e:
                    # 如果JSON解析失败，尝试解密
                    decrypted_data = decrypt(data)
                    message = json.loads(decrypted_data)
            except Exception as e:
                logger.error(f"消息解密失败: {self._safe_str(e)}")
                return

            # 确保message不为空
            if message is None:
                logger.error("消息解析后为空")
                return

            # 确保message是字典类型
            if not isinstance(message, dict):
                logger.error(f"消息格式错误，期望字典但得到: {type(message)}")
                logger.warning(f"消息内容: {message}")
                return

            # 【消息接收标识】记录收到消息的时间，用于控制Cookie刷新
            self.last_message_received_time = time.time()
            logger.warning(f"【{self.cookie_id}】收到消息，更新消息接收时间标识")

            # 【优先处理】尝试获取订单ID并获取订单详情
            order_id = None
            try:
                order_id = self._extract_order_id(message)
                if order_id:
                    msg_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                    logger.info(f'[{msg_time}] 【{self.cookie_id}】✅ 检测到订单ID: {order_id}，开始获取订单详情')

                    # 通知订单状态处理器订单ID已提取
                    if self.order_status_handler:
                        logger.info(f"【{self.cookie_id}】准备调用订单状态处理器.on_order_id_extracted: {order_id}")
                        try:
                            self.order_status_handler.on_order_id_extracted(order_id, self.cookie_id, message)
                            logger.info(f"【{self.cookie_id}】订单状态处理器.on_order_id_extracted调用成功: {order_id}")
                        except Exception as e:
                            logger.error(f"【{self.cookie_id}】通知订单状态处理器订单ID提取失败: {self._safe_str(e)}")
                            import traceback
                            logger.error(f"【{self.cookie_id}】详细错误信息: {traceback.format_exc()}")
                    else:
                        logger.warning(f"【{self.cookie_id}】订单状态处理器为None，跳过订单ID提取通知: {order_id}")

                    # 立即获取订单详情信息
                    try:
                        # 先尝试提取用户ID和商品ID用于订单详情获取
                        temp_user_id = None
                        temp_item_id = None

                        # 提取用户ID
                        try:
                            message_1 = message.get("1")
                            if isinstance(message_1, str) and '@' in message_1:
                                temp_user_id = message_1.split('@')[0]
                            elif isinstance(message_1, dict):
                                # 从字典中提取用户ID
                                if "10" in message_1 and isinstance(message_1["10"], dict):
                                    temp_user_id = message_1["10"].get("senderUserId", "unknown_user")
                                else:
                                    temp_user_id = "unknown_user"
                            else:
                                temp_user_id = "unknown_user"
                        except:
                            temp_user_id = "unknown_user"

                        # 提取商品ID
                        try:
                            if "1" in message and isinstance(message["1"], dict) and "10" in message["1"] and isinstance(message["1"]["10"], dict):
                                url_info = message["1"]["10"].get("reminderUrl", "")
                                if isinstance(url_info, str) and "itemId=" in url_info:
                                    temp_item_id = url_info.split("itemId=")[1].split("&")[0]

                            if not temp_item_id:
                                temp_item_id = self.extract_item_id_from_message(message)
                        except:
                            pass

                        # 检查是否已经在获取该订单详情
                        order_detail_lock = self._order_detail_locks[order_id]
                        if order_detail_lock.locked():
                            logger.info(f'[{msg_time}] 【{self.cookie_id}】🔒 订单 {order_id} 详情正在被其他任务获取，跳过重复请求')
                        else:
                            # 调用订单详情获取方法
                            order_detail = await self.fetch_order_detail_info(order_id, temp_item_id, temp_user_id)
                            if order_detail:
                                logger.info(f'[{msg_time}] 【{self.cookie_id}】✅ 订单详情获取成功: {order_id}')
                            else:
                                logger.warning(f'[{msg_time}] 【{self.cookie_id}】⚠️ 订单详情获取失败: {order_id}')

                    except Exception as detail_e:
                        logger.error(f'[{msg_time}] 【{self.cookie_id}】❌ 获取订单详情异常: {self._safe_str(detail_e)}')
                else:
                    logger.warning(f"【{self.cookie_id}】未检测到订单ID")
            except Exception as e:
                logger.error(f"【{self.cookie_id}】提取订单ID失败: {self._safe_str(e)}")

            # 安全地获取用户ID
            user_id = None
            try:
                message_1 = message.get("1")
                if isinstance(message_1, str) and '@' in message_1:
                    user_id = message_1.split('@')[0]
                elif isinstance(message_1, dict):
                    # 如果message['1']是字典，从message["1"]["10"]["senderUserId"]中提取user_id
                    if "10" in message_1 and isinstance(message_1["10"], dict):
                        user_id = message_1["10"].get("senderUserId", "unknown_user")
                    else:
                        user_id = "unknown_user"
                else:
                    user_id = "unknown_user"
            except Exception as e:
                logger.warning(f"提取用户ID失败: {self._safe_str(e)}")
                user_id = "unknown_user"



            # 安全地提取商品ID
            item_id = None
            try:
                if "1" in message and isinstance(message["1"], dict) and "10" in message["1"] and isinstance(message["1"]["10"], dict):
                    url_info = message["1"]["10"].get("reminderUrl", "")
                    if isinstance(url_info, str) and "itemId=" in url_info:
                        item_id = url_info.split("itemId=")[1].split("&")[0]

                # 如果没有提取到，使用辅助方法
                if not item_id:
                    item_id = self.extract_item_id_from_message(message)

                if not item_id:
                    item_id = f"auto_{user_id}_{int(time.time())}"
                    logger.warning(f"无法提取商品ID，使用默认值: {item_id}")

            except Exception as e:
                logger.error(f"提取商品ID时发生错误: {self._safe_str(e)}")
                item_id = f"auto_{user_id}_{int(time.time())}"
            # 处理订单状态消息
            try:
                logger.info(message)
                msg_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

                # 安全地检查订单状态
                red_reminder = None
                if isinstance(message, dict) and "3" in message and isinstance(message["3"], dict):
                    red_reminder = message["3"].get("redReminder")

                if red_reminder == '等待买家付款':
                    user_url = f'https://www.goofish.com/personal?userId={user_id}'
                    logger.info(f'[{msg_time}] 【系统】等待买家 {user_url} 付款')
                    return
                elif red_reminder == '交易关闭':
                    user_url = f'https://www.goofish.com/personal?userId={user_id}'
                    logger.info(f'[{msg_time}] 【系统】买家 {user_url} 交易关闭')
                    return
                elif red_reminder == '等待卖家发货':
                    user_url = f'https://www.goofish.com/personal?userId={user_id}'
                    logger.info(f'[{msg_time}] 【系统】交易成功 {user_url} 等待卖家发货')
                    # return
            except:
                pass

            # 判断是否为聊天消息
            if not self.is_chat_message(message):
                logger.warning("非聊天消息")
                return

            # 处理聊天消息
            try:
                # 安全地提取聊天消息信息
                if not (isinstance(message, dict) and "1" in message and isinstance(message["1"], dict)):
                    logger.error("消息格式错误：缺少必要的字段结构")
                    return

                message_1 = message["1"]
                if not isinstance(message_1.get("10"), dict):
                    logger.error("消息格式错误：缺少消息详情字段")
                    return

                create_time = int(message_1.get("5", 0))
                message_10 = message_1["10"]
                send_user_name = message_10.get("senderNick", message_10.get("reminderTitle", "未知用户"))
                send_user_id = message_10.get("senderUserId", "unknown")
                send_message = message_10.get("reminderContent", "")
                is_image_msg = False
                image_ocr_text = None
                image_url = ""

                if not send_message:
                    image_url = self._extract_image_url_from_message(message_10)
                    if image_url:
                        is_image_msg = True
                        logger.info(f"【{self.cookie_id}】检测到买家图片消息: {image_url[:100]}")
                        from utils.ocr_engine import ocr_from_url_async, is_available as ocr_available
                        if ocr_available():
                            try:
                                image_ocr_text = await ocr_from_url_async(image_url)
                                if image_ocr_text:
                                    logger.info(f"【{self.cookie_id}】OCR 识别结果: {image_ocr_text[:200]}")
                                    send_message = image_ocr_text
                                else:
                                    logger.info(f"【{self.cookie_id}】OCR 识别无文字内容")
                            except Exception as e:
                                logger.error(f"【{self.cookie_id}】OCR 识别异常: {self._safe_str(e)}")
                        else:
                            logger.info(f"【{self.cookie_id}】OCR 引擎不可用，跳过图片识别")

                chat_id_raw = message_1.get("2", "")
                chat_id = chat_id_raw.split('@')[0] if '@' in str(chat_id_raw) else str(chat_id_raw)

                if is_image_msg:
                    await self.send_image_to_manual_notification(
                        send_user_name, send_user_id,
                        image_ocr_text or '(未识别出文字)',
                        image_url, item_id, chat_id
                    )
                    pause_manager.pause_chat(chat_id, self.cookie_id)
                    logger.info(f"【{self.cookie_id}】图片消息已暂停 chat_id={chat_id} 的自动回复")

            except Exception as e:
                logger.error(f"提取聊天消息信息失败: {self._safe_str(e)}")
                return

            # 格式化消息时间
            msg_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(create_time/1000))



            # 判断消息方向
            if send_user_id == self.myid:
                logger.info(f"[{msg_time}] 【手动发出】 商品({item_id}): {send_message}")

                # 暂停该chat_id的自动回复10分钟
                pause_manager.pause_chat(chat_id, self.cookie_id)

                return
            else:
                if is_image_msg:
                    logger.info(f"[{msg_time}] 【收到图片-OCR】用户: {send_user_name} (ID: {send_user_id}), 商品({item_id}): {send_message}")
                    logger.info(f"[{msg_time}] 【图片消息-转人工】已发送通知，跳过自动回复")
                    return

                # 🔔 立即发送消息通知（独立于自动回复功能）
                # 检查是否为群组消息，如果是群组消息则跳过通知
                try:
                    session_type = message_10.get("sessionType", "1")  # 默认为个人消息类型
                    if session_type == "30":
                        logger.info(f"📱 检测到群组消息（sessionType=30），跳过消息通知")
                    else:
                        # 只对个人消息发送通知
                        await self.send_notification(send_user_name, send_user_id, send_message, item_id, chat_id)
                except Exception as notify_error:
                    logger.error(f"📱 发送消息通知失败: {self._safe_str(notify_error)}")




            # 【优先处理】使用订单状态处理器处理系统消息
            if self.order_status_handler:
                try:
                    # 处理系统消息的订单状态更新
                    try:
                        handled = self.order_status_handler.handle_system_message(
                            message=message,
                            send_message=send_message,
                            cookie_id=self.cookie_id,
                            msg_time=msg_time
                        )
                    except Exception as e:
                        logger.error(f"【{self.cookie_id}】处理系统消息失败: {self._safe_str(e)}")
                        handled = False
                    
                    # 处理红色提醒消息
                    if not handled:
                        try:
                            if isinstance(message, dict) and "3" in message and isinstance(message["3"], dict):
                                red_reminder = message["3"].get("redReminder")
                                user_id = message["3"].get("userId", "unknown")
                                
                                if red_reminder:
                                    try:
                                        self.order_status_handler.handle_red_reminder_message(
                                            message=message,
                                            red_reminder=red_reminder,
                                            user_id=user_id,
                                            cookie_id=self.cookie_id,
                                            msg_time=msg_time
                                        )
                                    except Exception as e:
                                        logger.error(f"【{self.cookie_id}】处理红色提醒消息失败: {self._safe_str(e)}")
                        except Exception as red_e:
                            logger.warning(f"处理红色提醒消息失败: {self._safe_str(red_e)}")
                            
                except Exception as e:
                    logger.error(f"订单状态处理失败: {self._safe_str(e)}")

            # 检查买家是否在黑名单中
            try:
                from db_manager import db_manager
                cookie_info = db_manager.get_cookie_by_id(self.cookie_id)
                if cookie_info:
                    user_id = cookie_info.get('user_id', 0)
                    if user_id and send_user_id:
                        if db_manager.is_buyer_blacklisted(user_id, send_user_id):
                            logger.warning(f"【{self.cookie_id}】买家 {send_user_id} 在黑名单中，跳过自动回复/发货")
                            return
            except Exception as bl_e:
                logger.error(f"【{self.cookie_id}】黑名单检查异常: {self._safe_str(bl_e)}")

            # 【优先处理】检查系统消息和自动发货触发消息（不受人工接入暂停影响）
            if send_message == '[我已拍下，待付款]':
                logger.info(f'[{msg_time}] 【{self.cookie_id}】系统消息不处理')
                return
            elif send_message == '[你关闭了订单，钱款已原路退返]':
                logger.info(f'[{msg_time}] 【{self.cookie_id}】系统消息不处理')
                return
            elif send_message == '[不想宝贝被砍价?设置不砍价回复  ]':
                logger.info(f'[{msg_time}] 【{self.cookie_id}】系统提示信息不处理')
                return 
            elif send_message == 'AI正在帮你回复消息，不错过每笔订单':
                logger.info(f'[{msg_time}] 【{self.cookie_id}】系统提示信息不处理')
                return 
            elif send_message == '发来一条消息':
                logger.info(f'[{msg_time}] 【{self.cookie_id}】系统通知消息不处理')
                return
            elif send_message == '发来一条新消息':
                logger.info(f'[{msg_time}] 【{self.cookie_id}】系统通知消息不处理')
                return
            elif send_message == '[买家确认收货，交易成功]':
                logger.info(f'[{msg_time}] 【{self.cookie_id}】交易完成消息，触发自动评价')
                if self.order_status_handler:
                    order_id = self.order_status_handler.extract_order_id(message)
                    if order_id:
                        asyncio.create_task(self.auto_evaluate(order_id, item_id, send_user_id))
                    else:
                        logger.warning(f'[{msg_time}] 【{self.cookie_id}】无法提取订单ID，跳过自动评价')
                return
            elif send_message == '快给ta一个评价吧~' or send_message == '快给ta一个评价吧～':
                logger.info(f'[{msg_time}] 【{self.cookie_id}】评价提醒消息，触发自动评价')
                if self.order_status_handler:
                    order_id = self.order_status_handler.extract_order_id(message)
                    if order_id:
                        asyncio.create_task(self.auto_evaluate(order_id, item_id, send_user_id))
                    else:
                        logger.warning(f'[{msg_time}] 【{self.cookie_id}】无法提取订单ID，跳过自动评价')
                return
            elif send_message == '卖家人不错？送Ta闲鱼小红花':
                logger.info(f'[{msg_time}] 【{self.cookie_id}】小红花提醒消息不处理')
                return
            elif send_message == '[你已确认收货，交易成功]':
                logger.info(f'[{msg_time}] 【{self.cookie_id}】买家确认收货消息不处理')
                return
            elif send_message == '[你已发货]':
                logger.info(f'[{msg_time}] 【{self.cookie_id}】发货确认消息不处理')
                return
            elif send_message == '已发货':
                logger.info(f'[{msg_time}] 【{self.cookie_id}】发货确认消息不处理')
                return
            # 【重要】检查是否为自动发货触发消息 - 即使在人工接入暂停期间也要处理
            elif self._is_auto_delivery_trigger(send_message):
                logger.info(f'[{msg_time}] 【{self.cookie_id}】检测到自动发货触发消息，即使在暂停期间也继续处理: {send_message}')
                # 使用统一的自动发货处理方法
                await self._handle_auto_delivery(websocket, message, send_user_name, send_user_id,
                                               item_id, chat_id, msg_time)
                return
            # 【重要】检查是否为"我已小刀，待刀成"卡片消息 - 即使在人工接入暂停期间也要处理
            elif send_message == '[卡片消息]':
                # 检查是否为"我已小刀，待刀成"的卡片消息
                try:
                    # 从消息中提取卡片内容
                    card_title = None
                    if isinstance(message, dict) and "1" in message and isinstance(message["1"], dict):
                        message_1 = message["1"]
                        if "6" in message_1 and isinstance(message_1["6"], dict):
                            message_6 = message_1["6"]
                            if "3" in message_6 and isinstance(message_6["3"], dict):
                                message_6_3 = message_6["3"]
                                if "5" in message_6_3:
                                    # 解析JSON内容
                                    try:
                                        card_content = json.loads(message_6_3["5"])
                                        if "dxCard" in card_content and "item" in card_content["dxCard"]:
                                            card_item = card_content["dxCard"]["item"]
                                            if "main" in card_item and "exContent" in card_item["main"]:
                                                ex_content = card_item["main"]["exContent"]
                                                card_title = ex_content.get("title", "")
                                    except (json.JSONDecodeError, KeyError) as e:
                                        logger.warning(f"解析卡片消息失败: {e}")

                    # 检查是否为"我已小刀，待刀成"
                    if card_title == "我已小刀，待刀成":
                        logger.info(f'[{msg_time}] 【{self.cookie_id}】【系统】检测到"我已小刀，待刀成"，即使在暂停期间也继续处理')

                        # 检查商品是否属于当前cookies
                        if item_id and item_id != "未知商品":
                            try:
                                from db_manager import db_manager
                                item_info = db_manager.get_item_info(self.cookie_id, item_id)
                                if not item_info:
                                    logger.warning(f'[{msg_time}] 【{self.cookie_id}】❌ 商品 {item_id} 不属于当前账号，跳过免拼发货')
                                    return
                                logger.warning(f'[{msg_time}] 【{self.cookie_id}】✅ 商品 {item_id} 归属验证通过')
                            except Exception as e:
                                logger.error(f'[{msg_time}] 【{self.cookie_id}】检查商品归属失败: {self._safe_str(e)}，跳过免拼发货')
                                return

                        # 提取订单ID
                        order_id = self._extract_order_id(message)
                        if not order_id:
                            logger.warning(f'[{msg_time}] 【{self.cookie_id}】❌ 未能提取到订单ID，无法执行免拼发货')
                            return

                        # 更新订单的is_bargain字段为True（标记为小刀订单）
                        try:
                            from db_manager import db_manager
                            db_manager.insert_or_update_order(
                                order_id=order_id,
                                item_id=item_id,
                                buyer_id=send_user_id,
                                cookie_id=self.cookie_id,
                                is_bargain=True,
                                chat_id=chat_id
                            )
                            logger.info(f'[{msg_time}] 【{self.cookie_id}】✅ 订单 {order_id} 已标记为小刀订单')
                        except Exception as e:
                            logger.error(f'[{msg_time}] 【{self.cookie_id}】标记小刀订单失败: {self._safe_str(e)}')

                        # 延迟2秒后执行免拼发货
                        logger.info(f'[{msg_time}] 【{self.cookie_id}】延迟2秒后执行免拼发货...')
                        await asyncio.sleep(self._random_delay(2.0, 0.3))
                        # 调用自动免拼发货方法
                        result = await self.auto_freeshipping(order_id, item_id, send_user_id)
                        if result.get('success'):
                            logger.info(f'[{msg_time}] 【{self.cookie_id}】✅ 自动免拼发货成功')
                        else:
                            logger.warning(f'[{msg_time}] 【{self.cookie_id}】❌ 自动免拼发货失败: {result.get("error", "未知错误")}')
                        await self._handle_auto_delivery(websocket, message, send_user_name, send_user_id,
                                                       item_id, chat_id, msg_time)
                        return
                    else:
                        logger.info(f'[{msg_time}] 【{self.cookie_id}】收到卡片消息，标题: {card_title or "未知"}')
                        # 如果不是目标卡片消息，继续正常处理流程（会受到暂停影响）

                except Exception as e:
                    logger.error(f"处理卡片消息异常: {self._safe_str(e)}")
                    # 如果处理异常，继续正常处理流程（会受到暂停影响）

            # 使用防抖机制处理聊天消息回复
            # 如果用户连续发送消息，等待用户停止发送后再回复最后一条消息
            await self._schedule_debounced_reply(
                chat_id=chat_id,
                message_data=message_data,
                websocket=websocket,
                send_user_name=send_user_name,
                send_user_id=send_user_id,
                send_message=send_message,
                item_id=item_id,
                msg_time=msg_time
            )

        except Exception as e:
            logger.error(f"处理消息时发生错误: {self._safe_str(e)}")
            logger.warning(f"原始消息: {message_data}")

    async def send_image_msg(self, ws, cid, toid, image_url, width=800, height=600, card_id=None):
        """发送图片消息"""
        try:
            # 检查图片URL是否需要上传到CDN
            original_url = image_url

            if self._is_cdn_url(image_url):
                # 已经是CDN链接，直接使用
                logger.info(f"【{self.cookie_id}】使用已有的CDN图片链接: {image_url}")
            elif image_url.startswith('/static/uploads/') or image_url.startswith('static/uploads/'):
                # 本地图片，需要上传到闲鱼CDN
                local_image_path = image_url.replace('/static/uploads/', 'static/uploads/')
                if os.path.exists(local_image_path):
                    logger.info(f"【{self.cookie_id}】准备上传本地图片到闲鱼CDN: {local_image_path}")

                    # 使用图片上传器上传到闲鱼CDN
                    from utils.image_uploader import ImageUploader
                    uploader = ImageUploader(self.cookies_str)

                    async with uploader:
                        cdn_url = await uploader.upload_image(local_image_path)
                        if cdn_url:
                            logger.info(f"【{self.cookie_id}】图片上传成功，CDN URL: {cdn_url}")
                            image_url = cdn_url

                            # 如果是卡券图片，更新数据库中的图片URL
                            if card_id is not None:
                                await self._update_card_image_url(card_id, cdn_url)

                            # 获取实际图片尺寸
                            from utils.image_utils import image_manager
                            try:
                                actual_width, actual_height = image_manager.get_image_size(local_image_path)
                                if actual_width and actual_height:
                                    width, height = actual_width, actual_height
                                    logger.info(f"【{self.cookie_id}】获取到实际图片尺寸: {width}x{height}")
                            except Exception as e:
                                logger.warning(f"【{self.cookie_id}】获取图片尺寸失败，使用默认尺寸: {e}")
                        else:
                            logger.error(f"【{self.cookie_id}】图片上传失败: {local_image_path}")
                            logger.error(f"【{self.cookie_id}】❌ Cookie可能已失效！请检查配置并更新Cookie")
                            raise Exception(f"图片上传失败（Cookie可能已失效）: {local_image_path}")
                else:
                    logger.error(f"【{self.cookie_id}】本地图片文件不存在: {local_image_path}")
                    raise Exception(f"本地图片文件不存在: {local_image_path}")
            else:
                logger.warning(f"【{self.cookie_id}】未知的图片URL格式: {image_url}")

            # 记录详细的图片信息
            logger.info(f"【{self.cookie_id}】准备发送图片消息:")
            logger.info(f"  - 原始URL: {original_url}")
            logger.info(f"  - CDN URL: {image_url}")
            logger.info(f"  - 图片尺寸: {width}x{height}")
            logger.info(f"  - 聊天ID: {cid}")
            logger.info(f"  - 接收者ID: {toid}")

            # 构造图片消息内容 - 使用正确的闲鱼格式
            image_content = {
                "contentType": 2,  # 图片消息类型
                "image": {
                    "pics": [
                        {
                            "height": int(height),
                            "type": 0,
                            "url": image_url,
                            "width": int(width)
                        }
                    ]
                }
            }

            # Base64编码
            content_json = json.dumps(image_content, ensure_ascii=False)
            content_base64 = str(base64.b64encode(content_json.encode('utf-8')), 'utf-8')

            logger.info(f"【{self.cookie_id}】图片内容JSON: {content_json}")
            logger.info(f"【{self.cookie_id}】Base64编码长度: {len(content_base64)}")

            # 构造WebSocket消息（完全参考send_msg的格式）
            msg = {
                "lwp": "/r/MessageSend/sendByReceiverScope",
                "headers": {
                    "mid": generate_mid()
                },
                "body": [
                    {
                        "uuid": generate_uuid(),
                        "cid": f"{cid}@goofish",
                        "conversationType": 1,
                        "content": {
                            "contentType": 101,
                            "custom": {
                                "type": 1,
                                "data": content_base64
                            }
                        },
                        "redPointPolicy": 0,
                        "extension": {
                            "extJson": "{}"
                        },
                        "ctx": {
                            "appVersion": "1.0",
                            "platform": "web"
                        },
                        "mtags": {},
                        "msgReadStatusSetting": 1
                    },
                    {
                        "actualReceivers": [
                            f"{toid}@goofish",
                            f"{self.myid}@goofish"
                        ]
                    }
                ]
            }

            await ws.send(json.dumps(msg))
            logger.info(f"【{self.cookie_id}】图片消息发送成功: {image_url}")

        except Exception as e:
            logger.error(f"【{self.cookie_id}】发送图片消息失败: {self._safe_str(e)}")
            raise

