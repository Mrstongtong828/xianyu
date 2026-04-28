import os
import json
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

from XianyuAgent import XianyuReplyBot as _Bot

_bot: Optional[_Bot] = None


def _get_bot() -> _Bot:
    global _bot
    if _bot is None:
        _bot = _Bot()
    return _bot


async def agent_get_reply(
    send_message: str,
    item_info: dict,
    chat_id: str,
    cookie_id: str,
) -> Optional[str]:
    from ai_reply_engine import ai_reply_engine
    from db_manager import db_manager
    settings = db_manager.get_ai_reply_settings(cookie_id)
    os.environ["OPENAI_API_KEY"] = settings.get("api_key", "")
    os.environ["OPENAI_BASE_URL"] = settings.get("base_url", "https://api.deepseek.com/v1")
    os.environ["MODEL_NAME"] = settings.get("model_name", "deepseek-chat")
    context = ai_reply_engine.get_conversation_context(chat_id, cookie_id)

    item_desc = json.dumps({
        "title":       item_info.get("title", ""),
        "description": item_info.get("desc", ""),
        "price":       item_info.get("price", 0),
    }, ensure_ascii=False)

    # generate_reply 是同步函数，用 to_thread 避免阻塞事件循环
    reply = await asyncio.to_thread(
        _get_bot().generate_reply,
        send_message,
        item_desc,
        context,
    )
    return None if reply == "-" else reply
