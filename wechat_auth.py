import time
import uuid
import requests
import qrcode
import io
import base64
from loguru import logger
from db_manager import db_manager


class WechatAuth:
    def __init__(self, app_id: str, app_secret: str, redirect_uri: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self.redirect_uri = redirect_uri

    def is_configured(self) -> bool:
        return bool(self.app_id and self.app_secret)

    def generate_login_state(self) -> str:
        state = uuid.uuid4().hex
        expires_at = time.time() + 300
        db_manager.conn.execute(
            "INSERT INTO wechat_login_states (state, expires_at) VALUES (?, ?)",
            (state, expires_at)
        )
        db_manager.conn.commit()
        return state

    def get_qrcode_base64(self, state: str) -> str:
        url = (
            f"https://open.weixin.qq.com/connect/qrconnect"
            f"?appid={self.app_id}"
            f"&redirect_uri={self.redirect_uri}"
            f"&response_type=code"
            f"&scope=snsapi_login"
            f"&state={state}"
            f"#wechat_redirect"
        )
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return base64.b64encode(buf.getvalue()).decode()

    def check_state(self, state: str) -> bool:
        cursor = db_manager.conn.cursor()
        cursor.execute(
            "SELECT used, expires_at FROM wechat_login_states WHERE state = ?",
            (state,)
        )
        row = cursor.fetchone()
        if not row:
            return False
        used, expires_at = row
        if used or expires_at < time.time():
            return False
        return True

    def mark_state_used(self, state: str):
        db_manager.conn.execute(
            "UPDATE wechat_login_states SET used = TRUE WHERE state = ?",
            (state,)
        )
        db_manager.conn.commit()

    def get_access_token(self, code: str) -> dict:
        url = "https://api.weixin.qq.com/sns/oauth2/access_token"
        params = {
            "appid": self.app_id,
            "secret": self.app_secret,
            "code": code,
            "grant_type": "authorization_code"
        }
        resp = requests.get(url, params=params, timeout=10)
        return resp.json()

    def get_user_info(self, access_token: str, openid: str) -> dict:
        url = "https://api.weixin.qq.com/sns/userinfo"
        params = {
            "access_token": access_token,
            "openid": openid
        }
        resp = requests.get(url, params=params, timeout=10)
        return resp.json()

    def get_user_by_openid(self, openid: str) -> dict:
        cursor = db_manager.conn.cursor()
        cursor.execute(
            "SELECT id, username, email, is_active FROM users WHERE wechat_openid = ?",
            (openid,)
        )
        row = cursor.fetchone()
        if row:
            return {
                'id': row[0],
                'username': row[1],
                'email': row[2],
                'is_active': row[3],
                'is_admin': row[1] == 'admin'
            }
        return None

    def bind_wechat(self, user_id: int, openid: str, unionid: str = None, nickname: str = '', avatar_url: str = ''):
        updates = ["wechat_openid = ?", "wechat_bound_at = ?"]
        params = [openid, time.time()]
        if unionid:
            updates.append("wechat_unionid = ?")
            params.append(unionid)
        if nickname:
            updates.append("wechat_nickname = ?")
            params.append(nickname)
        if avatar_url:
            updates.append("wechat_avatar_url = ?")
            params.append(avatar_url)
        params.append(user_id)
        db_manager.conn.execute(
            f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
            params
        )
        db_manager.conn.commit()
        logger.info(f"用户 {user_id} 已绑定微信 openid={openid[:10]}...")

    def unbind_wechat(self, user_id: int):
        db_manager.conn.execute(
            "UPDATE users SET wechat_openid = NULL, wechat_unionid = NULL, wechat_nickname = '', wechat_avatar_url = '', wechat_bound_at = 0 WHERE id = ?",
            (user_id,)
        )
        db_manager.conn.commit()
        logger.info(f"用户 {user_id} 已解绑微信")

    def get_wechat_info(self, user_id: int) -> dict:
        cursor = db_manager.conn.cursor()
        cursor.execute(
            "SELECT wechat_openid, wechat_nickname, wechat_avatar_url, wechat_bound_at FROM users WHERE id = ?",
            (user_id,)
        )
        row = cursor.fetchone()
        if row and row[0]:
            return {
                'bound': True,
                'openid': row[0][:10] + '...' if row[0] else '',
                'nickname': row[1] or '',
                'avatar_url': row[2] or '',
                'bound_at': row[3] or 0
            }
        return {'bound': False}


wechat_auth = None

def init_wechat_auth():
    global wechat_auth
    from config import WECHAT_CONFIG
    app_id = WECHAT_CONFIG.get('app_id', '')
    app_secret = WECHAT_CONFIG.get('app_secret', '')
    redirect_uri = WECHAT_CONFIG.get('redirect_uri', '')
    if app_id and app_secret:
        wechat_auth = WechatAuth(app_id, app_secret, redirect_uri)
        logger.info("微信登录模块已初始化")
    else:
        logger.info("微信登录未配置（缺少app_id或app_secret）")
