# gzh-platform 项目指引

这是一个公众号内容运营平台，核心目标是降低同事从热点选题到公众号草稿发布的配置和使用门槛。

## 快速启动

推荐在 Windows 上直接运行：

```powershell
.\start-dev.ps1
```

默认服务地址：

- 后端：`http://127.0.0.1:5001`
- 前端：`http://127.0.0.1:3001`

首次打开前端后先进入 `/settings`，使用配置向导完成目录、AI、公众号和发布依赖检查。

## 目录结构

```text
backend/
  app.py                  Flask 入口，注册 /api 蓝图
  config.py               从 backend/.env 读取本机配置
  database.py             SQLite 初始化和幂等补列
  models.py               SQLAlchemy 数据模型
  routes/                 articles, topics, benchmarks, materials, knowledge, settings, analytics, tasks
  services/               AI、热点源、素材沉淀、知识库、生成、改写、发布、数据同步
  prompts/                内置写作和审查提示词
frontend/
  src/pages/              选题库、素材库、文章工坊、发布中心、数据看板、设置
  src/api/                前端 API client
docs/                     面向用户和维护者的部署、架构、运维文档
```

## 核心业务流

```text
热点源/文章/搜索结果
  -> 统一 HotItem / SourceItem
  -> AI 摘要、分类、去重
  -> material_candidates 候选池
  -> 人工确认 approve/reject
  -> benchmarks 正式素材库 + Markdown 文件
  -> 文章工坊推荐素材和知识片段
  -> 文章生成
  -> 发布前改写生成新草稿
  -> 人工确认后发布到公众号草稿箱
```

真实发布是外部写入动作，自动测试和浏览器 QA 不应直接点击最终“发布”按钮，除非用户明确确认。

## 环境变量

配置来自 `backend/.env`，不要提交真实密钥。

| 变量 | 用途 |
| --- | --- |
| `GZHPUBLISHER_ROOT` | 本地内容工作区根目录 |
| `ARTICLES_DIR` | 生成文章保存目录 |
| `BENCHMARKS_DIR` | 正式素材 Markdown 保存目录 |
| `ASSETS_DIR` | 资源目录 |
| `WECHAT_APP_ID` | 微信公众号 AppID |
| `WECHAT_APP_SECRET` | 微信公众号 AppSecret |
| `WECHAT_STATS_DAYS_BACK` | 数据看板同步回溯天数 |
| `WECHAT_STATS_MAX_WORKERS` | 公众号数据同步并发数 |
| `AI_PROVIDER` | `claude_cli` 或 `openai_compatible` |
| `CLAUDE_BIN` | Claude CLI 路径 |
| `AI_BASE_URL` | OpenAI-compatible Base URL |
| `AI_API_KEY` | AI API Key |
| `AI_MODEL` | AI 模型名 |
| `AI_PRESET_PROVIDER` | 设置页模型预设 key |
| `AI_EXTRA_BODY_JSON` | 透传给模型 API 的 JSON object |
| `SEARCH_PROVIDER` | 搜索服务标识 |
| `SEARCH_API_KEY` | 搜索 API Key |
| `SEARCH_BASE_URL` | 搜索 API Base URL |
| `HOT_SOURCE_PRESETS_JSON` | 热点来源预设 JSON |
| `HTTPS_PROXY` | 可选代理 |
| `FLASK_PORT` | 后端端口，默认 5001 |
| `FLASK_DEBUG` | Flask debug 开关 |

## 数据模型

主要表：

- `articles`：文章元数据、发布状态、media_id、关联选题/素材。
- `article_stats`：公众号阅读、分享、点赞、评论等统计。
- `benchmarks`：正式素材库，支持 `reference_article` 和 `fact_material`。
- `material_candidates`：AI 自动收集候选，人工确认后进入 `benchmarks`。
- `knowledge_files`：用户上传的知识库文件。
- `knowledge_chunks`：知识库分块，供推荐和文章生成使用。
- `topics`：热点选题，保存创作简报、素材、知识片段和生成文章关联。
- `tasks`：后台任务状态。
- `sync_status`：数据看板最后一次同步状态。

