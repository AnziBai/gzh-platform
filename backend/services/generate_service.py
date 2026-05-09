"""Article generation service."""

import os
import re
from pathlib import Path

from services.ai_client import find_claude_bin, get_ai_client
from services.prompt_loader import load_writer_spec
from services.task_manager import task_manager


def run_generate(
    task_id: str,
    topic: str,
    benchmark_slug: str | None = None,
    reference_article_slug: str | None = None,
):
    from config import Config

    task_manager.push_log(task_id, f"开始生成文章：{topic}", progress=5)

    writer_spec, writer_source = load_writer_spec(Config)
    task_manager.push_log(task_id, f"写作规范：{writer_source}", progress=8)

    benchmark_hint = _build_benchmark_hint(benchmark_slug)
    if reference_article_slug:
        benchmark_hint += _build_reference_article_hint(reference_article_slug)

    prompt = f"""{writer_spec}

---

## 当前任务

主题：{topic}{benchmark_hint}

请严格按照上面的写作规范生成完整文章。
只输出 Markdown 内容，必须从 frontmatter 的 `---` 开始，不要输出解释或思考过程。
"""

    client = get_ai_client(Config)
    task_manager.push_log(task_id, f"正在调用 AI 写作智能体：{client.label()}", progress=12)
    response = client.generate_text(prompt)
    full_output = response.text.strip()

    for line in full_output[:1200].splitlines():
        clean = line.strip()
        if clean:
            task_manager.push_log(task_id, clean[:120])

    if response.duration_ms is not None or response.cost_usd is not None:
        duration = f"{response.duration_ms / 1000:.1f}s" if response.duration_ms else "未知"
        cost = f"${response.cost_usd:.4f}" if response.cost_usd is not None else "未知"
        task_manager.push_log(task_id, f"生成完成，耗时 {duration}，花费 {cost}", progress=90)
    else:
        task_manager.push_log(task_id, "生成完成", progress=90)

    _validate_generated_article(full_output)

    task_manager.push_log(task_id, "正在保存文章文件...", progress=92)
    saved_path = _save_article(full_output, topic, Config.ARTICLES_DIR)
    task_manager.push_log(task_id, f"已保存：{os.path.basename(saved_path)}", progress=98)

    return {"file_path": saved_path, "slug": Path(saved_path).stem}


def _build_benchmark_hint(benchmark_slug: str | None) -> str:
    if not benchmark_slug:
        return ""

    from config import Config

    benchmark_path = os.path.join(
        Config.GZHPUBLISHER_ROOT,
        "skills",
        "fuwei-geo",
        "references",
        "benchmark-articles",
        f"{benchmark_slug}.md",
    )
    if os.path.exists(benchmark_path):
        with open(benchmark_path, "r", encoding="utf-8") as f:
            benchmark_content = f.read()
        return f"\n\n## 仿写参考爆款素材\n\n{benchmark_content}"
    return f"\n\n## 仿写参考爆款素材\n\n未找到本地素材文件，仅使用素材标识：{benchmark_slug}"


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


def _validate_generated_article(content: str) -> None:
    if not (content or "").lstrip().startswith("---"):
        raise RuntimeError("AI 生成内容缺少 frontmatter，请检查写作模型或提示词配置。")

    fm_match = re.match(r"^\s*---\s*\n(.*?)\n---", content, re.DOTALL)
    if not fm_match:
        raise RuntimeError("AI 生成内容 frontmatter 格式不完整。")

    frontmatter = fm_match.group(1)
    if not re.search(r"^title:\s*\S+", frontmatter, re.MULTILINE):
        raise RuntimeError("AI 生成内容 frontmatter 缺少 title 字段。")

    body = content[fm_match.end():].strip()
    if not body:
        raise RuntimeError("AI 生成内容缺少正文。")


def _save_article(content: str, topic: str, articles_dir: str) -> str:
    import re as _re
    from datetime import date

    slug = None
    fm_match = _re.match(r"^---\s*\n(.*?)\n---", content, _re.DOTALL)
    if fm_match:
        fm_text = fm_match.group(1)
        slug_match = _re.search(r"^slug:\s*(.+)$", fm_text, _re.MULTILINE)
        if slug_match:
            slug = slug_match.group(1).strip().strip('"\'')

    if not slug:
        clean = _re.sub(r"[^\w\u4e00-\u9fff]", "-", topic[:20]).strip("-")
        slug = f"{date.today().strftime('%Y%m%d')}-{clean}"

    os.makedirs(articles_dir, exist_ok=True)
    file_path = os.path.join(articles_dir, f"{slug}.md")

    if os.path.exists(file_path):
        suffix = 2
        while os.path.exists(file_path):
            file_path = os.path.join(articles_dir, f"{slug}-{suffix}.md")
            suffix += 1

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    return file_path.replace("\\", "/")


def _find_claude_bin():
    from config import Config

    return find_claude_bin(Config)
