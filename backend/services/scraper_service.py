"""
scraper_service.py — 金融热点爬虫服务

提供：
  fetch_toutiao_hot(limit)      抓取头条热榜，返回 list[dict]
  fetch_eastmoney_hot(limit)    抓取东方财富热帖，返回 list[dict]
  fetch_xueqiu_hot(limit)       抓取雪球热帖，返回 list[dict]
  score_relevance(titles, context)  关键词打分，返回 list[float]
  run_scrape(task_id, platform)     TaskManager 入口
"""

import logging
from typing import Optional

import requests

from database import SessionLocal
from models import Topic
from services.task_manager import task_manager


def _get_proxies() -> dict | None:
    from config import Config
    proxy = Config.HTTPS_PROXY.strip() if Config.HTTPS_PROXY else ""
    return {"https": proxy, "http": proxy} if proxy else None

logger = logging.getLogger(__name__)

# ─── 常量 ────────────────────────────────────────────────────────────────────

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.toutiao.com/",
}

_HOT_BOARD_URL = (
    "https://www.toutiao.com/hot-event/hot-board/"
    "?origin=toutiao_pc"
    "&_signature=_02B4Z6wo00501DX0pNwAAIDCIXCKGAOTQF6QbDiAAInk01"
)

_FEED_URL = (
    "https://www.toutiao.com/api/pc/list/feed"
    "?channel_id=0&max_behot_time=0&category=pc_profile_homepage"
)

# 东方财富热帖 API
_EASTMONEY_URL = (
    "https://emappdata.eastmoney.com/stockrank/getAllCurrentList"
)

# 雪球热帖 API
_XUEQIU_URL = (
    "https://stock.xueqiu.com/v5/stock/hot_stock/list.json"
    "?size=30&_type=10&type=10"
)

# 新浪财经热榜 API (feed.mix)
_SINA_URL = (
    "https://feed.mix.sina.com.cn/api/roll/get"
    "?pageid=153&lid=2516&k=&num=30&page=1&r=0.1"
)

# 宽论相关关键词（用于相关性打分）
_KUANLUN_KEYWORDS = [
    # 核心交易术语
    "量化", "概率", "交易", "投资", "基金",
    "金融", "策略", "期货", "股票", "炒股",
    "均线", "K线", "MACD", "趋势", "止损",
    "仓位", "回测", "选股", "大盘", "指数",
    "涨跌", "牛市", "熊市", "震荡", "主力",
    "散户", "筹码", "成交量", "突破", "背离",
    "波浪", "缠论", "分型", "行情",
    # 广义金融/经济
    "A股", "港股", "美股", "纳斯达克", "上证",
    "深成指", "创业板", "科创板", "北向资金",
    "基金经理", "券商", "银行股", "保险",
    "理财", "资产", "收益率", "市盈率", "估值",
    "财报", "业绩", "分红", "回购", "IPO",
    "降息", "降准", "央行", "货币政策", "通胀",
    "GDP", "经济", "市场", "板块", "热点",
    "概念股", "龙头", "涨停", "跌停", "利好",
    "利空", "反弹", "回调", "支撑位", "压力位",
]

# 最低相关性分数：低于此值的热点不入库
_MIN_RELEVANCE_SCORE = 0.1


# ─── 核心函数 ─────────────────────────────────────────────────────────────────

def fetch_toutiao_hot(limit: int = 30) -> list[dict]:
    """
    抓取今日头条热榜。

    先尝试 hot-board API，失败则 fallback 到 feed API。
    网络/解析失败时记录日志并返回空列表，不抛异常。

    返回值每项包含：
        title       str   热榜标题
        hot_value   int   热度值（无则为 0）
        source_url  str   原文链接
        platform    str   "toutiao"
    """
    items = _fetch_hot_board(limit)
    if not items:
        logger.warning("hot-board API 无数据，尝试 feed API")
        items = _fetch_feed(limit)
    return items


def score_relevance(titles: list[str], context: str = "") -> list[float]:
    """
    用关键词匹配给每个 title 打 0-1 分。

    匹配规则：
      - 每命中一个宽论关键词 +0.1，上限 1.0
      - context 非空时，context 中出现的词额外加权 +0.1（同一词只算一次）
    """
    scores: list[float] = []
    context_hits = {kw for kw in _KUANLUN_KEYWORDS if kw in context}

    for title in titles:
        score = 0.0
        for kw in _KUANLUN_KEYWORDS:
            if kw in title:
                score += 0.1
                if kw in context_hits:
                    score += 0.1  # context 加权
        scores.append(min(round(score, 2), 1.0))

    return scores


