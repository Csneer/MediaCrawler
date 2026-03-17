from __future__ import annotations

import asyncio
import time
from typing import Dict, Iterable

from monitor.manager import MonitorManager
from monitor.models import MonitorTarget
import logging


logger = logging.getLogger("MediaCrawler.monitor")
class MonitorScheduler:
    def __init__(self, manager: MonitorManager, targets: Iterable[MonitorTarget]) -> None:
        self.manager = manager
        self.targets = [t for t in targets if t.enabled]

    async def run_forever(self) -> None:
        next_run: Dict[str, float] = {
            f"{t.platform}:{t.target_id}": 0.0 for t in self.targets
        }

        while True:
            now = time.monotonic()
            for target in self.targets:
                key = f"{target.platform}:{target.target_id}"
                if now >= next_run[key]:
                    await self.manager.check_target_once(target)
                    next_run[key] = time.monotonic() + target.check_interval_sec
            await asyncio.sleep(1)

    def dump_targets(self) -> None:
        for t in self.targets:
            logger.info(
                "[MonitorScheduler] monitor target platform=%s target_id=%s interval=%ss replies=%s",
                t.platform,
                t.target_id,
                t.check_interval_sec,
                t.fetch_reply_comments,
            )
