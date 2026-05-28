# engine.py — pgvector 降级版
# 移除了 pgvector 适配器注册，其余逻辑不变
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

import config


def get_engine(url=None):
    """返回数据库引擎，支持通过 url 参数注入（测试/多环境）"""
    target_url = url or config.DATABASE_URL
    engine = create_engine(
        target_url,
        poolclass=QueuePool,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=3600,
        echo=False,
    )
    return engine


def get_session_factory(engine=None):
    """返回 session factory，支持通过 engine 参数注入"""
    eng = engine or get_engine()
    return sessionmaker(bind=eng, expire_on_commit=False)
