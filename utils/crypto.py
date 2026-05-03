"""
敏感字段加密工具模块
使用 Fernet 对称加密保护数据库中存储的闲鱼账号密码等敏感信息
密钥从环境变量 SENSITIVE_KEY 读取，未设置时自动生成并持久化到 data/.sensitive_key
"""

import os
import base64
from loguru import logger

_KEY_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', '.sensitive_key')
_fernet = None


def _load_or_create_key() -> bytes:
    """加载或创建加密密钥"""
    # 优先从环境变量读取
    env_key = os.getenv('SENSITIVE_KEY')
    if env_key:
        try:
            key = base64.urlsafe_b64decode(env_key.encode())
            if len(key) == 32:
                return base64.urlsafe_b64encode(key)
        except Exception:
            logger.warning("环境变量 SENSITIVE_KEY 格式无效，忽略")

    # 从文件读取
    if os.path.exists(_KEY_FILE):
        try:
            with open(_KEY_FILE, 'rb') as f:
                key = f.read().strip()
            if len(key) == 44:  # Fernet key base64 length
                return key
        except Exception:
            logger.warning("读取密钥文件失败，将重新生成")

    # 生成新密钥并持久化
    from cryptography.fernet import Fernet
    key = Fernet.generate_key()
    try:
        os.makedirs(os.path.dirname(_KEY_FILE), exist_ok=True)
        with open(_KEY_FILE, 'wb') as f:
            f.write(key)
        # Windows 下也尝试设置文件权限为仅当前用户可读
        try:
            import stat
            os.chmod(_KEY_FILE, stat.S_IRUSR | stat.S_IWUSR)
        except Exception:
            pass
        logger.info(f"已生成新加密密钥并保存到: {_KEY_FILE}")
    except Exception as e:
        logger.error(f"保存密钥文件失败: {e}")
    return key


def _get_fernet():
    global _fernet
    if _fernet is None:
        from cryptography.fernet import Fernet
        _fernet = Fernet(_load_or_create_key())
    return _fernet


def encrypt_value(plaintext: str) -> str:
    """加密字符串，返回 base64 编码的密文。空字符串直接返回空字符串。"""
    if not plaintext:
        return ''
    try:
        f = _get_fernet()
        return f.encrypt(plaintext.encode('utf-8')).decode('ascii')
    except Exception as e:
        logger.warning(f"加密失败，数据将以明文存储: {e}")
        return plaintext  # 降级：返回原文


def decrypt_value(ciphertext: str) -> str:
    """解密 base64 编码的密文，返回明文。空字符串直接返回空字符串。
    如果解密失败（如旧数据未加密），返回原文以兼容历史数据。"""
    if not ciphertext:
        return ''
    try:
        f = _get_fernet()
        return f.decrypt(ciphertext.encode('ascii')).decode('utf-8')
    except Exception:
        # 兼容未加密的历史数据：如果看起来不像 Fernet 密文，直接返回原文
        logger.warning("解密失败，返回原始数据（可能是未加密的历史数据）")
        return ciphertext
