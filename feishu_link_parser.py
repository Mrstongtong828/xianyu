"""
飞书链接解析器 - 从飞书消息中解析闲鱼链接，提取卖家ID和商品信息
"""
import re
import json
import asyncio
from typing import Optional, Dict, Any, Tuple
from urllib.parse import urlparse, parse_qs, unquote
from loguru import logger


_GOOFISH_URL_PATTERN = re.compile(
    r'https?://(?:www\.)?goofish\.com/(?:item\?id=|personal\?userId=)(\d+)|'
    r'https?://(?:www\.)?2\.taobao\.com/item\.htm\?.*?id=(\d+)'
)

_ITEM_ID_PATTERN = re.compile(r'item\?id=(\d{10,})')
_USER_ID_PATTERN = re.compile(r'(?:userId|user_id)=(\d+)')
_ITEM_ID_SHORT = re.compile(r'goofish\.com/im/(\d+)')
_XIANYU_URL_PATTERN = re.compile(r'https?://(?:[^.]+\.)?goofish\.com[^\s]*|https?://2\.taobao\.com/item\.htm[^\s]*')


def extract_goofish_urls(text: str) -> list:
    """从文本中提取所有闲鱼/转转链接"""
    urls = []
    for match in _XIANYU_URL_PATTERN.finditer(text):
        url = match.group(0).strip()
        url = re.sub(r'[\)\]）】,，。；;].*$', '', url)
        urls.append(url)
    return urls


def parse_goofish_url(url: str) -> Dict[str, Any]:
    """
    解析闲鱼链接，提取商品ID和卖家ID

    支持格式:
    - https://www.goofish.com/item?id=1234567890
    - https://www.goofish.com/personal?userId=123456
    - https://www.goofish.com/im/1234567890
    - https://2.taobao.com/item.htm?id=1234567890
    """
    result = {
        'url': url,
        'item_id': None,
        'user_id': None,
        'link_type': 'unknown'
    }

    # 优先检查用户链接
    user_match = _USER_ID_PATTERN.search(url)
    if user_match:
        result['user_id'] = user_match.group(1)
        if 'personal' in url:
            result['link_type'] = 'user'

    # 检查商品链接（仅当是 item?id= 格式时才赋值）
    item_match = _ITEM_ID_PATTERN.search(url)
    if item_match:
        result['item_id'] = item_match.group(1)
        result['link_type'] = 'item'

    # 短链接格式
    if not result['item_id']:
        short_match = _ITEM_ID_SHORT.search(url)
        if short_match:
            result['item_id'] = short_match.group(1)
            result['link_type'] = 'item_short'

    # 最后兜底：从通用模式中提取，但注意区分 item 和 personal
    if not result['item_id'] and not result['user_id']:
        match = _GOOFISH_URL_PATTERN.search(url)
        if match:
            extracted = match.group(1) or match.group(2)
            if extracted:
                if 'personal' in url:
                    result['user_id'] = extracted
                    result['link_type'] = 'user'
                else:
                    result['item_id'] = extracted
                    result['link_type'] = 'item'

    return result


METADATA_CACHE = {}
_METADATA_CACHE_TTL = 600


