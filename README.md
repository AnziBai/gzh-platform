# 公众号内容平台

面向公众号团队的内容运营工作台，覆盖“热点抓取 -> AI 素材沉淀 -> 知识库辅助写作 -> 文章生成 -> 发布前改写 -> 公众号草稿发布”的完整流程。

这版重点升级了开箱即用体验：新环境可以通过设置页向导自动创建目录并写入基础配置；内容生产可以从热点自动沉淀素材，并在文章工坊里自动推荐知识库片段、事实素材和爆款参考。

## 最新更新

- 热点抓取升级为统一来源适配器，支持财经热点和 AI 热点风格来源，抓取后自动进入选题库。
- 抓到的热点会先沉淀到“AI 自动收集候选”，由 AI 判断为事实资料或爆款参考，人工确认后进入正式素材库。
- 素材库支持两类素材：`fact_material` 事实资料、`reference_article` 爆款范文。
- 新增知识库上传，支持 Markdown、TXT、PDF 文件。Markdown/TXT 可直接使用；PDF 需要安装 `pypdf`。
- 文章工坊可以按主题和热点智能推荐知识库片段、事实素材和爆款参考，再生成正文。
- 发布中心新增“发布前改写”，不会覆盖原文，会生成新的发布版草稿，人工确认后再发布。
- 设置页新增配置向导、部署诊断、国内模型预设和开箱即用进度。
- 支持 OpenAI-compatible 国内模型接入，包括 DeepSeek、通义百炼、智谱 GLM、Kimi/Moonshot、火山方舟/豆包、MiMo/TokenPlan、自定义兼容接口。
- 对国内模型输出做了健壮性兜底：正文生成和发布前改写即使缺少标准 frontmatter，也会自动补齐后再保存。
- 移动端布局已修复，小屏会切换为顶部导航，文章工坊不再被侧栏挤压。

## 快速开始

### Windows

```powershell
.\start-dev.ps1
```

脚本会自动：

- 创建后端 Python 虚拟环境。
- 安装后端依赖。
- 安装前端依赖。
- 启动 Flask 后端和 Vite 前端。

默认地址：

- 后端：`http://127.0.0.1:5001`
- 前端：`http://127.0.0.1:3001`

打开前端后，先进入“设置”页，点击“配置向导”，按步骤完成本机配置。

### Mac / Linux

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

另开一个终端：

```bash
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 3001
```

## 首次部署流程

1. 打开 `http://127.0.0.1:3001/settings`。
2. 点击“配置向导”。
3. 选择或填写本地工作目录。
4. 一键创建文章目录、素材目录、数据库目录，并写入 `backend/.env`。
5. 选择 AI 模型预设，填写 API Key、Base URL、Model。
6. 填写微信公众号 AppID/AppSecret。
7. 在公众号后台把本机公网 IP 加入白名单。
8. 回到设置页点击测试连接。
9. 确认“开箱即用进度”中的能力项变绿。

配置只保存在当前电脑的 `backend/.env`。密钥字段不会回显，留空保存时会保留原有密钥。

## 核心业务流程

### 1. 抓取热点

进入“选题库”：

- 选择来源，例如财经热点、AI 热点或全部来源。
- 选择精选/全部、时间窗、分类、关键词。
- 点击“全部平台抓取”或指定平台按钮。

抓取完成后，系统会：

- 将热点写入选题库。
- 过滤金融相关内容。
- 自动生成素材候选。
- 保留来源 URL，方便后续事实追溯。

### 2. 审核素材候选

进入“素材库”：

- 查看“AI 自动收集候选”。
- 确认候选是事实资料还是爆款参考。
- 点击“入库”“改类入库”或“忽略”。

入库后，素材会同时进入数据库和本地 Markdown 文件，兼容原有文件素材机制。

### 3. 上传知识库

在“素材库”的 Knowledge Base 区域上传：

- `.md`
- `.txt`
- `.pdf`

知识库适合放团队内部文档、产品资料、案例库、方法论、行业研究、历史文章复盘。文章工坊会根据主题和热点自动挑选相关片段。

