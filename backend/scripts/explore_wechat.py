"""
探索微信后台页面结构，找到正确的导航路径和选择器。
运行后会在每个关键页面保存截图。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BROWSER_STATE_DIR = os.path.join(SCRIPT_DIR, ".wechat_browser_state")


def explore():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            BROWSER_STATE_DIR,
            headless=False,  # 可见模式方便调试
            viewport={"width": 1400, "height": 900},
            locale="zh-CN",
        )

        page = context.pages[0] if context.pages else context.new_page()

        try:
            # 1. 打开首页
            print("[1] 打开首页...")
            page.goto("https://mp.weixin.qq.com/", wait_until="networkidle", timeout=30000)
            time.sleep(3)
            page.screenshot(path=os.path.join(SCRIPT_DIR, "explore_01_dashboard.png"))

            # 2. 打印页面标题和 URL
            print(f"  标题: {page.title()}")
            print(f"  URL: {page.url}")

            # 3. 获取左侧菜单结构
            print("\n[2] 查找侧边栏菜单...")
            menu_items = page.query_selector_all(
                'nav a, .weui-desktop-sidebar a, .sidebar a, '
                '[class*="menu"] a, [class*="nav"] a, '
                '.weui-desktop-account__nav a'
            )
            print(f"  找到 {len(menu_items)} 个菜单项:")
            for i, item in enumerate(menu_items[:30]):
                text = item.inner_text().strip()
                href = item.get_attribute("href") or ""
                if text:
                    print(f"    [{i}] {text} -> {href[:80]}")

            # 4. 尝试查找 "图文统计" 菜单
            print("\n[3] 查找 '图文统计' 菜单...")
            stat_link = page.query_selector('a:has-text("图文统计"), [href*="appmsg_stat"]')
            if stat_link:
                print(f"  找到: {stat_link.inner_text().strip()}")
                print(f"  href: {stat_link.get_attribute('href')}")
            else:
                print("  未找到 '图文统计'，尝试查找所有包含 '统计' 的元素...")
                stat_els = page.query_selector_all(':has-text("统计")')
                for el in stat_els[:10]:
                    tag = el.evaluate("el => el.tagName")
                    text = el.inner_text().strip()[:50]
                    print(f"    <{tag}> {text}")

            # 5. 尝试查找 "已发表" 或 "图文" 菜单
            print("\n[4] 查找 '已发表' / '图文' 菜单...")
            for keyword in ["已发表", "图文", "图文消息", "草稿箱"]:
                link = page.query_selector(f'a:has-text("{keyword}")')
                if link:
                    href = link.get_attribute("href") or ""
                    print(f"  '{keyword}' -> {href[:100]}")

            # 6. 尝试通过 JavaScript 获取页面路由信息
            print("\n[5] 通过 JS 探索页面结构...")
            js_result = page.evaluate("""() => {
                const links = Array.from(document.querySelectorAll('a[href]'));
                return links
                    .filter(a => a.href && a.href.includes('mp.weixin.qq.com'))
                    .map(a => ({text: a.innerText.trim().substring(0, 40), href: a.href}))
                    .filter(a => a.text)
                    .slice(0, 50);
            }""")
            print(f"  内部链接 {len(js_result)} 个:")
            for link in js_result:
                print(f"    {link['text']} -> {link['href'][:100]}")

            # 7. 尝试点击 "图文统计"
            print("\n[6] 尝试点击 '图文统计'...")
            clicked = False
            for selector in [
                'a:has-text("图文统计")',
                '[href*="appmsg_stat"]',
                'text=图文统计',
            ]:
                try:
                    el = page.query_selector(selector)
                    if el and el.is_visible():
                        el.click()
                        time.sleep(3)
                        page.screenshot(path=os.path.join(SCRIPT_DIR, "explore_02_stats.png"))
                        print(f"  点击成功，新 URL: {page.url}")
                        clicked = True
                        break
                except Exception as e:
                    print(f"  {selector} 失败: {e}")

            if not clicked:
                # 尝试悬停 "图文" 菜单展开子菜单
                print("\n  尝试悬停 '图文' 菜单...")
                for keyword in ["图文", "内容与互动"]:
                    try:
                        el = page.query_selector(f'a:has-text("{keyword}")')
                        if el:
                            el.hover()
                            time.sleep(2)
                            page.screenshot(path=os.path.join(SCRIPT_DIR, f"explore_hover_{keyword}.png"))
                            print(f"  悬停 '{keyword}' 成功")
                    except Exception:
                        pass

            # 8. 如果进入了统计页面，探索表格结构
            if clicked:
                print("\n[7] 探索统计页面表格...")
                tables = page.query_selector_all('table')
                print(f"  找到 {len(tables)} 个表格")
                for i, table in enumerate(tables[:3]):
                    rows = table.query_selector_all('tr')
                    print(f"  表格 {i}: {len(rows)} 行")
                    if rows:
                        # 打印表头
                        headers = rows[0].query_selector_all('th, td')
                        header_text = [h.inner_text().strip()[:20] for h in headers]
                        print(f"    表头: {header_text}")
                        # 打印第一行数据
                        if len(rows) > 1:
                            cells = rows[1].query_selector_all('td')
                            cell_text = [c.inner_text().strip()[:20] for c in cells]
                            print(f"    第1行: {cell_text}")

                # 获取分页信息
                pagination = page.query_selector_all('[class*="pagination"], [class*="page"]')
                print(f"  分页元素: {len(pagination)}")

            # 9. 尝试直接访问文章管理页面
            print("\n[8] 尝试直接访问文章管理页面...")
            for url_name, url in [
                ("appmsg_edit_v2", "https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit&isNew=1&type=77"),
                ("appmsg_v2_list", "https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_v2&action=list_card&begin=0&count=50&type=10"),
                ("appmsg_stat", "https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_stat&action=stat_page"),
            ]:
                try:
                    page.goto(url, wait_until="networkidle", timeout=15000)
                    time.sleep(2)
                    title = page.title()
                    page.screenshot(path=os.path.join(SCRIPT_DIR, f"explore_url_{url_name}.png"))
                    print(f"  {url_name}: 标题='{title}', URL={page.url[:100]}")
                except Exception as e:
                    print(f"  {url_name} 失败: {e}")

        except Exception as e:
            print(f"出错: {e}")
            import traceback
            traceback.print_exc()
        finally:
            context.close()


if __name__ == "__main__":
    explore()