async def fetch_item_metadata(item_id: str, cookies_str: str = None) -> Dict[str, Any]:
    """
    通过闲鱼API获取商品元数据（标题、价格、卖家信息等）

    Args:
        item_id: 商品ID
        cookies_str: 可选的Cookie字符串（使用已登录账号的cookie）

    Returns:
        包含 title, price, seller_id, seller_name 的字典
    """
    import time
    cache_key = f"item_meta_{item_id}"
    cached = METADATA_CACHE.get(cache_key)
    if cached and time.time() - cached.get('_ts', 0) < _METADATA_CACHE_TTL:
        logger.info(f"使用缓存的商品元数据: {item_id}")
        return cached

    try:
        import aiohttp

        params = {
            'jsv': '2.7.2',
            'appKey': '34839810',
            't': str(int(time.time()) * 1000),
            'sign': '',
            'v': '1.0',
            'type': 'originaljson',
            'accountSite': 'xianyu',
            'dataType': 'json',
            'timeout': '20000',
            'api': 'mtop.taobao.idle.pc.detail',
            'sessionOption': 'AutoLoginOnly',
        }

        data_val = '{"itemId":"' + item_id + '"}'

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Content-Type': 'application/x-www-form-urlencoded',
        }

        if cookies_str:
            headers['Cookie'] = cookies_str

        try:
            from utils.xianyu_utils import generate_sign, trans_cookies
            token = ''
            if cookies_str:
                cookie_dict = trans_cookies(cookies_str)
                token = cookie_dict.get('_m_h5_tk', '').split('_')[0]
            sign = generate_sign(params['t'], token, data_val)
            params['sign'] = sign
        except Exception:
            pass

        async with aiohttp.ClientSession() as session:
            async with session.post(
                'https://h5api.m.goofish.com/h5/mtop.taobao.idle.pc.detail/1.0/',
                params=params,
                data={'data': data_val},
                headers=headers,
                timeout=15
            ) as response:
                res_json = await response.json()

        result = {'item_id': item_id, '_ts': time.time()}

        if isinstance(res_json, dict):
            data_block = res_json.get('data', {})
            if isinstance(data_block, dict):
                item_data = data_block.get('item', data_block)
                if isinstance(item_data, dict):
                    result['title'] = item_data.get('title', '')
                    result['price'] = item_data.get('price', '')
                    result['price_text'] = item_data.get('priceText', item_data.get('price_text', ''))

                    seller_info = item_data.get('seller', {}) or item_data.get('user', {})
                    if isinstance(seller_info, dict):
                        result['seller_id'] = str(seller_info.get('userId', seller_info.get('user_id', '')))
                        result['seller_name'] = seller_info.get('nick', seller_info.get('userNick', ''))

                    if not result.get('seller_id'):
                        result['seller_id'] = str(item_data.get('userId', item_data.get('sellerId', '')))

            ret_value = res_json.get('ret', [])
            success = any('SUCCESS' in str(r) for r in ret_value)
            result['_api_success'] = success

        METADATA_CACHE[cache_key] = result
        logger.info(f"商品元数据获取成功: {item_id} -> {result.get('title', 'N/A')}")
        return result

    except Exception as e:
        logger.error(f"获取商品元数据失败: {item_id}, {e}")
        return {'item_id': item_id, 'error': str(e), '_ts': time.time()}


async def parse_feishu_message_for_links(text: str) -> list:
    """
    解析飞书消息中的闲鱼链接，返回结构化数据列表

    Args:
        text: 飞书消息文本内容

    Returns:
        [{url, item_id, user_id, link_type, metadata}, ...]
    """
    urls = extract_goofish_urls(text)
    if not urls:
        return []

    results = []
    for url in urls:
        parsed = parse_goofish_url(url)
        if parsed['item_id'] or parsed['user_id']:
            results.append(parsed)

    return results


def format_bargain_notification(item_meta: Dict[str, Any], bargain_config: Dict[str, Any] = None) -> str:
    """格式化议价通知消息，用于发送回飞书"""
    title = item_meta.get('title', '未知商品')
    price = item_meta.get('price_text') or item_meta.get('price', '未知')
    seller = item_meta.get('seller_name', '未知')
    item_id = item_meta.get('item_id', '')
    seller_id = item_meta.get('seller_id', '')

    lines = [
        f"🔍 闲鱼商品解析结果",
        f"商品: {title}",
        f"价格: {price}",
        f"卖家: {seller}",
        f"卖家ID: {seller_id}",
        f"商品ID: {item_id}",
    ]

    if bargain_config:
        max_discount = bargain_config.get('max_discount_percent', 0)
        max_amount = bargain_config.get('max_discount_amount', 0)
        lines.append('')
        lines.append(f"📋 议价设置: 最大折扣 {max_discount}% / {max_amount}元")

    return '\n'.join(lines)