def fetch_eastmoney_hot(limit: int = 30) -> list[dict]:
    """抓取东方财富热帖（股票社区热门讨论）。"""
    try:
        resp = requests.post(
            _EASTMONEY_URL,
            json={"appId": "appId01", "globalId": "786e4c21-70dc-435a-93bb-38", "marketType": "", "pageNo": 1, "pageSize": limit},
            headers={**_HEADERS, "Referer": "https://guba.eastmoney.com/", "Content-Type": "application/json"},
            timeout=10,
            proxies=_get_proxies(),
        )
        resp.raise_for_status()
        data = resp.json()
        raw_list = data.get("data", [])
        result = []
        for item in raw_list[:limit]:
            title = (item.get("title") or item.get("postTitle") or "").strip()
            if not title:
                continue
            stock_code = item.get("stockCode") or item.get("code") or ""
            result.append({
                "title": title,
                "hot_value": _safe_int(item.get("hotValue") or item.get("readCount") or 0),
                "source_url": f"https://guba.eastmoney.com/list,{stock_code}.html" if stock_code else "",
                "platform": "eastmoney",
            })
        return result
    except Exception as e:
        logger.error("东方财富热帖请求失败: %s", e)
        return []


def fetch_xueqiu_hot(limit: int = 30) -> list[dict]:
    """抓取雪球热帖（投资者讨论热门）。"""
    try:
        resp = requests.get(
            _XUEQIU_URL,
            headers={**_HEADERS, "Referer": "https://xueqiu.com/", "Cookie": "xq_a_token=;"},
            timeout=10,
            proxies=_get_proxies(),
        )
        resp.raise_for_status()
        data = resp.json()
        raw_list = data.get("data", {}).get("items", [])
        result = []
        for item in raw_list[:limit]:
            title = (item.get("name") or item.get("title") or item.get("text") or "").strip()
            if not title:
                continue
            code = item.get("code") or item.get("symbol") or ""
            result.append({
                "title": title,
                "hot_value": _safe_int(item.get("increment") or item.get("followers") or 0),
                "source_url": f"https://xueqiu.com/S/{code}" if code else "",
                "platform": "xueqiu",
            })
        return result
    except Exception as e:
        logger.error("雪球热帖请求失败: %s", e)
        return []


def fetch_sina_hot(limit: int = 30) -> list[dict]:
    """抓取新浪财经热榜（纯金融内容，无需过滤）。"""
    try:
        resp = requests.get(
            _SINA_URL,
            headers={**_HEADERS, "Referer": "https://finance.sina.com.cn/"},
            timeout=10,
            proxies=_get_proxies(),
        )
        resp.raise_for_status()
        data = resp.json()
        raw_list = data.get("result", {}).get("data", [])
        result = []
        for item in raw_list[:limit]:
            title = (item.get("title") or "").strip()
            if not title:
                continue
            hot_value = _safe_int(item.get("comment") or item.get("read") or 0)
            url_str = (item.get("url") or "").strip()
            result.append({
                "title": title,
                "hot_value": hot_value,
                "source_url": url_str,
                "platform": "sina",
            })
        return result
    except Exception as e:
        logger.error("新浪财经热榜请求失败: %s", e)
        return []


def run_scrape(task_id: str, platform: str) -> dict:
    """
    TaskManager 调用入口。

    流程：抓取 → 打分 → 过滤（只保留金融相关） → 存 DB → 推 SSE 日志
    返回 {"saved": int, "platform": str}
    """
    task_manager.push_log(task_id, f"开始抓取 {platform} 热点…", progress=5)

    # 1. 抓取
    if platform == "toutiao":
        items = fetch_toutiao_hot(limit=30)
    elif platform == "eastmoney":
        items = fetch_eastmoney_hot(limit=30)
    elif platform == "xueqiu":
        items = fetch_xueqiu_hot(limit=30)
    elif platform == "sina":
        items = fetch_sina_hot(limit=30)
    elif platform == "all":
        items = []
        for name, fetcher in [("toutiao", fetch_toutiao_hot), ("sina", fetch_sina_hot), ("eastmoney", fetch_eastmoney_hot), ("xueqiu", fetch_xueqiu_hot)]:
            task_manager.push_log(task_id, f"抓取 {name}…", progress=10)
            batch = fetcher(limit=20)
            items.extend(batch)
    else:
        logger.warning("未支持的平台: %s", platform)
        task_manager.push_log(task_id, f"不支持的平台: {platform}", progress=100)
        return {"saved": 0, "platform": platform}

    if not items:
        task_manager.push_log(task_id, "抓取结果为空，任务结束", progress=100)
        return {"saved": 0, "platform": platform}

    task_manager.push_log(task_id, f"抓取到 {len(items)} 条热点", progress=40)

    # 2. 打分
    titles = [it["title"] for it in items]
    scores = score_relevance(titles)
    task_manager.push_log(task_id, "相关性打分完成", progress=60)

    # 3. 过滤：只保留金融交易相关的
    filtered = [(it, sc) for it, sc in zip(items, scores) if sc >= _MIN_RELEVANCE_SCORE]
    skipped = len(items) - len(filtered)
    task_manager.push_log(task_id, f"过滤后保留 {len(filtered)} 条金融相关（过滤掉 {skipped} 条无关）", progress=75)

    if not filtered:
        task_manager.push_log(task_id, "没有找到金融相关热点", progress=100)
        return {"saved": 0, "platform": platform}

    filtered_items = [it for it, _ in filtered]
    filtered_scores = [sc for _, sc in filtered]

    # 4. 存 DB
    saved = _save_topics(filtered_items, filtered_scores)
    task_manager.push_log(task_id, f"已入库 {saved} 条（去重后）", progress=90)

    task_manager.push_log(task_id, "抓取任务完成", progress=100)
    return {"saved": saved, "platform": platform}


