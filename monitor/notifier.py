from __future__ import annotations

from datetime import datetime, timezone
from typing import List

import httpx

from monitor.models import MonitorComment, MonitorTarget
import logging


logger = logging.getLogger("MediaCrawler.monitor")
class WebhookNotifier:
    async def notify_new_comments(self, target: MonitorTarget, comments: List[MonitorComment], webhook_url: str) -> None:
        if not webhook_url or not comments:
            return

        payload = {
            "platform": target.platform,
            "target_id": target.target_id,
            "target_url": target.target_url,
            "event_type": "new_comment",
            "comments": [
                {
                    "comment_key": c.comment_key,
                    "author_name": c.author_name,
                    "content": c.content,
                    "published_at_raw": c.published_at_raw,
                    "is_reply": c.is_reply,
                }
                for c in comments
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(webhook_url, json=payload)
                resp.raise_for_status()
                logger.info(
                    "[WebhookNotifier] webhook sent, target=%s, count=%s, status=%s",
                    target.target_id,
                    len(comments),
                    resp.status_code,
                )
        except Exception as exc:
            logger.error("[WebhookNotifier] webhook failed target=%s err=%s", target.target_id, exc)
