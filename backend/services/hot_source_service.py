"""Unified hot item adapters."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import time

import requests


AIHOT_BASE_URL = "https://aihot.virxact.com"
AIHOT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


@dataclass
class HotItem:
    id: str
    title: str
    url: str | None
    source: str
    published_at: str | None
    summary: str | None
    category: str | None
    platform: str
    hot_value: int = 0
    raw_payload: dict | None = None

    def to_topic_dict(self) -> dict:
        return {
            "title": self.title,
            "source_url": self.url or "",
            "platform": self.platform,
            "hot_value": self.hot_value,
            "summary": self.summary or "",
            "category": self.category or "",
            "source": self.source,
            "raw_payload": self.raw_payload or {},
        }


def fetch_hot_items(
    source_group: str = "finance",
    platform: str | None = None,
    mode: str = "selected",
    category: str | None = None,
    since_hours: int | None = None,
    keyword: str | None = None,
    limit: int = 50,
) -> tuple[list[HotItem], list[str]]:
    """Return normalized hot items and non-fatal source errors."""

    source_group = (source_group or "finance").strip()
    errors: list[str] = []
    items: list[HotItem] = []

    if source_group in {"finance", "all"}:
        try:
            items.extend(_fetch_finance_items(platform or "all", min(limit, 30)))
        except Exception as exc:
            errors.append(f"财经热点抓取失败: {exc}")

    if source_group in {"ai", "aihot", "all"}:
        try:
            items.extend(_fetch_aihot_items(mode, category, since_hours, keyword, min(limit, 100)))
        except Exception as exc:
            errors.append(f"AI HOT 抓取失败: {exc}")

    return items[:limit], errors


def _fetch_finance_items(platform: str, limit: int) -> list[HotItem]:
    from services import scraper_service

    if platform == "toutiao":
        raw_items = scraper_service.fetch_toutiao_hot(limit=limit)
    elif platform == "eastmoney":
        raw_items = scraper_service.fetch_eastmoney_hot(limit=limit)
    elif platform == "xueqiu":
        raw_items = scraper_service.fetch_xueqiu_hot(limit=limit)
    elif platform == "sina":
        raw_items = scraper_service.fetch_sina_hot(limit=limit)
    else:
        raw_items = []
        for name, fetcher in [
            ("toutiao", scraper_service.fetch_toutiao_hot),
            ("sina", scraper_service.fetch_sina_hot),
            ("eastmoney", scraper_service.fetch_eastmoney_hot),
            ("xueqiu", scraper_service.fetch_xueqiu_hot),
        ]:
            try:
                raw_items.extend(fetcher(limit=max(5, limit // 4)))
            except Exception:
                continue
            time.sleep(0.2)

    return [
        HotItem(
            id=f"{item.get('platform', 'finance')}:{item.get('title', '')}",
            title=item.get("title", ""),
            url=item.get("source_url") or None,
            source=item.get("platform", "finance"),
            published_at=None,
            summary=None,
            category="finance",
            platform=item.get("platform", "finance"),
            hot_value=item.get("hot_value") or 0,
            raw_payload=item,
        )
        for item in raw_items
        if item.get("title")
    ]


def _fetch_aihot_items(
    mode: str,
    category: str | None,
    since_hours: int | None,
    keyword: str | None,
    limit: int,
) -> list[HotItem]:
    params: dict[str, str | int] = {
        "mode": "all" if mode == "all" else "selected",
        "take": limit,
    }
    if category:
        params["category"] = category
    if keyword:
        params["q"] = keyword[:200]
    if since_hours:
        since = datetime.now(timezone.utc) - timedelta(hours=max(1, min(since_hours, 24 * 7)))
        params["since"] = since.strftime("%Y-%m-%dT%H:%M:%SZ")

    response = requests.get(
        f"{AIHOT_BASE_URL}/api/public/items",
        params=params,
        headers={"User-Agent": AIHOT_UA},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    result = []
    for item in payload.get("items", []):
        title = item.get("title") or item.get("title_en") or ""
        url = item.get("url")
        if not title:
            continue
        result.append(
            HotItem(
                id=item.get("id") or f"aihot:{url or title}",
                title=title,
                url=url,
                source=item.get("source") or "AI HOT",
                published_at=item.get("publishedAt"),
                summary=item.get("summary"),
                category=item.get("category"),
                platform="aihot",
                hot_value=0,
                raw_payload=item,
            )
        )
    return result


def serialize_hot_item(item: HotItem) -> dict:
    return asdict(item)
