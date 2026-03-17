from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha1
from typing import Any, Dict, List, Optional


@dataclass
class MonitorComment:
    platform: str
    target_id: str
    target_url: str
    comment_key: str
    comment_id_raw: str = ""
    parent_comment_key: str = ""
    author_name: str = ""
    content: str = ""
    published_at_raw: str = ""
    like_count: int = 0
    is_reply: bool = False
    first_seen_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    payload_json: str = "{}"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MonitorTarget:
    platform: str
    target_id: str
    target_url: str
    enabled: bool = True
    check_interval_sec: int = 60
    fetch_reply_comments: bool = False
    max_comments_per_round: int = 30
    max_reply_comments_per_round: int = 5
    webhook_url: str = ""


@dataclass
class RecoveryPolicy:
    rebuild_page_after_failures: int = 3
    cooldown_after_failures: int = 10


@dataclass
class MonitorRuntimeConfig:
    database_path: str = "data/monitor.db"
    default_interval_sec: int = 60
    max_comments_per_round: int = 30
    max_reply_comments_per_round: int = 5
    webhook_url: str = ""
    log_level: str = "INFO"
    recovery: RecoveryPolicy = field(default_factory=RecoveryPolicy)


@dataclass
class MonitorConfig:
    runtime: MonitorRuntimeConfig
    targets: List[MonitorTarget]


def build_comment_key(
    *,
    platform: str,
    target_id: str,
    comment_id_raw: str,
    parent_comment_key: str,
    author_name: str,
    content: str,
    published_at_raw: str,
) -> str:
    if comment_id_raw:
        return f"{platform}:{target_id}:{comment_id_raw}"

    raw = "||".join(
        [
            platform,
            target_id,
            parent_comment_key,
            author_name.strip(),
            content.strip(),
            published_at_raw.strip(),
        ]
    )
    return sha1(raw.encode("utf-8")).hexdigest()
