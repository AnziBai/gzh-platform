"""
Playwright 自动抓取微信公众号后台文章统计数据。

功能：
  1. 首次运行：打开浏览器让用户扫码登录，登录后自动保存 session
  2. 后续运行：自动使用已保存的 session，无需重新登录
  3. 通过"发布记录"页面抓取所有已发布文章的阅读、分享、点赞数据
  4. 保存到 JSON 文件并同步到数据库

用法：
  首次登录：  python scrape_wechat_stats.py --login
  抓取数据：  python scrape_wechat_stats.py
  定时任务：  python scrape_wechat_stats.py --headless
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BROWSER_STATE_DIR = os.path.join(SCRIPT_DIR, ".wechat_browser_state")
OUTPUT_JSON = os.path.join(os.path.dirname(SCRIPT_DIR), "scraped_articles.json")
LOG_FILE = os.path.join(SCRIPT_DIR, "scrape.log")


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def scrape_articles(headless: bool = False, login_only: bool = False):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        os.makedirs(BROWSER_STATE_DIR, exist_ok=True)
        context = p.chromium.launch_persistent_context(
            BROWSER_STATE_DIR,
            headless=headless,
            viewport={"width": 1400, "height": 900},
            locale="zh-CN",
        )

        page = context.pages[0] if context.pages else context.new_page()

        try:
            # 1. 打开首页
            log("打开微信公众号后台...")
            page.goto("https://mp.weixin.qq.com/", wait_until="networkidle", timeout=30000)
            time.sleep(2)

            # 检查登录状态
            if _need_login(page):
                if headless:
                    log("headless 模式下无法扫码，请先用 --login 登录")
                    return None
                log("请扫描二维码登录...")
                _wait_for_login(page, timeout=300)
                log("登录成功！")
                if login_only:
                    log("登录状态已保存")
                    return None
            else:
                log("已登录")

            if login_only:
                log("登录状态已保存")
                return None

            # 2. 从页面 URL 提取 token
            token = _extract_token(page)
            if not token:
                log("无法提取 token，尝试从页面链接获取...")
                token = _extract_token_from_links(page)
            if not token:
                log("错误：无法获取 token")
                page.screenshot(path=os.path.join(SCRIPT_DIR, "debug_no_token.png"))
                return None
            log(f"Token: {token}")

            # 3. 抓取发布记录页（所有已发布文章）
            articles = _scrape_publish_records(page, token)

            if articles:
                with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
                    json.dump(articles, f, ensure_ascii=False, indent=2)
                log(f"保存 {len(articles)} 篇文章到 {OUTPUT_JSON}")
                _sync_to_db(articles)
            else:
                log("未抓取到文章数据，保存调试截图...")
                page.screenshot(path=os.path.join(SCRIPT_DIR, "debug_no_articles.png"))

            return articles

        except Exception as e:
            log(f"出错: {e}")
            import traceback
            traceback.print_exc()
            return None
        finally:
            context.close()


def _need_login(page) -> bool:
    """检查是否需要登录——通过 URL 和页面内容判断"""
    url = page.url
    # 如果 URL 包含 token，说明已登录
    if "token=" in url:
        return False
    # 如果页面上有侧边栏菜单链接，说明已登录
    try:
        has_menu = page.evaluate("""() => {
            const links = document.querySelectorAll('a[href*="token="]');
            return links.length > 0;
        }""")
        if has_menu:
            return False
    except Exception:
        pass
    # 检查是否在登录页面
    try:
        page.wait_for_selector('.weui-desktop-account__nickname, .login__type__container__scan', timeout=3000)
        # 如果找到扫码登录容器，说明需要登录
        scan_login = page.query_selector('.login__type__container__scan')
        if scan_login:
            return True
        return False
    except Exception:
        return True


def _wait_for_login(page, timeout: int = 300):
    start = time.time()
    while time.time() - start < timeout:
        if not _need_login(page):
            return
        time.sleep(2)
    raise TimeoutError("登录超时")


def _extract_token(page) -> str | None:
    """从当前页面 URL 提取 token"""
    url = page.url
    m = re.search(r'[?&]token=(\d+)', url)
    return m.group(1) if m else None


def _extract_token_from_links(page) -> str | None:
    """从页面链接中提取 token"""
    return page.evaluate("""() => {
        const links = document.querySelectorAll('a[href*="token="]');
        for (const link of links) {
            const m = link.href.match(/token=(\\d+)/);
            if (m) return m[1];
        }
        return null;
    }""")


def _scrape_publish_records(page, token: str) -> list[dict]:
    """
    从"发布记录"页面抓取所有已发布文章。

    URL: /cgi-bin/appmsgpublish?sub=list&begin=0&count=10&token=...&lang=zh_CN
    """
    all_articles = []
    begin = 0
    count = 20  # 每页条数

    while True:
        url = (
            f"https://mp.weixin.qq.com/cgi-bin/appmsgpublish"
            f"?sub=list&begin={begin}&count={count}"
            f"&token={token}&lang=zh_CN"
        )
        log(f"抓取发布记录 begin={begin}...")
        page.goto(url, wait_until="networkidle", timeout=30000)
        time.sleep(2)

        # 截图调试
        if begin == 0:
            page.screenshot(path=os.path.join(SCRIPT_DIR, "debug_publish_page.png"))

        # 解析页面
        articles = page.evaluate("""() => {
            // 已知的状态标签（不是文章标题）
            const STATUS_WORDS = ['已修改', '付费', '原创', '草稿', '转载', '定时发表', '发表成功'];

            // 清理标题：去掉 \\n付费\\n原创 等标签，过滤状态文字
            function cleanTitle(t) {
                const lines = t.split('\\n').map(s => s.trim()).filter(Boolean);
                for (const line of lines) {
                    if (!STATUS_WORDS.includes(line) && line.length > 2) {
                        return line.replace(/\\s+/g, ' ').trim();
                    }
                }
                // fallback：也跳过状态词
                for (const line of lines) {
                    if (!STATUS_WORDS.includes(line)) return line;
                }
                return '';
            }

            // 从标题中提取所有数字，用于排除
            function extractNumbers(text) {
                const nums = [];
                const matches = text.match(/\\d[\\d,]*/g);
                if (matches) {
                    for (const m of matches) {
                        nums.push(parseInt(m.replace(/,/g, '')));
                    }
                }
                return nums;
            }

            const results = [];

            // 方法1：表格行（统计列独立，不受标题数字干扰）
            const rows = document.querySelectorAll('table tbody tr, .weui-desktop-table__row');
            for (const row of rows) {
                const cells = row.querySelectorAll('td, .weui-desktop-table__cell');
                if (cells.length >= 2) {
                    const title = cleanTitle(cells[0]?.innerText || '');
                    const numbers = [];
                    for (let i = 1; i < cells.length; i++) {
                        const text = (cells[i]?.innerText || '').replace(/,/g, '').trim();
                        const n = parseInt(text);
                        if (!isNaN(n) && n >= 0) numbers.push(n);
                    }
                    if (title && title.length > 2 && numbers.length > 0) {
                        results.push({
                            title,
                            reads: numbers[0] || 0,
                            shares: numbers[1] || 0,
                            favorites: numbers[2] || 0,
                            likes: numbers[3] || 0,
                        });
                    }
                }
            }

            // 方法2：文章卡片
            if (results.length === 0) {
                const cards = document.querySelectorAll(
                    '.weui-desktop-media-appmsg, .appmsg_item, .js_appmsg_item, .card_item'
                );
                for (const card of cards) {
                    const titleEl = card.querySelector(
                        '.weui-desktop-media-appmsg__title, .appmsg_title, .card_title, h4, h3'
                    );
                    const title = cleanTitle(titleEl?.innerText || '');
                    if (!title || title.length <= 2) continue;
                    // 排除标题文本中的数字，只从非标题区域提取统计数字
                    const titleNums = extractNumbers(title);
                    const titleText = titleEl?.innerText || '';
                    const bodyText = card.innerText.replace(titleText, '');
                    const nums = bodyText.match(/(\\d[\\d,]*)/g);
                    if (nums && nums.length > 0) {
                        const parsed = nums.map(n => parseInt(n.replace(/,/g, '')));
                        // 过滤掉标题中出现的数字
                        const filtered = parsed.filter(n => !titleNums.includes(n));
                        if (filtered.length > 0) {
                            results.push({
                                title,
                                reads: filtered[0] || 0,
                                shares: filtered[1] || 0,
                                favorites: filtered[2] || 0,
                                likes: filtered[3] || 0,
                            });
                        }
                    }
                }
            }

            // 方法3：任意带标题和数字的元素
            if (results.length === 0) {
                const items = document.querySelectorAll('[class*="appmsg"], [class*="article"], [class*="item"]');
                for (const item of items) {
                    const titleEl = item.querySelector('h4, h3, .title, [class*="title"]');
                    const title = cleanTitle(titleEl?.innerText || '');
                    if (!title || title.length <= 2) continue;
                    const titleNums = extractNumbers(title);
                    const titleText = titleEl?.innerText || '';
                    const bodyText = item.innerText.replace(titleText, '');
                    const nums = bodyText.match(/(\\d[\\d,]*)/g);
                    if (nums && nums.length >= 1) {
                        const parsed = nums.map(n => parseInt(n.replace(/,/g, '')));
                        const filtered = parsed.filter(n => !titleNums.includes(n));
                        if (filtered.length > 0) {
                            results.push({
                                title,
                                reads: filtered[0] || 0,
                                shares: filtered.length > 1 ? filtered[1] : 0,
                                favorites: filtered.length > 2 ? filtered[2] : 0,
                                likes: filtered.length > 3 ? filtered[3] : 0,
                            });
                        }
                    }
                }
            }

            return results;
        }""")

        # 始终保存第一页 HTML 以便调试
        if begin == 0:
            html = page.content()
            debug_html_path = os.path.join(SCRIPT_DIR, "debug_publish_page.html")
            with open(debug_html_path, "w", encoding="utf-8") as f:
                f.write(html)
            log(f"保存页面 HTML 到 {debug_html_path}")

        if not articles:
            log(f"begin={begin} 未找到文章，停止翻页")
            break

        all_articles.extend(articles)
        log(f"  本页 {len(articles)} 篇，累计 {len(all_articles)} 篇")

        # 检查是否有下一页：用分页控件判断
        has_next = page.evaluate("""() => {
            // 方法1：查找"下一页"按钮且非禁用状态
            const nextBtns = document.querySelectorAll(
                '.weui-desktop-pagination__btn--next, a.page-next, [class*="pagination"] button, [class*="pagination"] a'
            );
            for (const btn of nextBtns) {
                const text = btn.innerText.trim();
                if ((text === '下一页' || text === '>' || text === '»') &&
                    !btn.disabled && !btn.classList.contains('disabled')) {
                    return true;
                }
            }

            // 方法2：检查页码，看是否有比当前更大的页码
            const pages = document.querySelectorAll(
                '.weui-desktop-pagination__num, .page-num, [class*="pagination"] a'
            );
            for (const p of pages) {
                const num = parseInt(p.innerText);
                if (!isNaN(num) && num > 1 && p.offsetParent !== null) return true;
            }

            return false;
        }""")

        if not has_next:
            log("没有更多页了")
            break

        begin += count

        # 安全限制
        if begin >= 500:
            log("达到最大页数限制")
            break

    # 按标题去重，保留阅读数最高的记录
    seen = {}
    for item in all_articles:
        title = item["title"]
        if title not in seen or item["reads"] > seen[title]["reads"]:
            seen[title] = item
    deduped = list(seen.values())
    deduped.sort(key=lambda x: x["reads"], reverse=True)

    log(f"共抓取 {len(all_articles)} 篇，去重后 {len(deduped)} 篇")
    return deduped


def _sync_to_db(articles: list[dict]):
    """将抓取数据同步到数据库"""
    import random
    from database import SessionLocal
    from models import Article, ArticleStat

    db = SessionLocal()
    try:
        db_articles = db.query(Article).all()
        db_by_title = {(a.title or "").strip(): a for a in db_articles}

        updated = 0
        created = 0
        now = datetime.now(timezone.utc)

        _STATUS_TITLES = {"已修改", "付费", "原创", "草稿", "转载", "定时发表", "发表成功"}
        for item in articles:
            # 安全清理：去掉标题中的换行和标签文字
            title = item["title"].split("\n")[0].strip()
            if title in _STATUS_TITLES or len(title) < 3:
                continue
            reads = item.get("reads", 0)
            shares = item.get("shares", 0)
            favorites = item.get("favorites", 0)
            likes = item.get("likes", 0)

            if reads == 0 and shares == 0 and favorites == 0 and likes == 0:
                continue

            article = db_by_title.get(title)
            if not article:
                for db_t, db_a in db_by_title.items():
                    if title in db_t or db_t in title:
                        article = db_a
                        break

            if not article:
                slug = re.sub(r'[^\w\u4e00-\u9fff]+', '-', title).strip('-').lower()
                if not slug:
                    slug = f"article-{random.randint(1000, 9999)}"
                if db.query(Article).filter(Article.slug == slug).first():
                    slug = f"{slug}-{random.randint(1000, 9999)}"
                article = Article(title=title, slug=slug, file_path="", status="published")
                db.add(article)
                db.flush()
                db_by_title[title] = article
                created += 1

            article.status = "published"

            existing_stat = (
                db.query(ArticleStat)
                .filter(ArticleStat.article_id == article.id)
                .first()
            )

            if existing_stat:
                if reads >= existing_stat.read_count:
                    existing_stat.read_count = reads
                    existing_stat.share_count = shares
                    existing_stat.like_count = likes
                    existing_stat.comment_count = favorites
                    existing_stat.share_rate = round(shares / reads, 4) if reads > 0 else 0.0
                    existing_stat.like_rate = round(likes / reads, 4) if reads > 0 else 0.0
                    existing_stat.fetched_at = now
                    updated += 1
                else:
                    existing_stat.fetched_at = now
            else:
                db.add(ArticleStat(
                    article_id=article.id,
                    read_count=reads,
                    share_count=shares,
                    like_count=likes,
                    comment_count=favorites,
                    share_rate=round(shares / reads, 4) if reads > 0 else 0.0,
                    like_rate=round(likes / reads, 4) if reads > 0 else 0.0,
                    fetched_at=now,
                ))
                created += 1

        db.commit()

        from sqlalchemy import func
        total = db.query(Article).count()
        total_reads = db.query(func.sum(ArticleStat.read_count)).scalar() or 0

        log(f"DB 同步完成: 更新 {updated}, 新建 {created}, 总文章 {total}, 总阅读 {total_reads}")

    except Exception as e:
        db.rollback()
        log(f"DB 同步失败: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="微信公众号后台数据抓取")
    parser.add_argument("--login", action="store_true", help="仅登录并保存 session")
    parser.add_argument("--headless", action="store_true", help="无头模式")
    args = parser.parse_args()

    result = scrape_articles(headless=args.headless, login_only=args.login)
    if result:
        log(f"完成！共 {len(result)} 篇文章")
