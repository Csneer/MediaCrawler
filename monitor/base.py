from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from monitor.models import MonitorComment, MonitorTarget


class BaseCommentMonitor(ABC):
    @abstractmethod
    async def open_target(self, target: MonitorTarget) -> None:
        pass

    @abstractmethod
    async def fetch_latest_comments(self, target: MonitorTarget) -> List[MonitorComment]:
        pass

    @abstractmethod
    async def recover(self, target: MonitorTarget, failure_count: int) -> None:
        pass

    @abstractmethod
    async def close(self) -> None:
        pass
