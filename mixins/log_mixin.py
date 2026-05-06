"""
Log Mixin - 风控日志管理
"""
import sqlite3
import json
import time
import secrets
from typing import Optional, Dict, Any, List, Tuple
from loguru import logger


class LogManagerMixin:
    """风控日志管理"""

    def add_risk_control_log(self, cookie_id: str, event_type: str = 'slider_captcha',
                           event_description: str = None, processing_result: str = None,
                           processing_status: str = 'processing', error_message: str = None) -> bool:
        """
        添加风控日志记录

        Args:
            cookie_id: Cookie ID
            event_type: 事件类型，默认为'slider_captcha'
            event_description: 事件描述
            processing_result: 处理结果
            processing_status: 处理状态 ('processing', 'success', 'failed')
            error_message: 错误信息

        Returns:
            bool: 添加成功返回True，失败返回False
        """
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                    INSERT INTO risk_control_logs
                    (cookie_id, event_type, event_description, processing_result, processing_status, error_message)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (cookie_id, event_type, event_description, processing_result, processing_status, error_message))
                self.conn.commit()
                return True
        except Exception as e:
            logger.error(f"添加风控日志失败: {e}")
            return False



    def update_risk_control_log(self, log_id: int, processing_result: str = None,
                              processing_status: str = None, error_message: str = None) -> bool:
        """
        更新风控日志记录

        Args:
            log_id: 日志ID
            processing_result: 处理结果
            processing_status: 处理状态
            error_message: 错误信息

        Returns:
            bool: 更新成功返回True，失败返回False
        """
        try:
            with self.lock:
                cursor = self.conn.cursor()

                # 构建更新语句
                update_fields = []
                params = []

                if processing_result is not None:
                    update_fields.append("processing_result = ?")
                    params.append(processing_result)

                if processing_status is not None:
                    update_fields.append("processing_status = ?")
                    params.append(processing_status)

                if error_message is not None:
                    update_fields.append("error_message = ?")
                    params.append(error_message)

                if update_fields:
                    update_fields.append("updated_at = CURRENT_TIMESTAMP")
                    params.append(log_id)

                    sql = f"UPDATE risk_control_logs SET {', '.join(update_fields)} WHERE id = ?"
                    cursor.execute(sql, params)
                    self.conn.commit()
                    return cursor.rowcount > 0

                return False
        except Exception as e:
            logger.error(f"更新风控日志失败: {e}")
            return False



    def get_risk_control_logs(self, cookie_id: str = None, limit: int = 100, offset: int = 0) -> List[Dict]:
        """
        获取风控日志列表

        Args:
            cookie_id: Cookie ID，为None时获取所有日志
            limit: 限制返回数量
            offset: 偏移量

        Returns:
            List[Dict]: 风控日志列表
        """
        try:
            with self.lock:
                cursor = self.conn.cursor()

                if cookie_id:
                    cursor.execute('''
                        SELECT r.*, c.id as cookie_name
                        FROM risk_control_logs r
                        LEFT JOIN cookies c ON r.cookie_id = c.id
                        WHERE r.cookie_id = ?
                        ORDER BY r.created_at DESC
                        LIMIT ? OFFSET ?
                    ''', (cookie_id, limit, offset))
                else:
                    cursor.execute('''
                        SELECT r.*, c.id as cookie_name
                        FROM risk_control_logs r
                        LEFT JOIN cookies c ON r.cookie_id = c.id
                        ORDER BY r.created_at DESC
                        LIMIT ? OFFSET ?
                    ''', (limit, offset))

                columns = [description[0] for description in cursor.description]
                logs = []

                for row in cursor.fetchall():
                    log_info = dict(zip(columns, row))
                    logs.append(log_info)

                return logs
        except Exception as e:
            logger.error(f"获取风控日志失败: {e}")
            return []



    def get_risk_control_logs_count(self, cookie_id: str = None) -> int:
        """
        获取风控日志总数

        Args:
            cookie_id: Cookie ID，为None时获取所有日志数量

        Returns:
            int: 日志总数
        """
        try:
            with self.lock:
                cursor = self.conn.cursor()

                if cookie_id:
                    cursor.execute('SELECT COUNT(*) FROM risk_control_logs WHERE cookie_id = ?', (cookie_id,))
                else:
                    cursor.execute('SELECT COUNT(*) FROM risk_control_logs')

                return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"获取风控日志数量失败: {e}")
            return 0



    def delete_risk_control_log(self, log_id: int) -> bool:
        """
        删除风控日志记录

        Args:
            log_id: 日志ID

        Returns:
            bool: 删除成功返回True，失败返回False
        """
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute('DELETE FROM risk_control_logs WHERE id = ?', (log_id,))
                self.conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"删除风控日志失败: {e}")
            return False
    


    def get_operation_logs(self, cookie_id: str = None, log_type: str = None,
                           page: int = 1, page_size: int = 50) -> dict:
        """获取操作日志"""
        try:
            with self.lock:
                cursor = self.conn.cursor()
                conditions = []
                params = []
                if cookie_id:
                    conditions.append('cookie_id = ?')
                    params.append(cookie_id)
                if log_type:
                    conditions.append('event_type = ?')
                    params.append(log_type)

                where = ' WHERE ' + ' AND '.join(conditions) if conditions else ''

                cursor.execute(f'SELECT COUNT(*) FROM risk_control_logs {where}', params)
                total = cursor.fetchone()[0]

                offset = (page - 1) * page_size
                cursor.execute(f'''
                    SELECT * FROM risk_control_logs {where}
                    ORDER BY created_at DESC LIMIT ? OFFSET ?
                ''', params + [page_size, offset])
                rows = cursor.fetchall()
                columns = [d[0] for d in cursor.description]
                return {
                    'data': [dict(zip(columns, row)) for row in rows],
                    'total': total,
                    'page': page,
                    'page_size': page_size
                }
        except Exception as e:
            logger.error(f"获取操作日志失败: {e}")
            return {'data': [], 'total': 0, 'page': page, 'page_size': page_size}

