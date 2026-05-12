"""Topic-to-article workflow orchestration."""

import json
import os
import re
from pathlib import Path

from database import SessionLocal
from models import Article, Benchmark, Topic
from services.ai_client import get_ai_client
from services.article_service import parse_frontmatter
from services.generate_service import run_generate
from services.task_manager import task_manager


BRIEF_SCHEMA = {
    "recommended_title": "string",
    "title_angles": ["string"],
    "audience_pain_points": ["string"],
    "outline": ["string"],
    "usable_materials": ["string"],
    "risk_notes": ["string"],
}


def run_generate_brief(
    task_id: str,
    topic_id: int,
    material_ids: list[int] | None = None,
    reference_article_slug: str | None = None,
):
    from config import Config

    material_ids = _normalize_ids(material_ids)
    db = SessionLocal()
    try:
        topic = db.query(Topic).filter(Topic.id == topic_id).first()
        if not topic:
            raise RuntimeError("Topic not found")

        task_manager.push_log(task_id, f"Preparing brief for topic #{topic.id}", progress=8)
        materials = _load_materials(db, material_ids)
        reference_hint = _load_reference_article(reference_article_slug, Config.ARTICLES_DIR)
        prompt = _build_brief_prompt(topic, materials, reference_hint)

        client = get_ai_client(Config)
        task_manager.push_log(task_id, f"Calling AI brief writer: {client.label()}", progress=25)
        response = client.generate_text(prompt)
        brief = _parse_brief_json(response.text)

        topic.brief_json = json.dumps(brief, ensure_ascii=False)
        topic.material_ids_json = json.dumps(material_ids)
        topic.reference_article_slug = (reference_article_slug or "").strip() or None
        topic.status = "selected"
        db.commit()

        task_manager.push_log(task_id, "Brief saved to topic", progress=95)
        return {
            "topic_id": topic.id,
            "brief": brief,
            "material_ids": material_ids,
            "reference_article_slug": topic.reference_article_slug,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def run_generate_from_topic(task_id: str, topic_id: int):
    db = SessionLocal()
    try:
        topic = db.query(Topic).filter(Topic.id == topic_id).first()
        if not topic:
            raise RuntimeError("Topic not found")
        if not topic.brief_json:
            raise RuntimeError("Please generate and confirm the topic brief first")

        brief = json.loads(topic.brief_json)
        material_ids = _normalize_ids(json.loads(topic.material_ids_json or "[]"))
        materials = _load_materials(db, material_ids)
        context_hint = _build_article_context_hint(topic, brief, materials)
        reference_slug = topic.reference_article_slug

        task_manager.push_log(task_id, f"Generating article from topic #{topic.id}", progress=5)
        result = run_generate(
            task_id,
            brief.get("recommended_title") or topic.title,
            reference_article_slug=reference_slug,
            context_hint=context_hint,
        )

        article = _upsert_generated_article(db, topic, result)
        db.flush()
        topic.generated_article_id = article.id
        topic.status = "used"
        db.commit()

        result["article_id"] = article.id
        result["topic_id"] = topic.id
        return result
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _normalize_ids(ids) -> list[int]:
    if not ids:
        return []
    result = []
    for value in ids:
        try:
            result.append(int(value))
        except (TypeError, ValueError):
            continue
    return sorted(set(result))


def _load_materials(db, material_ids: list[int]) -> list[dict]:
    if not material_ids:
        return []
    records = db.query(Benchmark).filter(Benchmark.id.in_(material_ids)).all()
    by_id = {record.id: record for record in records}
    return [_serialize_material(by_id[mid]) for mid in material_ids if mid in by_id]


def _serialize_material(material: Benchmark) -> dict:
    content = ""
    if material.file_path and os.path.exists(material.file_path):
        content = parse_frontmatter(material.file_path).get("content", "")
    return {
        "id": material.id,
        "title": material.title,
        "platform": material.platform,
        "source_url": material.source_url,
        "material_type": material.material_type or "reference_article",
        "content": content.strip()[:5000],
    }


def _load_reference_article(slug: str | None, articles_dir: str) -> dict | None:
    slug = (slug or "").strip()
    if not slug:
        return None
    file_path = os.path.join(articles_dir, f"{slug}.md")
    parsed = parse_frontmatter(file_path)
    content = (parsed.get("content") or "").strip()
    return {
        "slug": slug,
        "title": parsed.get("frontmatter", {}).get("title") or slug,
        "content": content[:5000],
    }


def _build_brief_prompt(topic: Topic, materials: list[dict], reference: dict | None) -> str:
    materials_text = "\n\n".join(
        f"- {item['title']} ({item['material_type']}):\n{item['content'] or item['source_url'] or 'No content'}"
        for item in materials
    ) or "No fact materials selected."
    reference_text = (
        f"{reference['title']} ({reference['slug']}):\n{reference['content']}"
        if reference
        else "No reference article selected."
    )
    schema = json.dumps(BRIEF_SCHEMA, ensure_ascii=False, indent=2)
    return f"""
You are preparing a Chinese WeChat article brief for a finance content team.
Return valid JSON only. Do not wrap it in Markdown fences.

Schema:
{schema}

Topic:
- title: {topic.title}
- platform: {topic.platform}
- hot_value: {topic.hot_value}
- source_url: {topic.source_url or ""}

Fact materials:
{materials_text}

Reference article:
{reference_text}

Requirements:
- Keep the brief practical for a human editor.
- Separate facts from style inspiration.
- Include risk notes for claims that need verification or may be sensitive.
"""


def _parse_brief_json(raw: str) -> dict:
    text = (raw or "").strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"AI brief response was not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise RuntimeError("AI brief response must be a JSON object")
    for key in BRIEF_SCHEMA:
        data.setdefault(key, [] if key != "recommended_title" else "")
    return data


def _build_article_context_hint(topic: Topic, brief: dict, materials: list[dict]) -> str:
    material_text = "\n\n".join(
        f"### {item['title']}\n{item['content'] or item['source_url'] or 'No content'}"
        for item in materials
    ) or "No fact materials selected."
    return f"""

## Topic workflow brief

Original hotspot: {topic.title}
Platform: {topic.platform}
Hot value: {topic.hot_value}

Brief JSON:
{json.dumps(brief, ensure_ascii=False, indent=2)}

## Fact materials

{material_text}

Use fact materials for factual claims. Use the reference article only for structure and style, not as a factual source.
"""


def _upsert_generated_article(db, topic: Topic, result: dict) -> Article:
    file_path = result.get("file_path")
    slug = result.get("slug") or (Path(file_path).stem if file_path else None)
    if not file_path or not slug:
        raise RuntimeError("Generated article result is missing file_path or slug")

    article = db.query(Article).filter(Article.slug == slug).first()
    parsed = parse_frontmatter(file_path)
    title = parsed.get("frontmatter", {}).get("title") or topic.title
    content = parsed.get("content") or ""
    if not article:
        article = Article(slug=slug, title=title, status="draft")
        db.add(article)

    article.title = title
    article.file_path = file_path
    article.topic_id = topic.id
    article.word_count = len(re.findall(r"[\u4e00-\u9fff]", content))
    article.image_count = len(re.findall(r"<img\s", content, re.IGNORECASE))
    return article
