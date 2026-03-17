from __future__ import annotations

import asyncio
import json
from typing import Dict, List, Optional

from playwright.async_api import BrowserContext, Page, Playwright, async_playwright

import config
from media_platform.douyin import DouYinCrawler
from media_platform.douyin.login import DouYinLogin
from monitor.base import BaseCommentMonitor
from monitor.models import MonitorComment, MonitorTarget, build_comment_key
import logging


logger = logging.getLogger("MediaCrawler.monitor")
class DouyinCommentMonitor(BaseCommentMonitor):
    def __init__(self) -> None:
        self.crawler = DouYinCrawler()
        self.playwright: Optional[Playwright] = None
        self.browser_context: Optional[BrowserContext] = None
        self.page_by_target: Dict[str, Page] = {}

    async def _ensure_context(self) -> BrowserContext:
        if self.browser_context is not None:
            return self.browser_context

        self.playwright = await async_playwright().start()
        if config.ENABLE_CDP_MODE:
            self.browser_context = await self.crawler.launch_browser_with_cdp(self.playwright, None, None, headless=config.CDP_HEADLESS)
        else:
            self.browser_context = await self.crawler.launch_browser(self.playwright.chromium, None, None, headless=config.HEADLESS)
            await self.browser_context.add_init_script(path="libs/stealth.min.js")

        self.crawler.browser_context = self.browser_context
        page = await self.browser_context.new_page()
        self.crawler.context_page = page
        await page.goto("https://www.douyin.com", wait_until="domcontentloaded")
        self.crawler.dy_client = await self.crawler.create_douyin_client(httpx_proxy=None)

        if not await self.crawler.dy_client.pong(browser_context=self.browser_context):
            logger.info("[DouyinCommentMonitor] login session expired, trying login flow")
            login_obj = DouYinLogin(
                login_type=config.LOGIN_TYPE,
                login_phone="",
                browser_context=self.browser_context,
                context_page=page,
                cookie_str=config.COOKIES,
            )
            await login_obj.begin()
            await self.crawler.dy_client.update_cookies(browser_context=self.browser_context)

        return self.browser_context

    async def open_target(self, target: MonitorTarget) -> None:
        context = await self._ensure_context()
        if target.target_id in self.page_by_target and not self.page_by_target[target.target_id].is_closed():
            return

        page = await context.new_page()
        await page.goto(target.target_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)
        await self._open_comment_panel(page)
        await self._switch_to_latest(page)
        self.page_by_target[target.target_id] = page
        logger.info("[DouyinCommentMonitor] target opened %s", target.target_url)

    async def _open_comment_panel(self, page: Page) -> None:
        open_selectors = [
            "button:has-text('评论')",
            "[aria-label*='评论']",
            "div:has-text('评论')",
        ]
        for selector in open_selectors:
            btn = page.locator(selector).first
            if await btn.count() > 0:
                try:
                    await btn.click(timeout=2000)
                    await page.wait_for_timeout(800)
                    return
                except Exception:
                    continue

    async def _switch_to_latest(self, page: Page) -> None:
        selectors = [
            "button:has-text('最新评论')",
            "span:has-text('最新评论')",
            "div[role='button']:has-text('最新评论')",
        ]
        for selector in selectors:
            loc = page.locator(selector).first
            if await loc.count() > 0:
                try:
                    await loc.click(timeout=2000)
                    await page.wait_for_timeout(600)
                    logger.info("[DouyinCommentMonitor] switched to 最新评论")
                    return
                except Exception:
                    continue
        logger.warning("[DouyinCommentMonitor] 最新评论 button not found; keep current order")

    async def fetch_latest_comments(self, target: MonitorTarget) -> List[MonitorComment]:
        await self.open_target(target)
        page = self.page_by_target[target.target_id]
        await page.wait_for_timeout(500)

        raw_comments: List[dict] = await page.evaluate(
            """
            ({maxComments}) => {
              const toInt = (s) => {
                if (!s) return 0;
                const n = String(s).replace(/[^\d]/g, '');
                return n ? parseInt(n, 10) : 0;
              }
              const blocks = Array.from(document.querySelectorAll('div[class*="comment"], li[class*="comment"], article'));
              const result = [];
              for (const b of blocks) {
                const txt = (b.innerText || '').trim();
                if (!txt || txt.length < 2) continue;
                const authorEl = b.querySelector('a, h4, h3, span');
                const author = (authorEl?.textContent || '').trim();
                const contentEl = b.querySelector('p, span[class*="content"], div[class*="content"]');
                const content = (contentEl?.textContent || txt).trim();
                const timeEl = b.querySelector('span[class*="time"], span[class*="date"], time');
                const likeEl = b.querySelector('span[class*="like"], i[class*="like"] + span');
                const cid = b.getAttribute('data-comment-id') || b.getAttribute('data-id') || '';
                const parent = b.getAttribute('data-parent-id') || '';
                if (!content || !author) continue;
                result.push({
                  comment_id_raw: cid,
                  parent_id_raw: parent,
                  author_name: author,
                  content,
                  published_at_raw: (timeEl?.textContent || '').trim(),
                  like_count: toInt(likeEl?.textContent || ''),
                  payload: { text: txt }
                });
                if (result.length >= maxComments) break;
              }
              return result;
            }
            """,
            {"maxComments": target.max_comments_per_round},
        )

        comments: List[MonitorComment] = []
        for raw in raw_comments:
            parent_key = raw.get("parent_id_raw", "")
            key = build_comment_key(
                platform=target.platform,
                target_id=target.target_id,
                comment_id_raw=raw.get("comment_id_raw", ""),
                parent_comment_key=parent_key,
                author_name=raw.get("author_name", ""),
                content=raw.get("content", ""),
                published_at_raw=raw.get("published_at_raw", ""),
            )
            comments.append(
                MonitorComment(
                    platform=target.platform,
                    target_id=target.target_id,
                    target_url=target.target_url,
                    comment_key=key,
                    comment_id_raw=raw.get("comment_id_raw", ""),
                    parent_comment_key=parent_key,
                    author_name=raw.get("author_name", ""),
                    content=raw.get("content", ""),
                    published_at_raw=raw.get("published_at_raw", ""),
                    like_count=int(raw.get("like_count", 0) or 0),
                    is_reply=bool(parent_key),
                    payload_json=json.dumps(raw, ensure_ascii=False),
                )
            )

        if target.fetch_reply_comments:
            logger.warning("[DouyinCommentMonitor] reply monitoring is enabled, but currently only auto-detected visible replies are captured")
        return comments

    async def recover(self, target: MonitorTarget, failure_count: int) -> None:
        if failure_count < 3:
            return
        page = self.page_by_target.get(target.target_id)
        if page and not page.is_closed():
            await page.close()
        self.page_by_target.pop(target.target_id, None)
        await asyncio.sleep(1)
        await self.open_target(target)

    async def close(self) -> None:
        for page in self.page_by_target.values():
            if not page.is_closed():
                await page.close()
        self.page_by_target = {}

        if self.browser_context:
            await self.browser_context.close()
            self.browser_context = None

        if self.playwright:
            await self.playwright.stop()
            self.playwright = None
