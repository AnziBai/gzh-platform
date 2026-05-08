"""
generate_service.py — 调用 Claude Code 子进程生成文章。

Claude Code 命令格式：
  claude --print "<prompt>" --output-format stream-json

stdout 每行是一个 JSON 对象，type 字段区分消息类型：
  - assistant: 包含实际输出文本
  - result: 最终结果（包含 cost、duration 等）
  - system: 系统消息（可忽略）
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from services.task_manager import task_manager


def _strip_ansi(text: str) -> str:
    return re.sub(r'\x1b\[[0-9;]*[mGKHF]', '', text)


def run_generate(task_id: str, topic: str, benchmark_slug: str | None = None, reference_article_slug: str | None = None):
    """
    在后台线程中运行文章生成。
    调用 claude --print <prompt> --output-format stream-json 并流式推送日志。
    """
    from config import Config

    task_manager.push_log(task_id, f"开始生成文章：{topic}", progress=5)

    # 读取 agent 规范文件，直接注入 prompt（不依赖 Claude 自己去读文件）
    agent_path = os.path.join(Config.GZHPUBLISHER_ROOT, "agents", "kuanlun-geo-writer-enhanced.md")
    try:
        with open(agent_path, "r", encoding="utf-8") as f:
            agent_spec = f.read()
    except Exception as e:
        raise RuntimeError(f"无法读取 agent 规范文件 {agent_path}: {e}")

    benchmark_hint = ""
    if benchmark_slug:
        # 读取 benchmark 文章内容
        benchmark_path = os.path.join(Config.GZHPUBLISHER_ROOT, "skills", "fuwei-geo", "references", "benchmark-articles", f"{benchmark_slug}.md")
        if os.path.exists(benchmark_path):
            with open(benchmark_path, "r", encoding="utf-8") as f:
                benchmark_content = f.read()
            benchmark_hint = f"\n\n## 仿写模式：参考爆款素材\n\n{benchmark_content}"
        else:
            benchmark_hint = f"\n参考爆款素材关键词：{benchmark_slug}"

    if reference_article_slug:
        benchmark_hint += _build_reference_article_hint(reference_article_slug)

    prompt = f"""{agent_spec}

---

## 当前任务

主题：{topic}{benchmark_hint}

