"""
wechat_service.py — 微信公众号 API 客户端

提供：
  get_access_token()           获取 access_token（内存缓存，2小时TTL）
  get_article_stats(begin, end) 调用 datacube getarticletotal 接口
  fetch_real_stats()           拉取近30天数据，返回 {title: stats_dict}
"""

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ─── Token 缓存 ──────────────────────────────────────────────────────────────

_cached_token: Optional[str] = None
_token_expires_at: float = 0.0  # Unix timestamp


def reset_access_token_cache() -> None:
    global _cached_token, _token_expires_at
    _cached_token = None
    _token_expires_at = 0.0


def _get_proxies() -> dict | None:
    from config import Config
    proxy = Config.HTTPS_PROXY.strip() if Config.HTTPS_PROXY else ""
    return {"https": proxy, "http": proxy} if proxy else None


def _normalize_title(title: str | None) -> str:
    text = (title or "").strip().lower()
    return re.sub(r"\s+", " ", text)


def _display_title(title: str | None) -> str:
    return re.sub(r"\s+", " ", (title or "").strip())


def _to_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _is_fatal_stats_error(error: RuntimeError) -> bool:
    message = str(error).lower()
    return any(marker in message for marker in ("40164", "42001", "45009", "token", "quota"))


def get_access_token() -> str:
    """
    获取有效的 access_token，自动刷新（提前10分钟）。

    WeChat token 有效期 7200 秒（2小时），每日最多请求 2000 次。
    Raises:
        RuntimeError: appid/appsecret 未配置，或微信API返回错误
    """
    global _cached_token, _token_expires_at

    from config import Config
    if not Config.WECHAT_APP_ID or not Config.WECHAT_APP_SECRET:
        raise RuntimeError("WECHAT_APP_ID 或 WECHAT_APP_SECRET 未配置，请检查 .env 文件")

    now = time.time()
    if _cached_token and now < _token_expires_at - 600:  # 提前10分钟刷新
        return _cached_token

    url = (
        f"https://api.weixin.qq.com/cgi-bin/token"
        f"?grant_type=client_credential"
        f"&appid={Config.WECHAT_APP_ID}"
        f"&secret={Config.WECHAT_APP_SECRET}"
    )

    try:
        resp = requests.get(url, timeout=10, proxies=_get_proxies())
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        raise RuntimeError(f"网络请求 access_token 失败: {e}") from e

    if "errcode" in data:
        errcode = data.get("errcode")
        errmsg = data.get("errmsg", "")
        if errcode == 40164:
            raise RuntimeError(
                f"IP 白名单错误 (40164)：当前服务器 IP 未加入微信公众平台白名单，"
                f"请前往 mp.weixin.qq.com → 开发 → 基本配置 → IP白名单 添加"
            )
        raise RuntimeError(f"获取 access_token 失败: errcode={errcode}, errmsg={errmsg}")

    token = data.get("access_token")
    expires_in = data.get("expires_in", 7200)

    if not token:
        raise RuntimeError(f"微信返回了空的 access_token: {data}")

    _cached_token = token
    _token_expires_at = now + expires_in
    logger.info("access_token 已刷新，有效期 %d 秒", expires_in)
    return token


def get_article_stats_by_date(begin_date: str, end_date: str) -> list[dict]:
    """
    调用 getarticletotal 接口获取指定日期范围内的文章累计数据。

    Args:
        begin_date: "YYYY-MM-DD"（注意：数据有1天延迟，最早能查昨天）
        end_date:   "YYYY-MM-DD"（与 begin_date 相同，每次只能查1天）

    Returns:
        list of dicts with keys:
          msgid, title, int_page_read_count, share_count,
          add_to_fav_count, ori_page_read_count
    """
    token = get_access_token()
    url = f"https://api.weixin.qq.com/datacube/getarticletotal?access_token={token}"
    payload = {"begin_date": begin_date, "end_date": end_date}

    try:
        resp = requests.post(url, json=payload, timeout=15, proxies=_get_proxies())
        resp.raise_for_status()
        resp.encoding = "utf-8"
        data = resp.json()
    except requests.RequestException as e:
        raise RuntimeError(f"datacube API 请求失败: {e}") from e

    if "errcode" in data and data["errcode"] != 0:
        errcode = data.get("errcode")
        errmsg = data.get("errmsg", "")
        if errcode == 40164:
            raise RuntimeError(
                f"IP 白名单错误 (40164)：当前服务器 IP 未加入微信公众平台白名单"
            )
        if errcode == 42001:
            # token 过期，强制刷新
            global _cached_token
            _cached_token = None
            raise RuntimeError(f"access_token 已过期 (42001)，请重试")
        raise RuntimeError(f"datacube API 错误: errcode={errcode}, errmsg={errmsg}")

    return data.get("list", [])


