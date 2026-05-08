# gzh-platform — 公众号内容运营平台

宽论微信公众号内容运营的 Web 化界面，整合了 gzhpublisher 的全部 CLI 工作流。

## 快速启动

```bash
# 后端（Python Flask，端口 5001）
cd backend
python app.py

# 前端（React + Vite，端口 3001）
cd frontend
npm run dev
```

浏览器访问：http://localhost:3001

## 目录结构

```
gzh-platform/
├── backend/
│   ├── app.py                  ← Flask 入口 + CORS
│   ├── config.py               ← 从 .env 读环境变量
│   ├── models.py               ← SQLAlchemy 5 表（articles/benchmarks/topics/tasks/article_stats）
│   ├── database.py             ← SQLite 初始化，DB 在 data/gzh_platform.db
│   ├── publish_wenyan.mjs      ← 直调 @wenyan-md/core 发布（绕过 claude --print MCP 限制）
│   ├── routes/                 ← Flask 蓝图（articles/benchmarks/topics/analytics/tasks）
│   ├── services/
│   │   ├── generate_service.py ← claude --print 子进程生成文章（stdin 传 prompt）
│   │   ├── publish_service.py  ← 5 步发布流水线（见下方）
│   │   ├── article_service.py  ← 文章 CRUD + frontmatter 解析
│   │   ├── wechat_service.py   ← datacube 数据拉取
│   │   ├── scraper_service.py  ← 头条/新浪财经/东方财富/雪球爬虫 + 关键词过滤
│   │   └── task_manager.py     ← threading + SSE 实时推送
│   └── .env                    ← 配置文件（不进 git）
├── frontend/
│   └── src/
│       ├── pages/              ← 选题库/素材库/文章工坊/发布中心/数据看板
│       ├── components/
│       └── api/
└── CLAUDE.md
```

## 环境变量（backend/.env）

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `GZHPUBLISHER_ROOT` | gzhpublisher 项目根目录 | `C:/Users/anzib/gzhpublisher` |
| `ARTICLES_DIR` | 文章存放目录 | `$GZHPUBLISHER_ROOT/articles/published` |
| `WECHAT_APP_ID` | 微信公众号 AppID | — |
| `WECHAT_APP_SECRET` | 微信公众号 AppSecret | — |
| `FLASK_PORT` | 后端端口 | `5001` |

## 发布流水线（6 步，publish_service.py）

```
步骤 0：_dedup_frontmatter()     — 去除 auto_add_images.py 产生的重复 frontmatter 块
步骤 1：_run_auto_add_images()   — 调 gzhpublisher/scripts/auto_add_images.py 配图
步骤 2：_run_audit()             — claude --print 按 kuanlun-article-auditor 7 项清单审查
                                   FAIL → 抛异常，前端显示问题，不继续发布
步骤 3：_run_wenyan_publish()    — node publish_wenyan.mjs <file> orangeheart
                                   直调 @wenyan-md/core，不经过 claude --print
步骤 4：_run_git_commit()        — git add + commit，含 media_id
步骤 5：_persist_publish_result()— 写回 SQLite（media_id / status / publish_timestamp）
```

## 模型路由（发布流水线各步骤使用的 AI）

| 步骤 | 模型 | 说明 |
|------|------|------|
| 配图 — 向量粗排 | GLM embedding-3 | 智谱 API，段落→向量，余弦相似度 top-6 |
| 配图 — 语义精排 | GLM-4-flash | 智谱 API，top-6 候选取最匹配 1 张 |
| 文章生成 | Claude Code CLI 默认模型（Opus 4.6） | `claude --print` 子进程，stdin 传 prompt |
| 文章审查 | Claude Code CLI 默认模型（Opus 4.6） | `claude --print` 子进程，kuanlun-article-auditor |
| 渲染发布 | 无 AI | `publish_wenyan.mjs` → `@wenyan-md/core renderAndPublish()` |
| 选题评分 | 无 AI | `score_relevance()` 关键词匹配 |

## 关键设计决策

**为什么不用 `claude --print` 调 wenyan-mcp 发布？**  
`claude --print` headless 模式下 MCP server 永远处于 `pending` 状态，工具不注册，无法调用任何 MCP 工具。这是 Claude Code CLI 的架构限制，不可绕过。

**解决方案**：`publish_wenyan.mjs` 直接 `import @wenyan-md/core` 的 `renderAndPublish()`，完全绕过 Claude CLI。Node.js ESM 动态 import 需用 `pathToFileURL()` 处理 Windows 绝对路径。

**为什么 generate_service.py 把 agent 规范全文注入 prompt？**  
prompt 里只写文件路径不可靠——headless Claude 不一定读文件，即使读了也可能不严格遵守。直接注入 2400+ 行规范文本才能确保生成内容符合结构要求。

## API 端点概览

所有响应格式：`{"status": 0, "data": ..., "message": ""}`

| 端点 | 说明 |
|------|------|
| `GET /api/articles` | 文章列表 |
| `POST /api/articles/generate` | 触发生成（返回 task_id） |
| `POST /api/articles/{id}/publish` | 触发发布（返回 task_id） |
| `DELETE /api/articles/{id}` | 删除文章（已发布文章不可删） |
| `GET /api/tasks/{id}/stream` | SSE 实时日志流 |
| `GET /api/analytics/overview` | 数据看板总览 |
| `POST /api/analytics/fetch-stats` | 触发微信数据拉取 |
| `GET /api/benchmarks` | 爆款素材列表 |
| `POST /api/benchmarks` | 添加素材（支持粘贴全文，标题自动提取） |
| `DELETE /api/benchmarks/{id}` | 删除素材 |
| `GET /api/topics` | 选题库列表 |
| `POST /api/topics/scrape` | 触发选题抓取（支持 toutiao/sina/eastmoney/xueqiu/all） |

## 红线

- 任何发布操作必须经过步骤 2 审查，审查 FAIL 必须修改文章后重试，不可跳过
- 发布主题必须用 `orangeheart`，不能用 `default`
- 文章图片只能用 `<img>` HTML 标签 + 书中配图路径，不能用 Markdown `![]()` 或 Unsplash 图
- 修改 `.env`、`WECHAT_APP_ID/SECRET` 等配置前必须问用户