请严格按照上述 agent 规范生成完整文章，直接输出 Markdown 内容（从 frontmatter `---` 开始），不要输出任何解释或思考过程。"""

    task_manager.push_log(task_id, "正在调用 Claude Code 生成文章...", progress=10)

    # 找 claude 可执行文件
    claude_bin = _find_claude_bin()
    if not claude_bin:
        raise RuntimeError("找不到 claude 可执行文件，请确认 Claude Code CLI 已安装")

    task_manager.push_log(task_id, f"使用 claude: {claude_bin}", progress=12)

    # 用 stdin 传 prompt，避免 Windows CreateProcess 32767 字符限制
    cmd = [claude_bin, "--print", "--output-format", "stream-json", "--verbose"]

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=env,
        cwd=Config.GZHPUBLISHER_ROOT,
    )

    # 写入 prompt 后关闭 stdin
    proc.stdin.write(prompt)
    proc.stdin.close()

    output_chunks = []
    progress = 15

    try:
        for raw_line in proc.stdout:
            line = raw_line.strip()
            if not line:
                continue

            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                # 非 JSON 行直接当日志推送
                clean = _strip_ansi(line)
                if clean:
                    task_manager.push_log(task_id, clean)
                continue

            msg_type = obj.get("type", "")

            if msg_type == "assistant":
                # 提取文本内容
                for block in obj.get("message", {}).get("content", []):
                    if block.get("type") == "text":
                        text = block["text"]
                        output_chunks.append(text)
                        # 推送进度日志（每行最多50字）
                        for chunk_line in text.split("\n"):
                            clean = _strip_ansi(chunk_line).strip()
                            if clean and len(clean) > 2:
                                task_manager.push_log(task_id, clean[:120])
                        progress = min(progress + 2, 85)
                        task_manager.push_log(task_id, "", progress=progress)

            elif msg_type == "result":
                duration = obj.get("duration_ms", 0)
                cost = obj.get("cost_usd", 0)
                task_manager.push_log(
                    task_id,
                    f"生成完成，耗时 {duration/1000:.1f}s，花费 ${cost:.4f}",
                    progress=90,
                )

    finally:
        proc.wait()

    if proc.returncode != 0:
        stderr = proc.stderr.read()
        raise RuntimeError(f"Claude Code 进程退出码 {proc.returncode}: {stderr[:500]}")

    full_output = "".join(output_chunks)
    if not full_output.strip():
        raise RuntimeError("Claude Code 未输出任何内容")

    # 保存到文件
    task_manager.push_log(task_id, "正在保存文章文件...", progress=92)
    saved_path = _save_article(full_output, topic, Config.ARTICLES_DIR)
    task_manager.push_log(task_id, f"已保存：{os.path.basename(saved_path)}", progress=98)

    return {"file_path": saved_path, "slug": Path(saved_path).stem}


def _find_claude_bin():
    from config import Config

    configured = (Config.CLAUDE_BIN or "").strip()
    if configured and os.path.isfile(configured):
        return configured

    """在常见位置查找 claude 可执行文件。"""
    # 1. PATH 中查找
    import shutil
    found = shutil.which("claude")
    if found:
        return found

    # 2. Windows 常见安装路径
    candidates = [
        os.path.expanduser("~/.local/bin/claude"),
        os.path.expanduser("~/AppData/Local/Programs/claude/claude.exe"),
        "C:/Users/anzib/AppData/Roaming/npm/claude",
        "C:/Users/anzib/AppData/Roaming/npm/claude.cmd",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c

    return None


def _build_reference_article_hint(reference_article_slug: str) -> str:
    from config import Config
    from services.article_service import parse_frontmatter

    slug = (reference_article_slug or "").strip()
    if not slug:
        return ""

    file_path = os.path.join(Config.ARTICLES_DIR, f"{slug}.md")
    if not os.path.exists(file_path):
        return f"\n\n## 参考爆款文章\n\n未找到本地参考文章文件：{slug}"

    parsed = parse_frontmatter(file_path)
    content = (parsed.get("content") or "").strip()
    if not content:
        return f"\n\n## 参考爆款文章：{slug}\n\n本地文件没有可用正文。"

    return f"\n\n## 参考爆款文章：{slug}\n\n{content}"


def _save_article(content: str, topic: str, articles_dir: str) -> str:
    """将生成内容保存为 .md 文件，提取 frontmatter 中的 slug 或自动生成。"""
    import re as _re
    from datetime import date

    # 尝试从 frontmatter 提取 slug
    slug = None
    fm_match = _re.match(r'^---\s*\n(.*?)\n---', content, _re.DOTALL)
    if fm_match:
        fm_text = fm_match.group(1)
        slug_match = _re.search(r'^slug:\s*(.+)$', fm_text, _re.MULTILINE)
        if slug_match:
            slug = slug_match.group(1).strip().strip('"\'')

    if not slug:
        # 用主题前10字生成 slug（去掉特殊字符）
        clean = _re.sub(r'[^\w\u4e00-\u9fff]', '-', topic[:20]).strip('-')
        slug = f"{date.today().strftime('%Y%m%d')}-{clean}"

    os.makedirs(articles_dir, exist_ok=True)
    file_path = os.path.join(articles_dir, f"{slug}.md")

    # 防止覆盖已有文件
    if os.path.exists(file_path):
        suffix = 2
        while os.path.exists(file_path):
            file_path = os.path.join(articles_dir, f"{slug}-{suffix}.md")
            suffix += 1

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    return file_path.replace("\\", "/")
