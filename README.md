# gzh-platform

公众号内容运营平台，包含文章生成、发布中心、选题库和数据看板。

中文同事首次部署请先看：[中文快速部署指南](docs/中文快速部署指南.md)。
想用脚本自动创建目录、安装依赖并生成 `.env`，看：[自动初始化配置示例](docs/自动初始化配置示例.md)。
维护和二次开发请看：[架构说明](docs/架构说明.md) 与 [运维手册](docs/运维手册.md)。

## Quick Start

1. Install dependencies.

```bash
cd backend
pip install -r requirements.txt

cd ../frontend
npm install
```

2. Create backend config.

```bash
cd backend
copy .env.example .env
```

3. Start services.

```bash
# terminal 1
cd backend
python app.py

# terminal 2
cd frontend
npm run dev
```

Open `http://127.0.0.1:3001/settings` first and complete the environment checks.
The SQLite database is created automatically at `backend/data/gzh_platform.db`
on first run and is intentionally not committed.

## Required Settings

### WeChat Official Account

Fill these in Settings:

- `WECHAT_APP_ID`
- `WECHAT_APP_SECRET`

The machine's public IP must be added to the WeChat Official Account backend IP whitelist. Use **Test WeChat Connection** after saving. If it fails, the most common causes are:

- wrong AppID or AppSecret
- public IP not whitelisted
- account does not have the required API permission
- local network/proxy blocks `api.weixin.qq.com`

### AI Writer

Two modes are supported.

Claude CLI:

```env
AI_PROVIDER=claude_cli
CLAUDE_BIN=C:/Users/me/AppData/Roaming/npm/claude.cmd
```

OpenAI-compatible API:

```env
AI_PROVIDER=openai_compatible
AI_BASE_URL=https://api.deepseek.com/v1
AI_API_KEY=sk-...
AI_MODEL=deepseek-chat
```

Use **Test AI Connection** after saving.

## Prompt Rules

The platform prefers local prompt files from:

- `<GZHPUBLISHER_ROOT>/agents/kuanlun-geo-writer-enhanced.md`
- `<GZHPUBLISHER_ROOT>/agents/kuanlun-article-auditor.md`

If those files do not exist, it falls back to built-in prompts:

- `backend/prompts/writer_default.md`
- `backend/prompts/auditor_default.md`

This means new users do not need this repository's private MCP or skill workflow to generate and audit articles.

## Publish Dependencies

Publishing to WeChat draft uses:

- Node.js
- `backend/publish_wenyan.mjs`
- global `@wenyan-md/mcp` with `@wenyan-md/core`
- WeChat AppID/AppSecret

The Settings page environment check reports whether these are available.

## Data Dashboard

The dashboard can fetch official WeChat data through the configured AppID/AppSecret. It also has scripts for HTML/JSON backfill:

```bash
cd backend
python scripts/sync_wechat_stats.py --source api
python scripts/sync_wechat_stats.py --source html --html-path scripts/publish_records.html --dry-run
python scripts/sync_wechat_stats.py --source json --json-path scraped_articles.json --dry-run
```

Use `--dry-run` first when importing scraped or saved data. The script reports
matched, unmatched, and ambiguous titles; ambiguous titles are skipped instead of
being written to the database.

### Keeping Analytics Fresh

The dashboard shows the latest sync status from `GET /api/analytics/sync-status`
and refreshes that local status every minute while the page is open.

For unattended updates on Windows, create a Task Scheduler job that runs:

```bat
backend\scripts\run_wechat_stats_sync.bat
```

A practical starting schedule is twice per day, for example 09:00 and 18:00.
If you publish frequently, run it every 2-4 hours. The script records the latest
success or failure in the local database, so the dashboard can show whether data
is fresh or whether the last sync failed.
