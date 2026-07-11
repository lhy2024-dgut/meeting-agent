"""
database.py - PostgreSQL 数据库操作模块
负责：建表、插入、查询会议元数据和转录段落数据
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


def get_conn():
    """获取数据库连接"""
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", 5432),
        dbname=os.getenv("DB_NAME", "meeting_assistant"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
    )


def init_db():
    """
    初始化数据库：创建两张表
    - meetings：会议元数据
    - transcripts：转录段落数据（含时间戳，用于音频同步）
    """
    conn = get_conn()
    cur = conn.cursor()

    # 会议元数据表
    cur.execute("""
        CREATE TABLE IF NOT EXISTS meetings (
            id          SERIAL PRIMARY KEY,
            title       VARCHAR(255) NOT NULL,
            audio_path  TEXT,
            created_at  TIMESTAMP DEFAULT NOW(),
            updated_at  TIMESTAMP DEFAULT NOW()
        );
    """)

    # 转录段落表（每一段语音识别结果单独一行，存时间戳用于播放同步）
    cur.execute("""
        CREATE TABLE IF NOT EXISTS transcripts (
            id          SERIAL PRIMARY KEY,
            meeting_id  INTEGER REFERENCES meetings(id) ON DELETE CASCADE,
            text        TEXT NOT NULL,
            timestamp   FLOAT,       -- 该段在音频中的绝对时间（秒）
            start_time  FLOAT,       -- 开始时间（秒）
            end_time    FLOAT,       -- 结束时间（秒）
            audio_path  TEXT,        -- 冗余存储，方便查询
            summary     TEXT         -- 本段的小摘要（由LLM生成）
        );
    """)

    conn.commit()
    cur.close()
    conn.close()
    print("[DB] 数据库初始化完成")


def insert_meeting(title: str, audio_path: str) -> int:
    """插入一条会议记录，返回新会议的 id"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO meetings (title, audio_path) VALUES (%s, %s) RETURNING id;",
        (title, audio_path)
    )
    meeting_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return meeting_id


def insert_transcripts(meeting_id: int, segments: list, audio_path: str):
    """
    批量插入转录段落
    segments 格式：Whisper 返回的 result["segments"]，每个元素含 text/start/end
    """
    conn = get_conn()
    cur = conn.cursor()
    for seg in segments:
        cur.execute("""
            INSERT INTO transcripts
                (meeting_id, text, timestamp, start_time, end_time, audio_path)
            VALUES (%s, %s, %s, %s, %s, %s);
        """, (
            meeting_id,
            seg["text"].strip(),
            seg["start"],   # timestamp 用 start 时间代替
            seg["start"],
            seg["end"],
            audio_path
        ))
    conn.commit()
    cur.close()
    conn.close()


def update_segment_summary(meeting_id: int, segment_id: int, summary: str):
    """更新某段转录的摘要"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE transcripts SET summary=%s WHERE id=%s AND meeting_id=%s;",
        (summary, segment_id, meeting_id)
    )
    conn.commit()
    cur.close()
    conn.close()


def get_meeting(meeting_id: int) -> dict:
    """查询会议元数据"""
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM meetings WHERE id=%s;", (meeting_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else None


def get_transcripts(meeting_id: int) -> list:
    """查询某会议的所有转录段落，按时间顺序排列"""
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(
        "SELECT * FROM transcripts WHERE meeting_id=%s ORDER BY start_time;",
        (meeting_id,)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


def list_meetings() -> list:
    """列出所有会议"""
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM meetings ORDER BY created_at DESC;")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]



def insert_summary(meeting_id: int, summary: str, decisions: str, todos: str, keywords: list = None):
    """
    插入或更新一条纪要记录。
    使用 ON CONFLICT DO UPDATE 实现「有则更新，无则插入」（upsert），
    避免同一会议重复处理时报唯一键冲突错误。
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO summaries (meeting_id, summary, decisions, todos, keywords)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (meeting_id) DO UPDATE SET
            summary    = EXCLUDED.summary,
            decisions  = EXCLUDED.decisions,
            todos      = EXCLUDED.todos,
            keywords   = EXCLUDED.keywords,
            created_at = NOW();
    """, (meeting_id, summary, decisions, todos, keywords or []))
    conn.commit()
    cur.close()
    conn.close()


def get_summary(meeting_id: int) -> dict:
    """查询某会议的纪要内容"""
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM summaries WHERE meeting_id=%s;", (meeting_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else None


def list_summaries() -> list:
    """列出所有纪要，关联会议标题（用于历史查询）"""
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT s.*, m.title, m.created_at AS meeting_time
        FROM summaries s
        JOIN meetings m ON s.meeting_id = m.id
        ORDER BY s.created_at DESC;
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]