SQLite 仍然不使用 Alembic；新增列和表在 `init_db()` 中幂等创建/补齐。

## 关键 API

所有 API 默认前缀为 `/api`，响应格式为 `{"status": 0, "data": ..., "message": ""}`。

| API | 用途 |
| --- | --- |
| `GET /api/articles` | 文章列表 |
| `POST /api/articles/generate` | 生成文章，支持 `material_ids`、`knowledge_chunk_ids` |
| `POST /api/articles/<slug>/rewrite-for-publish` | 发布前改写，生成新草稿 |
| `POST /api/articles/<slug>/publish` | 发布到公众号草稿箱 |
| `GET /api/articles/hot-references` | 可作为仿写参考的高表现文章 |
| `GET /api/articles/by-slug/<slug>` | 按 slug 读取文章详情 |
| `GET /api/topics` | 选题库列表 |
| `POST /api/topics/scrape` | 抓取热点，支持来源、精选/全部、分类、时间窗、关键词 |
| `POST /api/topics/<id>/brief` | 为热点生成创作简报 |
| `POST /api/topics/<id>/generate` | 基于热点简报生成文章 |
| `GET /api/benchmarks` | 正式素材列表 |
| `PUT /api/benchmarks/<id>` | 更新素材类型等字段 |
| `GET /api/materials/candidates` | 素材候选池 |
| `POST /api/materials/collect` | 从文章/热点/搜索收集素材候选 |
| `POST /api/materials/candidates/<id>/approve` | 候选入库 |
| `POST /api/materials/candidates/<id>/reject` | 拒绝候选 |
| `POST /api/knowledge/files` | 上传知识库文件 |
| `GET /api/knowledge/files` | 知识库文件列表 |
| `DELETE /api/knowledge/files/<id>` | 删除知识库文件 |
| `POST /api/knowledge/recommend` | 按主题/热点推荐知识片段和素材 |
| `GET /api/settings/model-presets` | 国内模型预设 |
| `POST /api/settings/bootstrap` | 创建本地目录并写入 `.env` |
| `POST /api/settings/setup-wizard` | 按向导保存配置 |
| `GET /api/settings/diagnostics` | 部署诊断 |
| `GET /api/tasks/<id>/stream` | SSE 任务日志 |
| `GET /api/analytics/overview` | 数据看板概览 |
| `POST /api/analytics/fetch-stats` | 同步公众号数据 |

## 发布流水线

`publish_service.py` 的发布流程：

1. 去重 frontmatter。
2. 尝试自动配图。
3. AI 审查文章质量。
4. 调用 `publish_wenyan.mjs` 使用 Wenyan 排版并推送公众号草稿箱。
5. Git 归档。
6. 写回 SQLite。

发布前改写由 `rewrite_service.py` 处理，不覆盖原文。正文生成和发布前改写都使用 `_normalize_generated_article()` 兜底修复国内模型输出缺少 frontmatter 的情况。

## 开发与验证

后端：

```powershell
C:\Users\Administrator\.codex-tools\python-3.12.10\python.exe -m pytest backend/tests -q
```

前端：

```powershell
cd frontend
npm run lint
npm run build
```

2026-05-12 验证结果：后端 `99 passed`，前端 lint/build 通过，Browser use 跑通热点、素材、知识库、文章生成、发布前改写。

## 红线

- 不提交 `backend/.env`、SQLite 数据库、密钥、运行日志。
- 不要在没有用户确认时点击真实“发布”按钮。
- 自动收集素材必须保留来源 URL；无来源事实不应进入正式素材库。
- 候选素材先进入 `material_candidates`，不要绕过人工确认直接写正式素材库。
- 发布前改写必须生成新草稿，不能覆盖原文。
