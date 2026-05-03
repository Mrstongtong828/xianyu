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
