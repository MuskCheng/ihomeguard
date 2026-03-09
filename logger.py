"""统一日志模块"""
import logging
import sys
import os

# 日志格式
LOG_FORMAT = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# 全局 logger 缓存
_loggers = {}


def get_logger(name: str = 'ihomeguard') -> logging.Logger:
    """获取 logger 实例
    
    Args:
        name: logger 名称，默认为 'ihomeguard'
    
    Returns:
        配置好的 logger 实例
    """
    if name in _loggers:
        return _loggers[name]
    
    logger = logging.getLogger(name)
    
    # 避免重复添加 handler
    if logger.handlers:
        _loggers[name] = logger
        return logger
    
    # 日志级别从环境变量读取，默认 INFO
    log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
    logger.setLevel(getattr(logging, log_level, logging.INFO))
    
    # 控制台输出
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    logger.addHandler(console_handler)
    
    # 防止日志向上传播
    logger.propagate = False
    
    _loggers[name] = logger
    return logger


def set_log_level(level: str):
    """动态设置日志级别
    
    Args:
        level: 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
    """
    for logger in _loggers.values():
        logger.setLevel(getattr(logging, level.upper(), logging.INFO))


# 模块级 logger
logger = get_logger()
