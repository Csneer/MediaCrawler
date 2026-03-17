from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Iterable, List

import aiosqlite

from monitor.models import MonitorComment, MonitorTarget


class MonitorStorage:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    async def init(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS monitor_targets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    target_url TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    check_interval_sec INTEGER NOT NULL,
                    fetch_reply_comments INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_checked_at TEXT,
                    last_success_at TEXT,
                    last_error TEXT,
                    UNIQUE(platform, target_id)
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS monitor_comments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    comment_key TEXT NOT NULL UNIQUE,
                    comment_id_raw TEXT,
                    parent_comment_key TEXT,
                    author_name TEXT,
                    content TEXT,
                    published_at_raw TEXT,
                    like_count INTEGER,
                    is_reply INTEGER NOT NULL DEFAULT 0,
                    first_seen_at TEXT NOT NULL,
                    payload_json TEXT
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS monitor_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    comment_key TEXT,
                    message TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            await db.commit()

    async def upsert_target(self, target: MonitorTarget) -> None:
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO monitor_targets(platform, target_id, target_url, enabled, check_interval_sec,
                                            fetch_reply_comments, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(platform, target_id) DO UPDATE SET
                    target_url=excluded.target_url,
                    enabled=excluded.enabled,
                    check_interval_sec=excluded.check_interval_sec,
                    fetch_reply_comments=excluded.fetch_reply_comments,
                    updated_at=excluded.updated_at
                """,
                (
                    target.platform,
                    target.target_id,
                    target.target_url,
                    int(target.enabled),
                    target.check_interval_sec,
                    int(target.fetch_reply_comments),
                    now,
                    now,
                ),
            )
            await db.commit()

    async def update_target_check_result(self, target: MonitorTarget, success: bool, error: str = "") -> None:
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE monitor_targets
                SET last_checked_at=?, last_success_at=CASE WHEN ? THEN ? ELSE last_success_at END, last_error=?
                WHERE platform=? AND target_id=?
                """,
                (now, int(success), now, error, target.platform, target.target_id),
            )
            await db.commit()

    async def insert_new_comments(self, comments: Iterable[MonitorComment]) -> List[MonitorComment]:
        new_comments: List[MonitorComment] = []
        async with aiosqlite.connect(self.db_path) as db:
            for comment in comments:
                cur = await db.execute(
                    """
                    INSERT OR IGNORE INTO monitor_comments(
                        platform, target_id, comment_key, comment_id_raw, parent_comment_key,
                        author_name, content, published_at_raw, like_count, is_reply, first_seen_at, payload_json
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        comment.platform,
                        comment.target_id,
                        comment.comment_key,
                        comment.comment_id_raw,
                        comment.parent_comment_key,
                        comment.author_name,
                        comment.content,
                        comment.published_at_raw,
                        comment.like_count,
                        int(comment.is_reply),
                        comment.first_seen_at,
                        comment.payload_json,
                    ),
                )
                if cur.rowcount:
                    new_comments.append(comment)
            await db.commit()

        return new_comments

    async def record_events(self, platform: str, target_id: str, event_type: str, comments: Iterable[MonitorComment]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            for item in comments:
                await db.execute(
                    "INSERT INTO monitor_events(platform, target_id, event_type, comment_key, message, created_at) VALUES(?, ?, ?, ?, ?, ?)",
                    (platform, target_id, event_type, item.comment_key, json.dumps(item.to_dict(), ensure_ascii=False), now),
                )
            await db.commit()