# ─── 私有：抓取 ───────────────────────────────────────────────────────────────

def _fetch_hot_board(limit: int) -> list[dict]:
    try:
        resp = requests.get(_HOT_BOARD_URL, headers=_HEADERS, timeout=10, proxies=_get_proxies())
        resp.raise_for_status()
        data = resp.json()
        # 响应结构: {"data": [{"Title": ..., "HotValue": ..., "Url": ...}, ...]}
        raw_list = data.get("data", [])
        return _parse_hot_board(raw_list, limit)
    except requests.RequestException as e:
        logger.error("hot-board 请求失败: %s", e)
    except (ValueError, KeyError) as e:
        logger.error("hot-board 响应解析失败: %s", e)
    return []


def _parse_hot_board(raw_list: list, limit: int) -> list[dict]:
    result = []
    for item in raw_list[:limit]:
        title = (
            item.get("Title")
            or item.get("title")
            or item.get("query")
            or ""
        ).strip()
        if not title:
            continue
        hot_value = _safe_int(
            item.get("HotValue") or item.get("hot_value") or item.get("hotValue") or 0
        )
        url = (
            item.get("Url")
            or item.get("url")
            or item.get("source_url")
            or ""
        ).strip()
        result.append({
            "title": title,
            "hot_value": hot_value,
            "source_url": url,
            "platform": "toutiao",
        })
    return result


def _fetch_feed(limit: int) -> list[dict]:
    try:
        resp = requests.get(_FEED_URL, headers=_HEADERS, timeout=10, proxies=_get_proxies())
        resp.raise_for_status()
        data = resp.json()
        raw_list = data.get("data", [])
        return _parse_feed(raw_list, limit)
    except requests.RequestException as e:
        logger.error("feed API 请求失败: %s", e)
    except (ValueError, KeyError) as e:
        logger.error("feed API 响应解析失败: %s", e)
    return []


def _parse_feed(raw_list: list, limit: int) -> list[dict]:
    result = []
    for item in raw_list[:limit]:
        title = (
            item.get("title")
            or item.get("abstract")
            or ""
        ).strip()
        if not title:
            continue
        hot_value = _safe_int(item.get("comment_count", 0))
        url = item.get("source_url") or item.get("article_url") or ""
        result.append({
            "title": title,
            "hot_value": hot_value,
            "source_url": url.strip(),
            "platform": "toutiao",
        })
    return result


# ─── 私有：DB ─────────────────────────────────────────────────────────────────

def _save_topics(items: list[dict], scores: list[float]) -> int:
    """将热榜条目写入 topics 表，按 title+platform 去重（已有的跳过）。"""
    saved = 0
    db = SessionLocal()
    try:
        for item, score in zip(items, scores):
            exists = (
                db.query(Topic)
                .filter_by(title=item["title"], platform=item["platform"])
                .first()
            )
            if exists:
                continue
            topic = Topic(
                title=item["title"],
                platform=item["platform"],
                source_url=item.get("source_url") or None,
                hot_value=item.get("hot_value") or 0,
                relevance_score=score,
                status="new",
            )
            db.add(topic)
            saved += 1
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("写入 topics 失败: %s", e)
    finally:
        db.close()
    return saved


# ─── 工具 ─────────────────────────────────────────────────────────────────────

def _safe_int(val) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0