注意：PDF 上传依赖 `pypdf`。如果设置页提示缺少 PDF parser，Markdown/TXT 仍然可正常使用。

### 4. 生成文章

进入“文章工坊”：

1. 输入文章主题。
2. 可选选择热点。
3. 可选选择知识文件范围。
4. 点击“智能推荐素材”。
5. 检查系统推荐的知识片段、事实素材、爆款参考。
6. 点击“生成文章”。

生成成功后，文章会保存到 `ARTICLES_DIR`，并出现在文章列表和发布中心。

### 5. 发布前改写

进入“发布中心”：

1. 找到待发布文章。
2. 可选选择爆款参考。
3. 点击“发布前改写”。
4. 系统生成新的发布版草稿，不覆盖原文。
5. 人工确认后再点击“发布”。

最终“发布”会调用 Wenyan 排版并推送到微信公众号草稿箱，属于真实外部写入操作。

## AI 模型配置

推荐优先使用 OpenAI-compatible 模式：

```env
AI_PROVIDER=openai_compatible
AI_BASE_URL=https://api.deepseek.com/v1
AI_API_KEY=sk-...
AI_MODEL=deepseek-chat
```

设置页提供常用国内模型预设：

- DeepSeek
- 通义百炼
- 智谱 GLM
- Kimi / Moonshot
- 火山方舟 / 豆包
- MiMo / TokenPlan
- 自定义 OpenAI-compatible

部分模型支持额外参数透传：

```env
AI_EXTRA_BODY_JSON={"enable_thinking":false}
```

如果模型返回格式不稳定，系统会尽量自动规范化 Markdown 和 frontmatter，降低用户配置提示词的成本。

## 微信公众号配置

设置页填写：

- `WECHAT_APP_ID`
- `WECHAT_APP_SECRET`

还需要在微信公众号后台添加本机公网 IP 白名单。测试失败时优先检查：

- AppID/AppSecret 是否正确。
- 当前公网 IP 是否已加入白名单。
- 公众号是否有对应 API 权限。
- 本机网络或代理是否阻断 `api.weixin.qq.com`。

## 发布依赖

发布到公众号草稿箱依赖：

- Node.js
- `backend/publish_wenyan.mjs`
- 全局 `@wenyan-md/mcp`
- 微信公众号 AppID/AppSecret

设置页的“部署环境检查”会显示这些依赖是否可用。

## 数据看板

数据看板可以通过公众号 API 同步阅读、分享等数据。也支持 HTML/JSON 回填：

```bash
cd backend
python scripts/sync_wechat_stats.py --source api
python scripts/sync_wechat_stats.py --source html --html-path scripts/publish_records.html --dry-run
python scripts/sync_wechat_stats.py --source json --json-path scraped_articles.json --dry-run
```

建议先使用 `--dry-run`，确认匹配结果后再正式写入。

## 常用命令

后端测试：

```powershell
C:\Users\Administrator\.codex-tools\python-3.12.10\python.exe -m pytest backend/tests -q
```

前端检查：

```bash
cd frontend
npm run lint
npm run build
```

普通环境也可以使用：

```bash
cd backend
python -m pytest tests -q
```

## 近期验证结果

2026-05-12 本地验证：

- 后端测试：`99 passed`
- 前端 lint：通过
- 前端 build：通过
- Browser use 业务流：热点抓取、素材候选入库、知识库、文章生成、发布前改写均通过。

未自动执行的动作：

- 最终点击“发布”到微信公众号草稿箱。该动作会产生真实外部写入，需要人工确认后执行。

## 目录说明

- `backend/`：Flask API、SQLite 模型、AI 调用、发布和同步服务。
- `frontend/`：React + Ant Design 前端工作台。
- `backend/prompts/`：内置写作和审查提示词。
- `docs/`：部署、架构、运维等说明文档。
- `start-dev.ps1`：Windows 一键启动脚本。

## 进一步文档

- [自动初始化配置示例](docs/自动初始化配置示例.md)
- [中文快速部署指南](docs/中文快速部署指南.md)
- [架构说明](docs/架构说明.md)
- [运维手册](docs/运维手册.md)