def get_article_summary_by_date(begin_date: str, end_date: str) -> list[dict]:
    """
    调用 getarticlesummary 接口获取指定日期的文章阅读摘要（每日数据）。

    与 getarticletotal 不同，此接口返回所有有活动的文章，而非仅返回 1 篇。

    Args:
        begin_date: "YYYY-MM-DD"
        end_date:   "YYYY-MM-DD"

    Returns:
        list of dicts with keys:
          msgid, title, int_page_read_count, share_count,
          add_to_fav_count, ori_page_read_count
    """
    token = get_access_token()
    url = f"https://api.weixin.qq.com/datacube/getarticlesummary?access_token={token}"
    payload = {"begin_date": begin_date, "end_date": end_date}

    try:
        resp = requests.post(url, json=payload, timeout=15, proxies=_get_proxies())
        resp.raise_for_status()
        resp.encoding = "utf-8"
        data = resp.json()
    except requests.RequestException as e:
        raise RuntimeError(f"getarticlesummary API 请求失败: {e}") from e

    if "errcode" in data and data["errcode"] != 0:
        errcode = data.get("errcode")
        errmsg = data.get("errmsg", "")
        if errcode == 40164:
            raise RuntimeError(
                f"IP 白名单错误 (40164)：当前服务器 IP 未加入微信公众平台白名单"
            )
        if errcode == 42001:
            global _cached_token
            _cached_token = None
            raise RuntimeError(f"access_token 已过期 (42001)，请重试")
        raise RuntimeError(f"getarticlesummary API 错误: errcode={errcode}, errmsg={errmsg}")

    return data.get("list", [])


def fetch_real_stats(days_back: int = 365) -> dict[str, dict]:
    """
    拉取已发布文章的累计统计数据。

    策略：遍历近 days_back 天，每天调用 getarticlesummary 获取所有有活动的文章的
    每日数据，然后按文章标题求和得到累计值。

    getarticlesummary 每天返回所有有阅读/分享等活动的文章（比 getarticletotal 的
    每天 1 篇覆盖范围大得多）。

    Returns:
        {
            "文章标题": {
                "int_page_read_count": 1234,
                "share_count": 56,
                "add_to_fav_count": 23,
                "ori_page_read_count": 100,
            },
            ...
        }
    Raises:
        RuntimeError: API 调用失败（IP白名单、凭证错误等）
    """
    today = date.today()
    # 数据有1天延迟，从昨天开始
    dates = [
        (today - timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(1, days_back + 1)
    ]

    # 先拿一次 token（缓存），避免并发线程各自竞争刷新
    get_access_token()

    from config import Config

    max_workers = max(1, int(getattr(Config, "WECHAT_STATS_MAX_WORKERS", 1) or 1))

    def _fetch_one(date_str: str) -> tuple[str, list[dict]]:
        try:
            items = get_article_summary_by_date(date_str, date_str)
            return date_str, items
        except RuntimeError as e:
            if _is_fatal_stats_error(e):
                raise
            logger.warning("查询日期 %s 失败，跳过: %s", date_str, e)
            return date_str, []

    # 并发查询，最多 8 个线程（避免触发微信限流）
    day_results: dict[str, list[dict]] = {}
    if max_workers == 1:
        for date_str in dates:
            date_str, items = _fetch_one(date_str)
            day_results[date_str] = items
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_fetch_one, d): d for d in dates}
            for future in as_completed(futures):
                date_str, items = future.result()
                day_results[date_str] = items

    # 聚合数据：getarticlesummary 返回每日数据，按标题求和得到累计值
    result_by_key: dict[str, dict] = {}
    for date_str in sorted(day_results):
        for item in day_results[date_str]:
            title = _display_title(item.get("title"))
            title_key = _normalize_title(title)
            if not title_key:
                continue
            if title_key not in result_by_key:
                result_by_key[title_key] = {
                    "title": title,
                    "int_page_read_count": 0,
                    "share_count": 0,
                    "add_to_fav_count": 0,
                    "ori_page_read_count": 0,
                }
            row = result_by_key[title_key]
            row["int_page_read_count"] += _to_int(item.get("int_page_read_count"))
            row["share_count"] += _to_int(item.get("share_count"))
            row["add_to_fav_count"] += _to_int(item.get("add_to_fav_count"))
            row["ori_page_read_count"] += _to_int(item.get("ori_page_read_count"))

    result = {
        stats.pop("title"): stats
        for stats in result_by_key.values()
    }

    logger.info("fetch_real_stats 完成，获取到 %d 篇文章数据", len(result))
    return result


def get_published_articles() -> dict[str, dict]:
    """
    调用 freepublish/batchget 获取所有已发布文章的标题和时间戳。

    Returns:
        {title: {"article_id": str, "update_time": datetime}}
    """
    token = get_access_token()
    url = f"https://api.weixin.qq.com/cgi-bin/freepublish/batchget?access_token={token}"

    result: dict[str, dict] = {}
    offset = 0
    count = 20  # 微信每次最多返回20条

    while True:
        payload = {"offset": offset, "count": count, "no_content": 1}
        try:
            resp = requests.post(url, json=payload, timeout=15, proxies=_get_proxies())
            resp.raise_for_status()
            resp.encoding = "utf-8"
            data = resp.json()
        except requests.RequestException as e:
            raise RuntimeError(f"freepublish/batchget 请求失败: {e}") from e

        if "errcode" in data and data["errcode"] != 0:
            errcode = data.get("errcode")
            errmsg = data.get("errmsg", "")
            raise RuntimeError(f"freepublish/batchget 错误: errcode={errcode}, errmsg={errmsg}")

        items = data.get("item", [])
        for item in items:
            content = item.get("content", {})
            news_items = content.get("news_item", [])
            for ni in news_items:
                title = (ni.get("title") or "").strip()
                if title:
                    from datetime import datetime, timezone
                    update_time = item.get("update_time", 0)
                    result[title] = {
                        "article_id": item.get("article_id", ""),
                        "update_time": datetime.fromtimestamp(update_time, tz=timezone.utc) if update_time else None,
                    }

        if len(items) < count:
            break
        offset += count

    logger.info("get_published_articles 完成，获取到 %d 篇已发布文章", len(result))
    return result
