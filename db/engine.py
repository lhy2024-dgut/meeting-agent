from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

import config

# 模块级单例引擎，避免每次请求重建连接池耗尽 PostgreSQL 连接数
_default_engine = None
_default_session_factory = None


def get_engine(url=None):
    """返回数据库引擎，无 url 时返回全局单例。支持通过 url 参数注入（测试/多环境）。"""
    global _default_engine
    if url is not None:
        return _make_engine(url)
    if _default_engine is None:
        _default_engine = _make_engine(config.DATABASE_URL)
    return _default_engine


def _make_engine(target_url: str):
    engine_kwargs = {"echo": False}
    if target_url.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    else:
        engine_kwargs.update(
            {
                "poolclass": QueuePool,
                "pool_size": 5,
                "max_overflow": 10,
                "pool_pre_ping": True,
                "pool_recycle": 3600,
            }
        )
    engine = create_engine(target_url, **engine_kwargs)
    _register_vector_adapters(engine)
    return engine


def _register_vector_adapters(engine):
    """在 psycopg2 连接上注册 pgvector 类型适配器"""
    if engine.url.drivername.startswith("sqlite"):
        return
    try:
        from pgvector.psycopg2 import register_vector

        @event.listens_for(engine, "connect")
        def _on_connect(dbapi_connection, _connection_record):
            try:
                dbapi_connection.autocommit = True
                dbapi_connection.cursor().execute("CREATE EXTENSION IF NOT EXISTS vector")
                register_vector(dbapi_connection)
            except Exception:
                pass
            finally:
                # 无论成功与否都还原 autocommit，防止连接状态损坏
                dbapi_connection.autocommit = False
    except ImportError:
        pass


def get_session_factory(engine=None):
    """返回 session factory，无参数时返回全局单例。支持通过 engine 参数注入。"""
    global _default_session_factory
    if engine is not None:
        return sessionmaker(bind=engine, expire_on_commit=False)
    if _default_session_factory is None:
        _default_session_factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _default_session_factory
