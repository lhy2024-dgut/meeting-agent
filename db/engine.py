from sqlalchemy import create_engine, event
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
    _register_vector_adapters(engine)
    return engine


_vector_extension_ensured = False


def _register_vector_adapters(engine):
    """在 psycopg2 连接上注册 pgvector 类型适配器，扩展只在首次连接时创建一次"""
    global _vector_extension_ensured
    try:
        from pgvector.psycopg2 import register_vector

        @event.listens_for(engine, "connect")
        def _on_connect(dbapi_connection, _connection_record):
            global _vector_extension_ensured
            try:
                if not _vector_extension_ensured:
                    dbapi_connection.autocommit = True
                    dbapi_connection.cursor().execute("CREATE EXTENSION IF NOT EXISTS vector")
                    dbapi_connection.autocommit = False
                    _vector_extension_ensured = True
                register_vector(dbapi_connection)
            except Exception:
                pass
    except ImportError:
        pass


def get_session_factory(engine=None):
    """返回 session factory，支持通过 engine 参数注入"""
    eng = engine or get_engine()
    return sessionmaker(bind=eng, expire_on_commit=False)
