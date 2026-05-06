# -*- coding: utf-8 -*-
"""
EVALUATION DAO Mixin
"""

from loguru import logger
import sqlite3
import time
from typing import List, Tuple, Dict, Optional, Any


class EvaluationDAOMixin:
    """EVALUATION related database operations"""

    def get_evaluation_config(self, cookie_id: str) -> dict:
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM evaluation_config WHERE cookie_id = ?', (cookie_id,))
            row = cursor.fetchone()
            if row:
                columns = [d[0] for d in cursor.description]
                return dict(zip(columns, row))
            return {'auto_evaluate_enabled': False, 'evaluate_content': '感谢您的购买，欢迎再次光临！', 'auto_reply_review_enabled': False, 'reply_review_content': '感谢支持！'}



