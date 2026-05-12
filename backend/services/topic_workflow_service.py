"""Topic-to-article workflow orchestration."""

import json
import os
import re
from pathlib import Path

from database import SessionLocal
from models import Article, Benchmark, KnowledgeChunk, KnowledgeFile, Topic
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

MAX_KNOWLEDGE_CHUNKS = 5
MAX_KNOWLEDGE_CHUNK_CHARS = 3000


def run_generate_brief(
    task_id: str,
    topic_id: int,
    material_ids: list[int] | None = None,
    reference_article_slug: str | None = None,
    knowledge_chunk_ids: list[int] | None = None,
):
    from config import Config

    material_ids = _normalize_ids(material_ids)
    knowledge_chunk_ids = _normalize_ids(knowledge_chunk_ids)[:MAX_KNOWLEDGE_CHUNKS]
    db = SessionLocal()
    try:
        topic = db.query(Topic).filter(Topic.id == topic_id).first()
        if not topic:
            raise RuntimeError("Topic not found")

        task_manager.push_log(task_id, f"Preparing brief for topic #{topic.id}", progress=8)
        materials = _load_materials(db, material_ids)
        knowledge_chunks = _load_knowledge_chunks(db, knowledge_chunk_ids)
        reference_hint = _load_reference_article(reference_article_slug, Config.ARTICLES_DIR)
        prompt = _build_brief_prompt(topic, materials, reference_hint, knowledge_chunks)

        client = get_ai_client(Config)
        task_manager.push_log(task_id, f"Calling AI brief writer: {client.label()}", progress=25)
        response = client.generate_text(prompt)
        brief = _parse_brief_json(response.text)

        topic.brief_json = json.dumps(brief, ensure_ascii=False)
        topic.material_ids_json = json.dumps(material_ids)
        topic.knowledge_chunk_ids_json = json.dumps(knowledge_chunk_ids)
        topic.reference_article_slug = (reference_article_slug or "").strip() or None
        topic.status = "selected"
        db.commit()

        task_manager.push_log(task_id, "Brief saved to topic", progress=95)
        return {
            "topic_id": topic.id,
            "brief": brief,
            "material_ids": material_ids,
            "knowledge_chunk_ids": knowledge_chunk_ids,
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
        knowledge_chunk_ids = _normalize_ids(json.loads(topic.knowledge_chunk_ids_json or "[]"))[:MAX_KNOWLEDGE_CHUNKS]
        materials = _load_materials(db, material_ids)
        knowledge_chunks = _load_knowledge_chunks(db, knowledge_chunk_ids)
        context_hint = _build_article_context_hint(topic, brief, materials, knowledge_chunks)
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
    seen = set()
    for value in ids:
        try:
            normalized = int(value)
        except (TypeError, ValueError):
            continue
        if normalized in seen:
            continue
        result.append(normalized)
        seen.add(normalized)
    return result


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


def _load_knowledge_chunks(db, chunk_ids: list[int]) -> list[dict]:
    if not chunk_ids:
        return []
    limited_ids = chunk_ids[:MAX_KNOWLEDGE_CHUNKS]
    rows = (
        db.query(KnowledgeChunk, KnowledgeFile)
        .join(KnowledgeFile, KnowledgeFile.id == KnowledgeChunk.file_id)
        .filter(KnowledgeChunk.id.in_(limited_ids))
        .all()
    )
    by_id = {chunk.id: (chunk, file) for chunk, file in rows}
    chunks = []
    for chunk_id in limited_ids:
        row = by_id.get(chunk_id)
        if not row:
            continue
        chunk, file = row
        content = (chunk.content or "").strip()
        if not content:
            continue
        title = (chunk.title or file.original_filename or file.filename or f"Knowledge chunk {chunk.id}").strip()
        source = (file.original_filename or file.filename or file.file_path or "knowledge base").strip()
        chunks.append(
            {
                "id": chunk.id,
                "title": title[:200],
                "source": source[:200],
                "content": content[:MAX_KNOWLEDGE_CHUNK_CHARS],
            }
        )
    return chunks


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


def _format_knowledge_chunks(knowledge_chunks: list[dict]) -> str:
    return "\n\n".join(
        f"### {item['title']}\nSource: {item['source']}\n\n{item['content']}"
        for item in knowledge_chunks
    ) or "No knowledge base snippets selected."


def _build_brief_prompt(
    topic: Topic,
    materials: list[dict],
    reference: dict | None,
    knowledge_chunks: list[dict] | None = None,
) -> str:
    materials_text = "\n\n".join(
        f"- {item['title']} ({item['material_type']}):\n{item['content'] or item['source_url'] or 'No content'}"
        for item in materials
    ) or "No fact materials selected."
    reference_text = (
        f"{reference['title']} ({reference['slug']}):\n{reference['content']}"
        if reference
        else "No reference article selected."
    )
    knowledge_text = _format_knowledge_chunks(knowledge_chunks or [])
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

Knowledge base snippets:
{knowledge_text}

Reference article:
{reference_text}

Requirements:
- Keep the brief practical for a human editor.
- Treat knowledge base snippets as user-provided context.
- Treat fact materials as external factual sources.
- Treat the reference article as structure and style inspiration only.
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


def _build_article_context_hint(
    topic: Topic,
    brief: dict,
    materials: list[dict],
    knowledge_chunks: list[dict] | None = None,
) -> str:
    material_text = "\n\n".join(
        f"### {item['title']}\n{item['content'] or item['source_url'] or 'No content'}"
        for item in materials
    ) or "No fact materials selected."
    knowledge_text = _format_knowledge_chunks(knowledge_chunks or [])
    return f"""

## Topic workflow brief

Original hotspot: {topic.title}
Platform: {topic.platform}
Hot value: {topic.hot_value}

Brief JSON:
{json.dumps(brief, ensure_ascii=False, indent=2)}

## Fact materials

{material_text}

## Knowledge base snippets

{knowledge_text}

Use knowledge base snippets as user-provided context. Use fact materials as external facts for factual claims. Use the reference article only for structure and style, not as a factual source.
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
