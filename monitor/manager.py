from __future__ import annotations

from typing import Dict

from monitor.base import BaseCommentMonitor
from monitor.models import MonitorTarget
from monitor.notifier import WebhookNotifier
from monitor.storage import MonitorStorage
import logging


logger = logging.getLogger("MediaCrawler.monitor")
class MonitorManager:
    def __init__(self, storage: MonitorStorage, notifier: WebhookNotifier, monitor_adapter: BaseCommentMonitor, default_webhook: str = "") -> None:
        self.storage = storage
        self.notifier = notifier
        self.monitor_adapter = monitor_adapter
        self.default_webhook = default_webhook
        self.failure_count: Dict[str, int] = {}

    async def check_target_once(self, target: MonitorTarget) -> None:
        target_key = f"{target.platform}:{target.target_id}"
        try:
            logger.info("[MonitorManager] polling start target=%s", target_key)
            comments = await self.monitor_adapter.fetch_latest_comments(target)
            logger.info("[MonitorManager] fetched comments target=%s count=%s", target_key, len(comments))
            new_comments = await self.storage.insert_new_comments(comments)

            if new_comments:
                await self.storage.record_events(target.platform, target.target_id, "new_comment", new_comments)
                webhook = target.webhook_url or self.default_webhook
                await self.notifier.notify_new_comments(target, new_comments, webhook)

            logger.info("[MonitorManager] polling end target=%s new_comments=%s", target_key, len(new_comments))
            await self.storage.update_target_check_result(target, success=True)
            self.failure_count[target_key] = 0
        except Exception as exc:
            self.failure_count[target_key] = self.failure_count.get(target_key, 0) + 1
            logger.error("[MonitorManager] polling failed target=%s fail_count=%s err=%s", target_key, self.failure_count[target_key], exc)
            await self.storage.update_target_check_result(target, success=False, error=str(exc))
            await self.monitor_adapter.recover(target, self.failure_count[target_key])
