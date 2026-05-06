"""
WebSocket 连接和 Cookie 管理
"""
from __future__ import annotations
import json
import time
import asyncio
import traceback
from typing import TYPE_CHECKING, Optional, Dict, Any, List
from loguru import logger

if TYPE_CHECKING:
    from XianyuAutoAsync import ConnectionState


class ConnectionMixin:
    """WebSocket 连接和 Cookie 管理"""

    # Methods moved from XianyuLive

    def _set_connection_state(self, new_state: ConnectionState, reason: str = ""):
        """设置连接状态"""
        from XianyuAutoAsync import ConnectionState as CS
        old_state = self.connection_state
        self.connection_state = new_state

        if new_state == CS.FAILED:
            logger.error(f"[{self.cookie_id}] 连接状态: {old_state.value} -> {new_state.value}, 原因: {reason}")
        elif new_state == CS.RECONNECTING:
            logger.warning(f"[{self.cookie_id}] 连接状态: {old_state.value} -> {new_state.value}, 原因: {reason}")
        elif new_state == CS.CONNECTED:
            logger.info(f"[{self.cookie_id}] 连接状态: {old_state.value} -> {new_state.value}, 原因: {reason}")
        else:
            logger.debug(f"[{self.cookie_id}] 连接状态: {old_state.value} -> {new_state.value}, 原因: {reason}")

    async def _create_websocket_connection(self, headers):
        """创建WebSocket连接，兼容不同版本的websockets库"""
        import websockets

        websockets_version = getattr(websockets, '__version__', '未知')
        logger.warning(f"websockets库版本: {websockets_version}")

        try:
            return websockets.connect(
                self.base_url,
                extra_headers=headers
            )
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"extra_headers参数失败: {error_msg}")

            if "extra_headers" in error_msg or "unexpected keyword argument" in error_msg:
                logger.warning("websockets库不支持extra_headers参数，尝试additional_headers")
                try:
                    return websockets.connect(
                        self.base_url,
                        additional_headers=headers
                    )
                except Exception as e2:
                    error_msg2 = str(e2)
                    logger.warning(f"additional_headers参数失败: {error_msg2}")

                    if "additional_headers" in error_msg2 or "unexpected keyword argument" in error_msg2:
                        logger.warning("websockets库不支持headers参数，使用基础连接模式")
                        return websockets.connect(self.base_url)
                    else:
                        raise e2
            else:
                raise e
