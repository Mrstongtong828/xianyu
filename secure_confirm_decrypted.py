import json
import time
import hmac
import hashlib
import aiohttp
from loguru import logger
from config import config as cfg
from utils.xianyu_utils import generate_sign, trans_cookies


class SecureConfirm:
    def __init__(self, session, cookies_str, cookie_id, instance=None):
        self.session = session
        self.cookies_str = cookies_str
        self.cookies = trans_cookies(cookies_str) if cookies_str else {}
        self.cookie_id = cookie_id
        self.instance = instance
        self.current_token = getattr(instance, 'current_token', None) if instance else None
        self.last_token_refresh_time = getattr(instance, 'last_token_refresh_time', 0) if instance else 0
        self.token_refresh_interval = getattr(instance, 'token_refresh_interval', 72000) if instance else 72000

    async def _get_headers(self):
        token = trans_cookies(self.cookies_str).get('_m_h5_tk', '')
        token = token.split('_')[0] if token else ''
        return {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://www.goofish.com',
            'Referer': 'https://www.goofish.com/',
            'cookie': self.cookies_str,
        }

    async def _get_token(self):
        if self.current_token and (time.time() - self.last_token_refresh_time) < self.token_refresh_interval:
            return self.current_token

        try:
            cookies = trans_cookies(self.cookies_str)
            token = cookies.get('_m_h5_tk', '').split('_')[0] if cookies.get('_m_h5_tk') else ''
            device_id = None
            if self.instance:
                device_id = getattr(self.instance, 'device_id', None)
            if not device_id:
                unb = cookies.get('unb', 'unknown')
                from utils.xianyu_utils import generate_device_id
                device_id = generate_device_id(unb)

            timestamp = str(int(time.time() * 1000))
            data_val = '{"appKey":"444e9908a51d1cb236a27862abc769c9","deviceId":"' + device_id + '"}'
            sign = generate_sign(timestamp, token, data_val)

            params = {
                'jsv': '2.7.2',
                'appKey': '34839810',
                't': timestamp,
                'sign': sign,
                'v': '1.0',
                'type': 'originaljson',
                'accountSite': 'xianyu',
                'dataType': 'json',
                'timeout': '20000',
                'api': 'mtop.taobao.idlemessage.pc.login.token',
                'sessionOption': 'AutoLoginOnly',
            }
            data = {'data': data_val}

            async with aiohttp.ClientSession() as s:
                async with s.post(
                    'https://h5api.m.goofish.com/h5/mtop.taobao.idlemessage.pc.login.token/1.0/',
                    params=params, data=data,
                    headers={'cookie': self.cookies_str, 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                ) as resp:
                    res_json = await resp.json()
                    ret = res_json.get('ret', [])
                    if ret and len(ret) > 0:
                        ret_str = ret[0] if isinstance(ret, list) else str(ret)
                        if 'SUCCESS' in ret_str:
                            access_token = res_json.get('data', {}).get('accessToken', '')
                            if access_token:
                                self.current_token = access_token
                                self.last_token_refresh_time = time.time()
                                return access_token
            return None
        except Exception:
            return None

    async def auto_confirm(self, order_id, item_id=None, retry_count=0):
        try:
            access_token = await self._get_token()
            if not access_token:
                logger.warning(f"【{self.cookie_id}】确认发货失败：无法获取有效Token")
                return {'success': False, 'error': '无法获取有效Token', 'order_id': order_id}

            cookies = trans_cookies(self.cookies_str)
            unb = cookies.get('unb', '')
            device_id = getattr(self.instance, 'device_id', None) if self.instance else None
            if not device_id:
                from utils.xianyu_utils import generate_device_id
                device_id = generate_device_id(unb)

            data_val = json.dumps({
                "orderId": order_id,
                "appKey": "444e9908a51d1cb236a27862abc769c9",
                "deviceId": device_id,
            })

            m_h5_tk = cookies.get('_m_h5_tk', '')
            token = m_h5_tk.split('_')[0] if m_h5_tk else ''
            timestamp = str(int(time.time() * 1000))
            sign = generate_sign(timestamp, token, data_val)

            params = {
                'jsv': '2.7.2',
                'appKey': '34839810',
                't': timestamp,
                'sign': sign,
                'v': '1.0',
                'type': 'originaljson',
                'accountSite': 'xianyu',
                'dataType': 'json',
                'timeout': '20000',
                'api': 'mtop.taobao.idle.trd.ship',
                'sessionOption': 'AutoLoginOnly',
            }
            data = {'data': data_val}

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36',
                'Accept': 'application/json',
                'Accept-Language': 'zh-CN,zh;q=0.9',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': 'https://www.goofish.com',
                'Referer': 'https://www.goofish.com/',
                'cookie': self.cookies_str,
            }

            max_retries = 3
            for attempt in range(max_retries + retry_count):
                try:
                    async with aiohttp.ClientSession() as s:
                        async with s.post(
                            'https://h5api.m.goofish.com/h5/mtop.taobao.idle.trd.ship/1.0/',
                            params=params, data=data, headers=headers
                        ) as resp:
                            set_cookie = resp.headers.get('Set-Cookie', '')
                            if set_cookie:
                                self._update_cookies_from_set_cookie(set_cookie)

                            res_json = await resp.json()
                            ret = res_json.get('ret', [])

                            if ret and len(ret) > 0:
                                ret_str = ret[0] if isinstance(ret, list) else str(ret)
                                if 'SUCCESS' in ret_str:
                                    logger.info(f"【{self.cookie_id}】确认发货成功: {order_id}")
                                    return {'success': True, 'message': '确认发货成功', 'order_id': order_id}
                                elif 'FAIL_SYS_TOKEN_EXOIRED' in ret_str or '令牌过期' in ret_str:
                                    self.current_token = None
                                    self.last_token_refresh_time = 0
                                    if attempt < max_retries + retry_count - 1:
                                        await self._get_token()
                                        continue
                                    return {'success': False, 'error': 'Token过期', 'order_id': order_id}
                                else:
                                    return {'success': False, 'error': ret_str[:500], 'order_id': order_id}
                            else:
                                return {'success': False, 'error': f'未知响应: {json.dumps(res_json)[:500]}', 'order_id': order_id}
                except aiohttp.ClientError as e:
                    if attempt < max_retries + retry_count - 1:
                        await self._async_sleep(2)
                        continue
                    return {'success': False, 'error': f'网络错误: {str(e)}', 'order_id': order_id}

            return {'success': False, 'error': '确认发货重试次数已达上限', 'order_id': order_id}

        except Exception as e:
            logger.error(f"【{self.cookie_id}】确认发货异常: {str(e)}")
            return {'success': False, 'error': str(e), 'order_id': order_id}

    def _update_cookies_from_set_cookie(self, set_cookie_str):
        try:
            cookies = trans_cookies(self.cookies_str)
            for item in set_cookie_str.split(';'):
                item = item.strip()
                if '=' in item:
                    key, _, value = item.partition('=')
                    key = key.strip()
                    value = value.split(';')[0].strip()
                    if key and value:
                        cookies[key] = value
            self.cookies_str = '; '.join([f'{k}={v}' for k, v in cookies.items()])
            self.cookies = cookies
        except Exception:
            pass

    async def _async_sleep(self, seconds):
        import asyncio
        await asyncio.sleep(seconds)
