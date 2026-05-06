#!/usr/bin/env python3
"""
基于文件监控的日志收集器
"""

import os
import re
import time
import threading
from collections import deque
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path

class FileLogCollector:
    """基于文件监控的日志收集器"""
    
    def __init__(self, max_logs: int = 2000):
        self.max_logs = max_logs
        self.logs = deque(maxlen=max_logs)
        self.lock = threading.Lock()
        
        # 日志文件路径
        self.log_file = None
        self.last_position = 0
        
        # 启动文件监控
        self.setup_file_monitoring()
    
    def setup_file_monitoring(self):
        """设置文件监控"""
        # 查找日志文件
        possible_files = [
            "xianyu.log",
            "app.log", 
            "system.log",
            "logs/xianyu.log",
            "logs/app.log"
        ]
        
        for file_path in possible_files:
            if os.path.exists(file_path):
                self.log_file = file_path
                break
        
        if not self.log_file:
            # 如果没有找到现有文件，创建一个新的
            self.log_file = "realtime.log"
            
        # 设置loguru输出到文件
        self.setup_loguru_file_output()
        
        # 启动文件监控线程
        self.monitor_thread = threading.Thread(target=self.monitor_file, daemon=True)
        self.monitor_thread.start()
    
    def setup_loguru_file_output(self):
        """设置loguru输出到文件"""
        try:
            from loguru import logger

            logger.add(
                self.log_file,
                format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {name}:{function}:{line} - {message}",
                level="INFO",
                rotation="10 MB",
                retention="3 days",
                enqueue=False,
                buffering=1
            )

            logger.info("文件日志收集器已启动")
        except ImportError:
            pass

    def _recover_log_file(self):
        """当日志文件丢失时尝试恢复"""
        self.last_position = 0
        if os.path.exists(self.log_file):
            try:
                self.last_position = os.path.getsize(self.log_file)
                logger.debug(f"日志文件恢复，当前位置: {self.last_position}")
            except Exception:
                pass
        else:
            self.setup_loguru_file_output()
            logger.warning("日志文件丢失，已重新创建")
    
    def monitor_file(self):
        """监控日志文件变化（支持文件轮转恢复）"""
        stale_counter = 0
        max_stale_checks = 10  # 连续5秒无变化后重新检测文件

        while True:
            try:
                if not os.path.exists(self.log_file):
                    # 日志文件被删除或轮转，尝试寻找新文件
                    stale_counter += 1
                    if stale_counter > 3:
                        self._recover_log_file()
                        stale_counter = 0
                    time.sleep(1)
                    continue

                file_size = os.path.getsize(self.log_file)

                # 检测文件被截断（轮转时文件清空重新写入）
                if file_size < self.last_position:
                    logger.debug("检测到日志文件被截断（可能发生了轮转），重置读取位置")
                    self.last_position = 0
                    stale_counter = 0

                if file_size > self.last_position:
                    stale_counter = 0
                    try:
                        with open(self.log_file, 'r', encoding='utf-8') as f:
                            f.seek(self.last_position)
                            new_lines = f.readlines()
                            self.last_position = f.tell()
                    except (IOError, OSError) as io_err:
                        logger.debug(f"读取日志文件失败: {io_err}")
                        time.sleep(0.5)
                        continue
                    except UnicodeDecodeError:
                        self.last_position = file_size
                        time.sleep(0.5)
                        continue

                    for line in new_lines:
                        self.parse_log_line(line.strip())
                else:
                    stale_counter += 1
                    if stale_counter >= max_stale_checks:
                        # 长时间无变化，检查文件是否仍然有效
                        self.last_position = 0
                        stale_counter = 0

                time.sleep(0.5)

            except Exception as e:
                stale_counter += 1
                time.sleep(1)
    
    def parse_log_line(self, line: str):
        """解析日志行"""
        if not line:
            return
        
        try:
            # 解析loguru格式的日志
            # 格式: 2025-07-23 15:46:03.430 | INFO | __main__:debug_collector:70 - 消息
            pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) \| (\w+) \| ([^:]+):([^:]+):(\d+) - (.*)'
            match = re.match(pattern, line)
            
            if match:
                timestamp_str, level, source, function, line_num, message = match.groups()
                
                # 转换时间格式
                try:
                    timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S.%f')
                except Exception:
                    timestamp = datetime.now()
                
                log_entry = {
                    "timestamp": timestamp.isoformat(),
                    "level": level,
                    "source": source,
                    "function": function,
                    "line": int(line_num),
                    "message": message
                }
                
                with self.lock:
                    self.logs.append(log_entry)
            
        except Exception as e:
            # 如果解析失败，作为普通消息处理
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "level": "INFO",
                "source": "system",
                "function": "unknown",
                "line": 0,
                "message": line
            }
            
            with self.lock:
                self.logs.append(log_entry)
    
    def get_logs(self, lines: int = 200, level_filter: str = None, source_filter: str = None) -> List[Dict]:
        """获取日志记录"""
        with self.lock:
            logs_list = list(self.logs)
        
        # 应用过滤器
        if level_filter:
            logs_list = [log for log in logs_list if log['level'] == level_filter]
        
        if source_filter:
            logs_list = [log for log in logs_list if source_filter.lower() in log['source'].lower()]
        
        # 返回最后N行
        return logs_list[-lines:] if len(logs_list) > lines else logs_list
    
    def clear_logs(self):
        """清空日志"""
        with self.lock:
            self.logs.clear()
    
    def get_stats(self) -> Dict:
        """获取日志统计信息"""
        with self.lock:
            total_logs = len(self.logs)
            
            # 统计各级别日志数量
            level_counts = {}
            source_counts = {}
            
            for log in self.logs:
                level = log['level']
                source = log['source']
                
                level_counts[level] = level_counts.get(level, 0) + 1
                source_counts[source] = source_counts.get(source, 0) + 1
            
            return {
                "total_logs": total_logs,
                "level_counts": level_counts,
                "source_counts": source_counts,
                "max_capacity": self.max_logs,
                "log_file": self.log_file
            }


# 全局文件日志收集器实例
_file_collector = None
_file_collector_lock = threading.Lock()


def get_file_log_collector() -> FileLogCollector:
    """获取全局文件日志收集器实例"""
    global _file_collector
    
    if _file_collector is None:
        with _file_collector_lock:
            if _file_collector is None:
                _file_collector = FileLogCollector(max_logs=2000)
    
    return _file_collector


def setup_file_logging():
    """设置文件日志系统"""
    collector = get_file_log_collector()
    return collector


if __name__ == "__main__":
    # 测试文件日志收集器
    collector = setup_file_logging()
    
    # 生成一些测试日志
    from loguru import logger
    
    logger.info("文件日志收集器测试开始")
    logger.debug("这是调试信息")
    logger.warning("这是警告信息")
    logger.error("这是错误信息")
    logger.info("文件日志收集器测试结束")
    
    # 等待文件写入和监控
    time.sleep(2)
    
    # 获取日志
    logs = collector.get_logs(10)
    print(f"收集到 {len(logs)} 条日志:")
    for log in logs:
        print(f"  [{log['level']}] {log['source']}: {log['message']}")
    
    # 获取统计信息
    stats = collector.get_stats()
    print(f"\n统计信息: {stats}")
