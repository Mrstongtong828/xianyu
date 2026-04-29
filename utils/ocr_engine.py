"""PaddleOCR 离线图片文字识别引擎（懒加载）"""
import logging
from pathlib import Path
from io import BytesIO
from typing import Optional

logger = logging.getLogger("ocr_engine")

_ocr_instance = None
_ocr_available = None


def _init_ocr():
    """懒初始化 PaddleOCR（首次调用时才加载模型，节省内存）"""
    global _ocr_instance, _ocr_available
    if _ocr_available is not None:
        return _ocr_available

    try:
        from paddleocr import PaddleOCR
        _ocr_instance = PaddleOCR(
            use_angle_cls=True,
            lang='ch',
            use_gpu=False,
            show_log=False,
            use_space_char=True,
        )
        # 预热：加载后先跑一次空调用确保模型就绪
        _ocr_instance.ocr(_create_blank_image(), cls=True)
        _ocr_available = True
        logger.info("PaddleOCR 引擎初始化成功（CPU 模式）")
    except ImportError:
        logger.warning("PaddleOCR 未安装，图片识别功能不可用。安装: pip install paddlepaddle paddleocr")
        _ocr_available = False
    except Exception as e:
        logger.warning(f"PaddleOCR 初始化失败: {e}，图片识别功能不可用")
        _ocr_available = False

    return _ocr_available


def _create_blank_image():
    """创建一张空白图片用于预热"""
    from PIL import Image
    img = Image.new('RGB', (100, 100), color='white')
    buf = BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def ocr_from_bytes(image_bytes: bytes) -> Optional[str]:
    """对图片字节流进行 OCR 识别，返回文本

    Args:
        image_bytes: 图片二进制数据

    Returns:
        识别出的文本，失败或无结果返回 None
    """
    if not _init_ocr():
        return None

    try:
        result = _ocr_instance.ocr(image_bytes, cls=True)
        if not result or not result[0]:
            return None

        lines = []
        for line_info in result[0]:
            if line_info and len(line_info) >= 2:
                text = line_info[1][0] if isinstance(line_info[1], (list, tuple)) else str(line_info[1])
                if text and text.strip():
                    lines.append(text.strip())

        return '\n'.join(lines) if lines else None

    except Exception as e:
        logger.error(f"OCR 识别失败: {e}")
        return None


def ocr_from_url(url: str, timeout: int = 15) -> Optional[str]:
    """从 URL 下载图片并进行 OCR 识别

    Args:
        url: 图片 URL
        timeout: 下载超时时间（秒）

    Returns:
        识别出的文本，失败或无结果返回 None
    """
    try:
        import requests
        resp = requests.get(url, timeout=timeout, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'image/webp,image/png,image/jpeg,image/*;q=0.8',
        })
        resp.raise_for_status()

        content_type = resp.headers.get('Content-Type', '').lower()
        if not any(t in content_type for t in ('image', 'octet-stream')):
            logger.warning(f"OCR: URL 返回非图片内容 ({content_type}): {url[:100]}")
            return None

        if len(resp.content) < 100:
            logger.warning(f"OCR: 下载的图片太小 ({len(resp.content)} bytes)")
            return None

        return ocr_from_bytes(resp.content)

    except Exception as e:
        logger.error(f"OCR: 下载图片失败 ({url[:100]}): {e}")
        return None


async def ocr_from_url_async(url: str, timeout: int = 15) -> Optional[str]:
    """异步版本的 URL OCR 识别"""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout), headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'image/webp,image/png,image/jpeg,image/*;q=0.8',
            }) as resp:
                resp.raise_for_status()
                data = await resp.read()
                if len(data) < 100:
                    logger.warning(f"OCR: 下载的图片太小 ({len(data)} bytes)")
                    return None
                return ocr_from_bytes(data)
    except Exception as e:
        logger.error(f"OCR: 下载图片失败 ({url[:100]}): {e}")
        return None


def is_available() -> bool:
    """检查 OCR 引擎是否可用"""
    return _init_ocr()
