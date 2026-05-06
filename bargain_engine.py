"""
主动议价引擎 - 接收闲鱼链接后自动发起聊天并议价
"""
import json
import time
import base64
import asyncio
from typing import Optional, Dict, Any, List, Tuple
from loguru import logger

from feishu_link_parser import fetch_item_metadata

_pending_bargains: Dict[str, Dict[str, Any]] = {}
_pending_lock = asyncio.Lock()


async def get_available_account(cookies_str: str = None) -> Optional[Tuple[str, str, Any]]:
    """获取一个可用的闲鱼账号实例

    Returns:
        (cookie_id, cookies_str, XianyuLive_instance) 或 None
    """
    try:
        from XianyuAutoAsync import XianyuLive
        instances = XianyuLive.get_all_instances()
        if instances:
            for cookie_id, instance in instances.items():
                cookie_str = instance.cookies_str if hasattr(instance, 'cookies_str') else ''
                if cookie_str:
                    return cookie_id, cookie_str, instance
        return None
    except Exception as e:
        logger.error(f"获取可用账号失败: {e}")
        return None


def generate_mid():
    """生成消息ID"""
    import uuid
    return str(uuid.uuid4()).replace('-', '').upper()


def generate_uuid():
    """生成UUID"""
    import uuid
    return str(uuid.uuid4()).upper()


