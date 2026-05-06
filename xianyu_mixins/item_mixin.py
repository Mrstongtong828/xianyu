"""
商品同步和管理
"""
import json
import time
import asyncio
import traceback
from typing import Optional, Dict, Any, List
from loguru import logger


class ItemMixin:
    """商品同步和管理"""

    # Methods moved from XianyuLive
    async def save_item_info_to_db(self, item_id: str, item_detail: str = None, item_title: str = None):
        """保存商品信息到数据库

        Args:
            item_id: 商品ID
            item_detail: 商品详情内容（可以是任意格式的文本）
            item_title: 商品标题
        """
        try:
            # 跳过以 auto_ 开头的商品ID
            if item_id and item_id.startswith('auto_'):
                logger.warning(f"跳过保存自动生成的商品ID: {item_id}")
                return

            # 验证：如果只有商品ID，没有商品标题和商品详情，则不插入数据库
            if not item_title and not item_detail:
                logger.warning(f"跳过保存商品信息：缺少商品标题和详情 - {item_id}")
                return

            # 如果有商品标题但没有详情，也跳过（根据需求，需要同时有标题和详情）
            if not item_title or not item_detail:
                logger.warning(f"跳过保存商品信息：商品标题或详情不完整 - {item_id}")
                return

            from db_manager import db_manager

            # 直接使用传入的详情内容
            item_data = item_detail

            # 保存到数据库
            success = db_manager.save_item_info(self.cookie_id, item_id, item_data)
            if success:
                logger.info(f"商品信息已保存到数据库: {item_id}")
            else:
                logger.warning(f"保存商品信息到数据库失败: {item_id}")

        except Exception as e:
            logger.error(f"保存商品信息到数据库异常: {self._safe_str(e)}")

    async def _add_to_item_cache(self, item_id: str, detail: str):
        """添加商品详情到缓存，实现LRU策略和大小限制
        
        Args:
            item_id: 商品ID
            detail: 商品详情
        """
        async with self._item_detail_cache_lock:
            current_time = time.time()
            
            # 检查缓存大小，如果超过限制则清理
            if len(self._item_detail_cache) >= self._item_detail_cache_max_size:
                # 使用LRU策略删除最久未访问的项
                if self._item_detail_cache:
                    # 找到最久未访问的项
                    oldest_item = min(
                        self._item_detail_cache.items(),
                        key=lambda x: x[1].get('access_time', x[1]['timestamp'])
                    )
                    oldest_item_id = oldest_item[0]
                    del self._item_detail_cache[oldest_item_id]
                    logger.warning(f"缓存已满，删除最旧项: {oldest_item_id}")
            
            # 添加新项到缓存
            self._item_detail_cache[item_id] = {
                'detail': detail,
                'timestamp': current_time,
                'access_time': current_time
            }
            logger.warning(f"添加商品详情到缓存: {item_id}, 当前缓存大小: {len(self._item_detail_cache)}")

    async def _cleanup_item_cache(cls):
        """清理过期的商品详情缓存"""
        try:
            async with cls._item_detail_cache_lock:
                # 在持有锁时也要能响应取消信号
                await asyncio.sleep(0)
                
                current_time = time.time()
                expired_items = []
                
                # 找出所有过期的项
                for item_id, cache_data in cls._item_detail_cache.items():
                    # 在循环中也要能响应取消信号
                    await asyncio.sleep(0)
                    if current_time - cache_data['timestamp'] >= cls._item_detail_cache_ttl:
                        expired_items.append(item_id)
                
                # 删除过期项
                for item_id in expired_items:
                    await asyncio.sleep(0)  # 让出控制权
                    del cls._item_detail_cache[item_id]
                
                if expired_items:
                    logger.info(f"清理了 {len(expired_items)} 个过期的商品详情缓存")
                
                return len(expired_items)
        except asyncio.CancelledError:
            # 如果被取消，确保锁能正确释放
            raise

    async def save_items_list_to_db(self, items_list):
        """批量保存商品列表信息到数据库（并发安全）

        Args:
            items_list: 从get_item_list_info获取的商品列表
        """
        try:
            from db_manager import db_manager

            # 准备批量数据
            batch_data = []
            items_need_detail = []  # 需要获取详情的商品列表

            for item in items_list:
                item_id = item.get('id')
                if not item_id or item_id.startswith('auto_'):
                    continue

                # 构造商品详情数据
                item_detail = {
                    'title': item.get('title', ''),
                    'price': item.get('price', ''),
                    'price_text': item.get('price_text', ''),
                    'category_id': item.get('category_id', ''),
                    'auction_type': item.get('auction_type', ''),
                    'item_status': item.get('item_status', 0),
                    'detail_url': item.get('detail_url', ''),
                    'web_url': item.get('web_url', ''),  # Web可访问URL
                    'pic_info': item.get('pic_info', {}),
                    'detail_params': item.get('detail_params', {}),
                    'track_params': item.get('track_params', {}),
                    'item_label_data': item.get('item_label_data', {}),
                    'card_type': item.get('card_type', 0)
                }

                # 检查数据库中是否已有详情
                existing_item = db_manager.get_item_info(self.cookie_id, item_id)
                has_detail = existing_item and existing_item.get('item_detail') and existing_item['item_detail'].strip()

                batch_data.append({
                    'cookie_id': self.cookie_id,
                    'item_id': item_id,
                    'item_title': item.get('title', ''),
                    'item_description': '',  # 暂时为空
                    'item_category': str(item.get('category_id', '')),
                    'item_price': item.get('price_text', ''),
                    'item_detail': json.dumps(item_detail, ensure_ascii=False)
                })

                # 如果没有详情，添加到需要获取详情的列表
                if not has_detail:
                    items_need_detail.append({
                        'item_id': item_id,
                        'item_title': item.get('title', '')
                    })

            if not batch_data:
                logger.info("没有有效的商品数据需要保存")
                return 0

            # 使用批量保存方法（并发安全）
            saved_count = db_manager.batch_save_item_basic_info(batch_data)
            logger.info(f"批量保存商品信息完成: {saved_count}/{len(batch_data)} 个商品")

            # 异步获取缺失的商品详情
            if items_need_detail:
                from config import config
                auto_fetch_config = config.get('ITEM_DETAIL', {}).get('auto_fetch', {})

                if auto_fetch_config.get('enabled', True):
                    logger.info(f"发现 {len(items_need_detail)} 个商品缺少详情，开始获取...")
                    detail_success_count = await self._fetch_missing_item_details(items_need_detail)
                    logger.info(f"成功获取 {detail_success_count}/{len(items_need_detail)} 个商品的详情")
                else:
                    logger.info(f"发现 {len(items_need_detail)} 个商品缺少详情，但自动获取功能已禁用")

            return saved_count

        except Exception as e:
            logger.error(f"批量保存商品信息异常: {self._safe_str(e)}")
            return 0

    async def get_item_info(self, item_id, retry_count=0):
        """获取商品信息，自动处理token失效的情况"""
        if retry_count >= 4:  # 最多重试3次
            logger.error("获取商品信息失败，重试次数过多")
            return {"error": "获取商品信息失败，重试次数过多"}

        # 确保session已创建
        if not self.session:
            await self.create_session()

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
            'spm_cnt': 'a21ybx.im.0.0',
        }

        data_val = '{"itemId":"' + item_id + '"}'
        data = {
            'data': data_val,
        }

        # 始终从最新的cookies中获取_m_h5_tk token（刷新后cookies会被更新）
        token = trans_cookies(self.cookies_str).get('_m_h5_tk', '').split('_')[0] if trans_cookies(self.cookies_str).get('_m_h5_tk') else ''

        if token:
            logger.warning(f"使用cookies中的_m_h5_tk token: {token}")
        else:
            logger.warning("cookies中没有找到_m_h5_tk token")

        from utils.xianyu_utils import generate_sign
        sign = generate_sign(params['t'], token, data_val)
        params['sign'] = sign

        try:
            async with self.session.post(
                'https://h5api.m.goofish.com/h5/mtop.taobao.idle.pc.detail/1.0/',
                params=params,
                data=data
            ) as response:
                res_json = await response.json()

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

                logger.warning(f"商品信息获取成功: {res_json}")
                # 检查返回状态
                if isinstance(res_json, dict):
                    ret_value = res_json.get('ret', [])
                    # 检查ret是否包含成功信息
                    if not any('SUCCESS::调用成功' in ret for ret in ret_value):
                        logger.warning(f"商品信息API调用失败，错误信息: {ret_value}")

                        await asyncio.sleep(self._random_delay(0.5, 0.3))
                        return await self.get_item_info(item_id, retry_count + 1)
                    else:
                        logger.warning(f"商品信息获取成功: {item_id}")
                        return res_json
                else:
                    logger.error(f"商品信息API返回格式异常: {res_json}")
                    return await self.get_item_info(item_id, retry_count + 1)

        except Exception as e:
            logger.error(f"商品信息API请求异常: {self._safe_str(e)}")
            await asyncio.sleep(self._random_delay(0.5, 0.3))
            return await self.get_item_info(item_id, retry_count + 1)

    async def item_schedule_loop(self):
        """智能上下架定时检查循环"""
        logger.info(f"【{self.cookie_id}】智能上下架循环已启动")

        while self._running:
            try:
                await asyncio.sleep(self._randomize_interval(60, 0.2))

                from db_manager import db_manager
                pending = db_manager.get_pending_schedules()
                cookie_schedules = [s for s in pending if s.get('cookie_id') == self.cookie_id]

                for schedule in cookie_schedules:
                    schedule_id = schedule.get('id')
                    schedule_type = schedule.get('schedule_type')
                    item_id = schedule.get('item_id')
                    item_title = schedule.get('item_title', '')

                    try:
                        if schedule_type == 'list':
                            await self._list_item(item_id, item_title)
                        elif schedule_type == 'delist':
                            await self._delist_item(item_id, item_title)

                        db_manager.mark_schedule_run(schedule_id)
                        logger.info(f"【{self.cookie_id}】✅ 定时任务完成: {schedule_type} {item_title}({item_id})")

                        await self.send_delivery_failure_notification(
                            '', '', item_id,
                            f"定时{'上架' if schedule_type == 'list' else '下架'}完成: {item_title}",
                            ''
                        )
                    except Exception as e:
                        logger.error(f"【{self.cookie_id}】定时任务失败: {self._safe_str(e)}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"【{self.cookie_id}】智能上下架循环异常: {self._safe_str(e)}")
                await asyncio.sleep(self._randomize_interval(60, 0.2))

        logger.info(f"【{self.cookie_id}】智能上下架循环已停止")

    async def _list_item(self, item_id: str, item_title: str):
        try:
            api = 'mtop.idle.item.publish'
            data = {
                'api': api,
                'data': {
                    'itemId': item_id,
                    'itemStatus': '1'
                }
            }
            url = 'https://h5api.m.goofish.com/h5/' + api + '/1.0/'
            async with self.session.post(url, json=data, headers=self._get_headers()) as response:
                res_json = await response.json()
                logger.info(f"【{self.cookie_id}】上架响应: {json.dumps(res_json, ensure_ascii=False)[:200]}")
                ret = res_json.get('ret', [])
                if ret and len(ret) > 0:
                    if ret[0].get('code') == 'SUCCESS':
                        logger.info(f"【{self.cookie_id}】✅ 上架成功: {item_title}({item_id})")
                        return True
                logger.warning(f"【{self.cookie_id}】上架结果: {res_json}")
                return False
        except Exception as e:
            logger.error(f"【{self.cookie_id}】上架异常: {self._safe_str(e)}")
            return False

    async def _delist_item(self, item_id: str, item_title: str):
        try:
            api = 'mtop.idle.item.delist'
            data = {
                'api': api,
                'data': {
                    'itemId': item_id
                }
            }
            url = 'https://h5api.m.goofish.com/h5/' + api + '/1.0/'
            async with self.session.post(url, json=data, headers=self._get_headers()) as response:
                res_json = await response.json()
                logger.info(f"【{self.cookie_id}】下架响应: {json.dumps(res_json, ensure_ascii=False)[:200]}")
                ret = res_json.get('ret', [])
                if ret and len(ret) > 0:
                    if ret[0].get('code') == 'SUCCESS':
                        logger.info(f"【{self.cookie_id}】✅ 下架成功: {item_title}({item_id})")
                        return True
                logger.warning(f"【{self.cookie_id}】下架结果: {res_json}")
                return False
        except Exception as e:
            logger.error(f"【{self.cookie_id}】下架异常: {self._safe_str(e)}")
            return False

    async def item_sync_loop(self):
        """商品同步定时任务 - 按配置间隔定时同步商品信息

        支持动态配置更新：每次循环时从数据库读取最新配置
        """
        try:
            while True:
                try:
                    # 检查账号是否启用
                    from cookie_manager import manager as cookie_manager
                    if cookie_manager and not cookie_manager.get_cookie_status(self.cookie_id):
                        logger.info(f"【{self.cookie_id}】账号已禁用，停止商品同步循环")
                        break

                    # 从数据库读取最新配置（支持动态更新）
                    from db_manager import db_manager
                    item_sync_enabled_str = db_manager.get_system_setting('item_sync_enabled')
                    item_sync_interval_str = db_manager.get_system_setting('item_sync_interval')
                    item_sync_max_pages_str = db_manager.get_system_setting('item_sync_max_pages')

                    # 使用数据库配置，如果不存在则使用实例变量（从global_config.yml读取的默认值）
                    item_sync_enabled = item_sync_enabled_str == 'true' if item_sync_enabled_str is not None else self.item_sync_enabled
                    item_sync_interval = int(item_sync_interval_str) if item_sync_interval_str is not None else self.item_sync_interval
                    item_sync_max_pages = int(item_sync_max_pages_str) if item_sync_max_pages_str is not None else self.item_sync_max_pages

                    # 检查是否启用了商品同步功能
                    if not item_sync_enabled:
                        await self._interruptible_sleep(self._randomize_interval(60, 0.2))  # 未启用时每分钟检查一次
                        continue

                    # 检查距离上次同步的时间
                    current_time = time.time()
                    if current_time - self.last_item_sync_time < item_sync_interval:
                        # 未到达同步时间，等待
                        wait_time = min(60, item_sync_interval - (current_time - self.last_item_sync_time))
                        await self._interruptible_sleep(wait_time)
                        continue

                    # 使用Lock防止重复执行
                    if self.item_sync_lock.locked():
                        logger.info(f"【{self.cookie_id}】商品同步任务正在进行中，跳过本次执行")
                        await self._interruptible_sleep(self._randomize_interval(60, 0.2))
                        continue

                    # 执行商品同步
                    async with self.item_sync_lock:
                        try:
                            logger.info(f"【{self.cookie_id}】🔄 开始定时同步商品信息...")
                            result = await self.get_all_items(page_size=20, max_pages=item_sync_max_pages)

                            if result.get('success'):
                                total_count = result.get('total_count', 0)
                                saved_count = result.get('total_saved', 0)
                                self.last_item_sync_time = current_time
                                logger.info(f"【{self.cookie_id}】✅ 商品同步完成: 共 {total_count} 件商品，保存/更新 {saved_count} 件")
                            else:
                                error_msg = result.get('error', '未知错误')
                                logger.warning(f"【{self.cookie_id}】❌ 商品同步失败: {error_msg}")

                        except asyncio.CancelledError:
                            logger.info(f"【{self.cookie_id}】商品同步被取消")
                            raise
                        except Exception as sync_error:
                            logger.error(f"【{self.cookie_id}】商品同步异常: {self._safe_str(sync_error)}")

                    # 等待下次同步时间
                    await self._interruptible_sleep(self._randomize_interval(item_sync_interval, 0.2))

                except asyncio.CancelledError:
                    # 收到取消信号，立即退出循环
                    logger.info(f"【{self.cookie_id}】商品同步循环收到取消信号，准备退出")
                    raise
                except Exception as e:
                    logger.error(f"【{self.cookie_id}】商品同步任务失败: {self._safe_str(e)}")
                    # 出错后等待1分钟再重试
                    try:
                        await self._interruptible_sleep(self._randomize_interval(60, 0.2))
                    except asyncio.CancelledError:
                        logger.info(f"【{self.cookie_id}】商品同步循环在重试等待时收到取消信号，准备退出")
                        raise
        except asyncio.CancelledError:
            # 确保CancelledError被正确传播
            logger.info(f"【{self.cookie_id}】商品同步循环已取消，正在退出...")
            raise
        finally:
            # 确保任务能正常结束
            logger.info(f"【{self.cookie_id}】商品同步循环已退出")


    async def get_item_list_info(self, page_number=1, page_size=20, retry_count=0):
        """获取商品信息，自动处理token失效的情况

        Args:
            page_number (int): 页码，从1开始
            page_size (int): 每页数量，默认20
            retry_count (int): 重试次数，内部使用
        """
        if retry_count >= 4:  # 最多重试3次
            logger.error("获取商品信息失败，重试次数过多")
            return {"error": "获取商品信息失败，重试次数过多"}

        # 确保session已创建
        if not self.session:
            await self.create_session()

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
            'api': 'mtop.idle.web.xyh.item.list',
            'sessionOption': 'AutoLoginOnly',
            'spm_cnt': 'a21ybx.im.0.0',
            'spm_pre': 'a21ybx.collection.menu.1.272b5141NafCNK'
        }

        data = {
            'needGroupInfo': False,
            'pageNumber': page_number,
            'pageSize': page_size,
            'groupName': '在售',
            'groupId': '58877261',
            'defaultGroup': True,
            "userId": self.myid
        }

        # 始终从最新的cookies中获取_m_h5_tk token（刷新后cookies会被更新）
        token = trans_cookies(self.cookies_str).get('_m_h5_tk', '').split('_')[0] if trans_cookies(self.cookies_str).get('_m_h5_tk') else ''

        logger.warning(f"准备获取商品列表，token: {token}")
        if token:
            logger.warning(f"使用cookies中的_m_h5_tk token: {token}")
        else:
            logger.warning("cookies中没有找到_m_h5_tk token")

        # 生成签名
        data_val = json.dumps(data, separators=(',', ':'))
        sign = generate_sign(params['t'], token, data_val)
        params['sign'] = sign

        try:
            async with self.session.post(
                'https://h5api.m.goofish.com/h5/mtop.idle.web.xyh.item.list/1.0/',
                params=params,
                data={'data': data_val}
            ) as response:
                res_json = await response.json()

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

                logger.info(f"商品信息获取响应: {res_json}")

                # 检查响应是否成功
                if res_json.get('ret') and res_json['ret'][0] == 'SUCCESS::调用成功':
                    items_data = res_json.get('data', {})
                    # 从cardList中提取商品信息
                    card_list = items_data.get('cardList', [])

                    # 解析cardList中的商品信息
                    items_list = []
                    for card in card_list:
                        card_data = card.get('cardData', {})
                        if card_data:
                            # 提取商品基本信息
                            detail_params = card_data.get('detailParams', {})
                            item_id = detail_params.get('itemId', card_data.get('id', ''))

                            item_info = {
                                'id': item_id,
                                'title': card_data.get('title', ''),
                                'price': card_data.get('priceInfo', {}).get('price', ''),
                                'price_text': card_data.get('priceInfo', {}).get('preText', '') + card_data.get('priceInfo', {}).get('price', ''),
                                'category_id': card_data.get('categoryId', ''),
                                'auction_type': card_data.get('auctionType', ''),
                                'item_status': card_data.get('itemStatus', 0),
                                'detail_url': card_data.get('detailUrl', ''),
                                # Web可访问的商品URL（用于浏览器打开）
                                'web_url': f'https://www.goofish.com/item?id={item_id}',
                                'pic_info': card_data.get('picInfo', {}),
                                'detail_params': detail_params,
                                'track_params': card_data.get('trackParams', {}),
                                'item_label_data': card_data.get('itemLabelDataVO', {}),
                                'card_type': card.get('cardType', 0)
                            }
                            items_list.append(item_info)

                    logger.info(f"成功获取到 {len(items_list)} 个商品")

                    # 打印商品详细信息到控制台
                    print("\n" + "="*80)
                    print(f"📦 账号 {self.myid} 的商品列表 (第{page_number}页，{len(items_list)} 个商品)")
                    print("="*80)

                    for i, item in enumerate(items_list, 1):
                        print(f"\n🔸 商品 {i}:")
                        print(f"   商品ID: {item.get('id', 'N/A')}")
                        print(f"   商品标题: {item.get('title', 'N/A')}")
                        print(f"   价格: {item.get('price_text', 'N/A')}")
                        print(f"   分类ID: {item.get('category_id', 'N/A')}")
                        print(f"   商品状态: {item.get('item_status', 'N/A')}")
                        print(f"   拍卖类型: {item.get('auction_type', 'N/A')}")
                        print(f"   详情链接: {item.get('detail_url', 'N/A')}")
                        if item.get('pic_info'):
                            pic_info = item['pic_info']
                            print(f"   图片信息: {pic_info.get('width', 'N/A')}x{pic_info.get('height', 'N/A')}")
                            print(f"   图片链接: {pic_info.get('picUrl', 'N/A')}")
                        print(f"   完整信息: {json.dumps(item, ensure_ascii=False, indent=2)}")

                    print("\n" + "="*80)
                    print("✅ 商品列表获取完成")
                    print("="*80)

                    # 自动保存商品信息到数据库
                    if items_list:
                        saved_count = await self.save_items_list_to_db(items_list)
                        logger.info(f"已将 {saved_count} 个商品信息保存到数据库")

                    return {
                        "success": True,
                        "page_number": page_number,
                        "page_size": page_size,
                        "current_count": len(items_list),
                        "items": items_list,
                        "saved_count": saved_count if items_list else 0,
                        "raw_data": items_data  # 保留原始数据以备调试
                    }
                else:
                    # 检查是否是token失效
                    error_msg = res_json.get('ret', [''])[0] if res_json.get('ret') else ''
                    if 'FAIL_SYS_TOKEN_EXOIRED' in error_msg or 'token' in error_msg.lower():
                        logger.warning(f"Token失效，准备重试: {error_msg}")
                        await asyncio.sleep(self._random_delay(0.5, 0.3))
                        return await self.get_item_list_info(page_number, page_size, retry_count + 1)
                    else:
                        logger.error(f"获取商品信息失败: {res_json}")
                        return {"error": f"获取商品信息失败: {error_msg}"}

        except Exception as e:
            logger.error(f"商品信息API请求异常: {self._safe_str(e)}")
            await asyncio.sleep(self._random_delay(0.5, 0.3))
            return await self.get_item_list_info(page_number, page_size, retry_count + 1)

    async def get_all_items(self, page_size=20, max_pages=None):
        """获取所有商品信息（自动分页）

        Args:
            page_size (int): 每页数量，默认20
            max_pages (int): 最大页数限制，None表示无限制

        Returns:
            dict: 包含所有商品信息的字典
        """
        all_items = []
        page_number = 1
        total_saved = 0

        logger.info(f"开始获取所有商品信息，每页{page_size}条")

        while True:
            if max_pages and page_number > max_pages:
                logger.info(f"达到最大页数限制 {max_pages}，停止获取")
                break

            logger.info(f"正在获取第 {page_number} 页...")
            result = await self.get_item_list_info(page_number, page_size)

            if not result.get("success"):
                logger.error(f"获取第 {page_number} 页失败: {result}")
                break

            current_items = result.get("items", [])
            if not current_items:
                logger.info(f"第 {page_number} 页没有数据，获取完成")
                break

            all_items.extend(current_items)
            total_saved += result.get("saved_count", 0)

            logger.info(f"第 {page_number} 页获取到 {len(current_items)} 个商品")

            # 如果当前页商品数量少于页面大小，说明已经是最后一页
            if len(current_items) < page_size:
                logger.info(f"第 {page_number} 页商品数量({len(current_items)})少于页面大小({page_size})，获取完成")
                break

            page_number += 1

            # 添加延迟避免请求过快
            await asyncio.sleep(self._random_delay(1.0, 0.3))

        logger.info(f"所有商品获取完成，共 {len(all_items)} 个商品，保存了 {total_saved} 个")

        return {
            "success": True,
            "total_pages": page_number,
            "total_count": len(all_items),
            "total_saved": total_saved,
            "items": all_items
        }

