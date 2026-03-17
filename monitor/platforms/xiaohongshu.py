from __future__ import annotations

from typing import List

from monitor.base import BaseCommentMonitor
from monitor.models import MonitorComment, MonitorTarget


class XiaohongshuCommentMonitor(BaseCommentMonitor):
    async def open_target(self, target: MonitorTarget) -> None:
        raise NotImplementedError("Xiaohongshu monitor is reserved for future implementation")

    async def fetch_latest_comments(self, target: MonitorTarget) -> List[MonitorComment]:
        raise NotImplementedError("Xiaohongshu monitor is reserved for future implementation")

    async def recover(self, target: MonitorTarget, failure_count: int) -> None:
        return

    async def close(self) -> None:
        return