async def initiate_bargain_chat(
    account_cookie_id: str,
    account_cookies_str: str,
    seller_id: str,
    item_id: str,
    bargain_message: str,
    item_price: str = '',
    item_title: str = ''
) -> Dict[str, Any]:
    """
    通过一个已有账号向卖家发起聊天并发送议价消息

    Args:
        account_cookie_id: 使用哪个账号来发消息
        account_cookies_str: 该账号的cookie字符串
        seller_id: 卖家用户ID
        item_id: 商品ID
        bargain_message: 议价消息内容
        item_price: 商品价格（可选，用于日志）
        item_title: 商品标题（可选，用于日志）

    Returns:
        {success, chat_id, message, error}
    """
    import websockets
    from urllib.parse import urlparse

    result = {'success': False, 'chat_id': None, 'message': '', 'error': ''}

    try:
        base_url = 'wss://wss-goofish.dingtalk.com/'
        cookie_dict = {}
        for pair in account_cookies_str.split('; '):
            if '=' in pair:
                k, v = pair.split('=', 1)
                cookie_dict[k.strip()] = v.strip()

        my_id = cookie_dict.get('unb', '')
        if not my_id:
            result['error'] = 'Cookie中缺少unb字段'
            return result

        headers = {
            'Cookie': account_cookies_str,
            'Host': 'wss-goofish.dingtalk.com',
            'Connection': 'Upgrade',
            'Pragma': 'no-cache',
            'Cache-Control': 'no-cache',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Origin': 'https://www.goofish.com',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        }

        async with websockets.connect(base_url, extra_headers=headers) as ws:
            logger.info(f"WebSocket连接成功，开始创建聊天: seller={seller_id}, item={item_id}")

            create_msg = {
                "lwp": "/r/SingleChatConversation/create",
                "headers": {"mid": generate_mid()},
                "body": [{
                    "pairFirst": f"{seller_id}@goofish",
                    "pairSecond": f"{my_id}@goofish",
                    "bizType": "1",
                    "extension": {"itemId": item_id},
                    "ctx": {"appVersion": "1.0", "platform": "web"}
                }]
            }
            await ws.send(json.dumps(create_msg))

            chat_response = await asyncio.wait_for(ws.recv(), timeout=10)
            logger.info(f"聊天创建响应: {chat_response[:300]}")

            chat_id = None
            try:
                resp_data = json.loads(chat_response)
                if isinstance(resp_data, dict):
                    body = resp_data.get('body', [])
                    if isinstance(body, list) and body:
                        cid = body[0].get('cid', '')
                        if cid:
                            chat_id = cid.split('@')[0] if '@' in cid else cid
            except Exception:
                pass

            if not chat_id:
                try:
                    resp_json = json.loads(chat_response)
                    chat_id = _extract_cid_from_response(resp_json)
                except Exception:
                    pass

            if not chat_id:
                result['error'] = '无法获取chat_id'
                return result

            logger.info(f"聊天创建成功，chat_id={chat_id}")

            text_data = {
                "contentType": 1,
                "text": {"text": bargain_message}
            }
            text_base64 = base64.b64encode(
                json.dumps(text_data).encode('utf-8')
            ).decode('utf-8')

            send_msg = {
                "lwp": "/r/MessageSend/sendByReceiverScope",
                "headers": {"mid": generate_mid()},
                "body": [
                    {
                        "uuid": generate_uuid(),
                        "cid": f"{chat_id}@goofish",
                        "conversationType": 1,
                        "content": {
                            "contentType": 101,
                            "custom": {
                                "type": 1,
                                "data": text_base64
                            }
                        },
                        "redPointPolicy": 0,
                        "extension": {"extJson": "{}"},
                        "ctx": {"appVersion": "1.0", "platform": "web"},
                        "mtags": {},
                        "msgReadStatusSetting": 1
                    },
                    {
                        "actualReceivers": [
                            f"{seller_id}@goofish",
                            f"{my_id}@goofish"
                        ]
                    }
                ]
            }
            await ws.send(json.dumps(send_msg))

            try:
                send_response = await asyncio.wait_for(ws.recv(), timeout=5)
                logger.info(f"消息发送响应: {send_response[:200]}")
            except asyncio.TimeoutError:
                logger.info("消息发送后无响应（可能正常）")

            await asyncio.sleep(0.5)

        result['success'] = True
        result['chat_id'] = chat_id
        result['message'] = bargain_message

        logger.info(
            f"✅ 议价消息发送成功: account={account_cookie_id}, "
            f"chat_id={chat_id}, seller={seller_id}, item={item_id}"
        )
        return result

    except asyncio.TimeoutError:
        result['error'] = 'WebSocket操作超时'
        logger.error(f"议价聊天超时: {result['error']}")
        return result
    except Exception as e:
        result['error'] = str(e)
        logger.error(f"议价聊天失败: {e}")
        return result


def _extract_cid_from_response(data: dict) -> Optional[str]:
    """从WebSocket响应中递归提取cid"""
    if isinstance(data, dict):
        for key in ('cid', 'chatId', 'chat_id'):
            val = data.get(key, '')
            if val:
                return val.split('@')[0] if '@' in str(val) else str(val)
        if 'body' in data and isinstance(data['body'], list):
            for item in data['body']:
                cid = _extract_cid_from_response(item)
                if cid:
                    return cid
        for v in data.values():
            if isinstance(v, (dict, list)):
                cid = _extract_cid_from_response(v)
                if cid:
                    return cid
    elif isinstance(data, list):
        for item in data:
            cid = _extract_cid_from_response(item)
            if cid:
                return cid
    return None


def generate_bargain_message(
    item_title: str = '',
    item_price: str = '',
    max_discount_percent: int = 10,
    max_discount_amount: int = 100
) -> str:
    """生成初始议价消息（不需要AI的首轮简单议价）"""
    if item_title and item_price:
        return f"请问这个{item_title}可以便宜一点吗？"
    elif item_title:
        return f"请问这个{item_title}还有优惠吗？"
    else:
        return "请问可以便宜一点吗？"


async def generate_ai_bargain_message(
    item_title: str,
    item_price: str,
    item_desc: str = '',
    cookies_str: str = None
) -> Optional[str]:
    """使用AI生成更智能的议价消息"""
    try:
        from XianyuAgent import XianyuReplyBot

        item_info = {
            'title': item_title,
            'price': item_price,
            'desc': item_desc
        }
        item_info_str = json.dumps(item_info, ensure_ascii=False)

        context = [{
            'role': 'system',
            'content': (
                '你是一位买家，正在闲鱼上与卖家就一件商品进行议价。'
                '请以买家的身份，礼貌且真诚地向卖家询问是否可以优惠。'
                '回复要简短自然，像一个真实的买家。'
                '总字数不超过30字。'
            )
        }]

        bot = XianyuReplyBot()
        reply = await asyncio.to_thread(
            bot.generate_reply,
            '我想买这个，可以便宜一点吗？',
            item_info_str,
            context
        )
        if reply and reply != '-':
            return reply
        return None
    except Exception as e:
        logger.error(f"AI生成议价消息失败: {e}")
        return None


async def execute_bargain(
    item_id: str,
    seller_id: str = None,
    cookies_str: str = None,
    max_discount_percent: int = 10,
    max_discount_amount: int = 100,
    use_ai: bool = False
) -> Dict[str, Any]:
    """执行完整的议价流程

    Args:
        item_id: 商品ID
        seller_id: 卖家ID（可选，如果为空则从商品元数据中获取）
        cookies_str: 可选的Cookie字符串
        max_discount_percent: 最大折扣百分比
        max_discount_amount: 最大折扣金额
        use_ai: 是否使用AI生成议价消息

    Returns:
        {success, steps, error, item_info, bargain_result}
    """
    result = {'success': False, 'steps': [], 'error': '', 'item_info': {}, 'bargain_result': {}}

    try:
        result['steps'].append('fetching_metadata')
        meta = await fetch_item_metadata(item_id, cookies_str)
        result['item_info'] = meta

        if not seller_id:
            seller_id = meta.get('seller_id', '')
        if not item_id:
            item_id = meta.get('item_id', item_id)

        if not seller_id:
            return {**result, 'error': '未能获取卖家ID'}

        item_title = meta.get('title', '')
        item_price = meta.get('price_text') or meta.get('price', '')

        result['steps'].append('getting_account')
        account = await get_available_account(cookies_str)
        if not account:
            return {**result, 'error': '没有可用的闲鱼账号'}

        account_id, account_cookies, _ = account

        result['steps'].append('generating_message')
        if use_ai:
            bargain_msg = await generate_ai_bargain_message(
                item_title, item_price, '', account_cookies
            )
        if not bargain_msg:
            bargain_msg = generate_bargain_message(
                item_title, item_price, max_discount_percent, max_discount_amount
            )

        if not bargain_msg:
            bargain_msg = "请问可以便宜一点吗？"

        result['steps'].append('sending_message')
        bargain_result = await initiate_bargain_chat(
            account_id, account_cookies, seller_id, item_id, bargain_msg,
            item_price, item_title
        )
        result['bargain_result'] = bargain_result

        if bargain_result.get('success'):
            result['success'] = True
        else:
            result['error'] = bargain_result.get('error', '发送失败')

        return result

    except Exception as e:
        result['error'] = str(e)
        logger.error(f"执行议价流程失败: {e}")
        return result


async def handle_feishu_bargain_request(
    urls: list,
    response_url: str = None,
    max_discount_percent: int = 10,
    max_discount_amount: int = 100
) -> Dict[str, Any]:
    """处理来自飞书的议价请求

    Args:
        urls: 闲鱼链接列表
        response_url: 飞书响应URL（可选，用于主动回复飞书群）
        max_discount_percent: 最大折扣百分比
        max_discount_amount: 最大折扣金额

    Returns:
        处理结果
    """
    results = {'total': len(urls), 'success': [], 'failed': [], 'notifications': []}

    for url in urls:
        from feishu_link_parser import parse_goofish_url
        parsed = parse_goofish_url(url)
        if not parsed.get('item_id') and not parsed.get('user_id'):
            results['failed'].append({'url': url, 'error': '无法解析链接'})
            continue

        item_id = parsed.get('item_id', '')
        seller_id = parsed.get('user_id', '')

        bargain_result = await execute_bargain(
            item_id=item_id,
            seller_id=seller_id,
            max_discount_percent=max_discount_percent,
            max_discount_amount=max_discount_amount
        )

        entry = {
            'url': url,
            'item_id': item_id,
            'seller_id': seller_id,
            **bargain_result
        }

        if bargain_result.get('success'):
            results['success'].append(entry)

            from feishu_link_parser import format_bargain_notification
            notification = format_bargain_notification(
                bargain_result.get('item_info', {}),
                {'max_discount_percent': max_discount_percent, 'max_discount_amount': max_discount_amount}
            )
            notification += '\n\n✅ 议价消息已发送'
            results['notifications'].append(notification)
        else:
            results['failed'].append(entry)
            results['notifications'].append(
                f"❌ 议价失败: {url}\n错误: {bargain_result.get('error', '未知')}"
            )

    return results
