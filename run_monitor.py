from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
from typing import Any, Dict, List

from monitor.models import MonitorConfig, MonitorRuntimeConfig, MonitorTarget, RecoveryPolicy

logger = logging.getLogger("MediaCrawler.monitor")


def _load_yaml_file(path: str) -> Dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML is required for --config yaml file, install with `pip install pyyaml`") from exc

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _parse_douyin_aweme_id(url_or_id: str) -> str:
    if url_or_id.isdigit():
        return url_or_id
    patterns = [r"/video/(\d+)", r"modal_id=(\d+)"]
    for pattern in patterns:
        m = re.search(pattern, url_or_id)
        if m:
            return m.group(1)
    raise ValueError(f"Unable to parse douyin target id from: {url_or_id}")


def _build_target_id(platform: str, target_url: str, target_id: str) -> str:
    if target_id:
        return target_id
    if platform == "douyin":
        return _parse_douyin_aweme_id(target_url)
    raise ValueError(f"Unsupported platform for parsing target_id: {platform}")


def _build_config_from_args(args: argparse.Namespace) -> MonitorConfig:
    if args.config:
        data = _load_yaml_file(args.config)
        monitor_cfg = data.get("monitor", {})
        runtime = MonitorRuntimeConfig(
            database_path=data.get("database", {}).get("path", "data/monitor.db"),
            default_interval_sec=monitor_cfg.get("default_interval_sec", 60),
            max_comments_per_round=monitor_cfg.get("max_comments_per_round", 30),
            max_reply_comments_per_round=monitor_cfg.get("max_reply_comments_per_round", 5),
            webhook_url=data.get("notification", {}).get("webhook_url", ""),
            log_level=monitor_cfg.get("log_level", args.log_level),
            recovery=RecoveryPolicy(**monitor_cfg.get("recovery", {})),
        )
        targets: List[MonitorTarget] = []
        for item in data.get("targets", []):
            platform = item.get("platform", "douyin")
            target_url = item.get("target_url", "")
            parsed_target_id = _build_target_id(platform, target_url, item.get("target_id", ""))
            targets.append(
                MonitorTarget(
                    platform=platform,
                    target_id=parsed_target_id,
                    target_url=target_url,
                    enabled=item.get("enabled", True),
                    check_interval_sec=item.get("check_interval_sec", runtime.default_interval_sec),
                    fetch_reply_comments=item.get("fetch_reply_comments", False),
                    max_comments_per_round=item.get("max_comments_per_round", runtime.max_comments_per_round),
                    max_reply_comments_per_round=item.get("max_reply_comments_per_round", runtime.max_reply_comments_per_round),
                    webhook_url=item.get("webhook_url", ""),
                )
            )
        return MonitorConfig(runtime=runtime, targets=targets)

    if not args.url and not args.target_id:
        raise ValueError("Please provide --url or --target-id, or use --config")

    target_url = args.url
    if args.target_id and not target_url:
        target_url = f"https://www.douyin.com/video/{args.target_id}"
    parsed_target_id = _build_target_id(args.platform, target_url, args.target_id)

    runtime = MonitorRuntimeConfig(
        database_path=args.db_path,
        default_interval_sec=args.interval,
        max_comments_per_round=args.max_comments,
        max_reply_comments_per_round=args.max_reply_comments,
        webhook_url=args.webhook,
        log_level=args.log_level,
    )
    targets = [
        MonitorTarget(
            platform=args.platform,
            target_id=parsed_target_id,
            target_url=target_url,
            check_interval_sec=args.interval,
            fetch_reply_comments=args.fetch_replies,
            max_comments_per_round=args.max_comments,
            max_reply_comments_per_round=args.max_reply_comments,
            webhook_url=args.webhook,
        )
    ]
    return MonitorConfig(runtime=runtime, targets=targets)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run comment monitor subsystem")
    parser.add_argument("--platform", default="douyin", choices=["douyin"], help="target platform")
    parser.add_argument("--url", default="", help="target post URL")
    parser.add_argument("--target-id", default="", help="target post id")
    parser.add_argument("--interval", default=60, type=int, help="polling interval seconds")
    parser.add_argument("--fetch-replies", action="store_true", help="fetch second-level replies")
    parser.add_argument("--webhook", default="", help="webhook url")
    parser.add_argument("--config", default="", help="yaml config path")
    parser.add_argument("--db-path", default="data/monitor.db", help="sqlite database path")
    parser.add_argument("--max-comments", default=30, type=int, help="max top comments per round")
    parser.add_argument("--max-reply-comments", default=5, type=int, help="max reply comments per round")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser.parse_args()


async def _run() -> None:
    args = _parse_args()

    from monitor.manager import MonitorManager
    from monitor.notifier import WebhookNotifier
    from monitor.platforms import DouyinCommentMonitor
    from monitor.scheduler import MonitorScheduler
    from monitor.storage import MonitorStorage

    cfg = _build_config_from_args(args)

    logging.getLogger().setLevel(getattr(logging, cfg.runtime.log_level.upper(), logging.INFO))
    os.makedirs(os.path.dirname(cfg.runtime.database_path), exist_ok=True)

    storage = MonitorStorage(cfg.runtime.database_path)
    await storage.init()

    for target in cfg.targets:
        if target.platform != "douyin":
            raise ValueError("This release only supports douyin monitor")
        await storage.upsert_target(target)

    monitor = DouyinCommentMonitor()
    manager = MonitorManager(storage=storage, notifier=WebhookNotifier(), monitor_adapter=monitor, default_webhook=cfg.runtime.webhook_url)
    scheduler = MonitorScheduler(manager=manager, targets=cfg.targets)
    scheduler.dump_targets()

    try:
        await scheduler.run_forever()
    finally:
        await monitor.close()


if __name__ == "__main__":
    asyncio.run(_run())
