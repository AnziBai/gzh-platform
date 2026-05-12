"""Publish-safe article rewriting service."""

import os
import re
from pathlib import Path

from database import SessionLocal
from models import Article, Benchmark
from services.ai_client import get_ai_client
from services.article_service import parse_frontmatter
from services.generate_service import _save_article, _validate_generated_article
from services.task_manager import task_manager


def run_rewrite_for_publish(task_id: str, slug: str, reference_benchmark_id: int | None = None) -> dict:
    from config import Config

    task_manager.push_log(task_id, f"开始生成发布前改写稿：{slug}", progress=5)
    source_path = _find_article_path(slug, Config.ARTICLES_DIR)
    if not source_path:
        raise RuntimeError(f"找不到原文：{slug}")

    parsed = parse_frontmatter(source_path)
    original_title = parsed["frontmatter"].get("title") or slug
    original_content = parsed["content"]
    reference = _load_reference(reference_benchmark_id)

    prompt = f"""你是公众号发布前编辑。请基于原文生成一个新的发布版草稿，不要覆盖原文。

要求：
1. 保留事实、数据、引用来源，不添加无法追溯的新事实。
2. 如果提供了爆款参考，只学习结构、节奏、标题角度和表达方式，不复制原文句子。
3. 输出完整 Markdown，必须从 frontmatter 的 --- 开始，并包含 title 字段。
4. 适合人工确认后再发布。

## 原文标题
{original_title}

## 原文
{original_content}

## 爆款参考
{reference or "未选择爆款参考，请保持原文事实并优化发布表达。"}
"""

    client = get_ai_client(Config)
    task_manager.push_log(task_id, f"正在调用 AI 改写：{client.label()}", progress=15)
    response = client.generate_text(prompt)
    output = response.text.strip()
    _validate_generated_article(output)

    saved_path = _save_article(output, f"{original_title}-发布版", Config.ARTICLES_DIR)
    slug_out = Path(saved_path).stem
    task_manager.push_log(task_id, f"已保存新草稿：{slug_out}", progress=92)

    db = SessionLocal()
    try:
        article = Article(
            title=_extract_title(output) or f"{original_title}-发布版",
            slug=slug_out,
            file_path=saved_path,
            status="draft",
            word_count=len(re.sub(r"\s+", "", output)),
            image_count=output.count("!["),
        )
        db.add(article)
        db.commit()
    finally:
        db.close()

    return {"file_path": saved_path, "slug": slug_out, "source_slug": slug}


def _find_article_path(slug: str, articles_dir: str) -> str | None:
    db = SessionLocal()
    try:
        article = db.query(Article).filter(Article.slug == slug).first()
        if article and article.file_path and os.path.exists(article.file_path):
            return article.file_path
    finally:
        db.close()

    candidate = os.path.join(articles_dir, f"{slug}.md")
    return candidate if os.path.exists(candidate) else None


def _load_reference(reference_benchmark_id: int | None) -> str:
    if not reference_benchmark_id:
        return ""
    db = SessionLocal()
    try:
        benchmark = db.query(Benchmark).filter(Benchmark.id == reference_benchmark_id).first()
        if not benchmark or not benchmark.file_path or not os.path.exists(benchmark.file_path):
            return ""
        parsed = parse_frontmatter(benchmark.file_path)
        return f"标题：{benchmark.title}\n来源：{benchmark.source_url or benchmark.platform or '本地素材'}\n\n{parsed['content']}"
    finally:
        db.close()


def _extract_title(content: str) -> str | None:
    match = re.search(r"^title:\s*(.+)$", content, re.MULTILINE)
    return match.group(1).strip().strip("\"'") if match else None
