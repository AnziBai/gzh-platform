"""Collect, classify, and approve reusable materials."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date
from typing import Iterable

import requests

from database import SessionLocal
from models import Article, ArticleStat, Benchmark, MaterialCandidate, Topic

MATERIAL_TYPES = {"reference_article", "fact_material"}


def source_hash(*parts: str | None) -> str:
    joined = "\n".join((part or "").strip() for part in parts if part is not None)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def collect_from_hot_items(task_id: str | None, hot_items: Iterable[dict], topic_ids: list[int | None] | None = None) -> dict:
    from services.task_manager import task_manager

    created = 0
    failed = 0
    topic_ids = topic_ids or []
    db = SessionLocal()
    try:
        for index, item in enumerate(hot_items):
            title = (item.get("title") or "").strip()
            if not title:
                continue
            topic_id = topic_ids[index] if index < len(topic_ids) else None
            try:
                content = _candidate_content(item)
                classification = classify_material(title, content, item.get("source_url"), "hot_topic")
                candidate = upsert_candidate(
                    db,
                    title=title,
                    content=content,
                    source_url=item.get("source_url"),
                    platform=item.get("platform") or "unknown",
                    suggested_material_type=classification["material_type"],
                    confidence=classification["confidence"],
                    classification_reason=classification["reason"],
                    source_kind="hot_topic",
                    topic_id=topic_id,
                )
                if candidate:
                    created += 1
            except Exception as exc:
                failed += 1
                if task_id:
                    task_manager.push_log(task_id, f"素材候选生成失败: {title[:40]} - {exc}")
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return {"created": created, "failed": failed}


def collect_from_topic_ids(task_id: str, topic_ids: list[int] | None = None) -> dict:
    db = SessionLocal()
    try:
        q = db.query(Topic)
        if topic_ids:
            q = q.filter(Topic.id.in_(topic_ids))
        topics = q.order_by(Topic.discovered_at.desc()).limit(100).all()
        items = [
            {
                "title": topic.title,
                "source_url": topic.source_url,
                "platform": topic.platform,
                "summary": topic.relevance_reason,
            }
            for topic in topics
        ]
        ids = [topic.id for topic in topics]
    finally:
        db.close()
    return collect_from_hot_items(task_id, items, ids)


def collect_from_articles(task_id: str, only_hot: bool = False) -> dict:
    db = SessionLocal()
    created = 0
    try:
        articles = db.query(Article).order_by(Article.updated_at.desc()).limit(100).all()
        for article in articles:
            latest = _latest_stat(article)
            is_hot = bool(latest and (latest.read_count or 0) > 500)
            if only_hot and not is_hot:
                continue
            content = _read_file(article.file_path)
            if not content:
                continue
            material_type = "reference_article" if is_hot else "fact_material"
            candidate = upsert_candidate(
                db,
                title=article.title,
                content=_truncate(content, 4000),
                source_url=article.file_path,
                platform="article",
                suggested_material_type=material_type,
                confidence=0.82 if is_hot else 0.66,
                classification_reason="高阅读文章沉淀为爆款参考" if is_hot else "文章内容可拆为事实素材",
                source_kind="published_article" if is_hot else "generated_article",
                article_id=article.id,
            )
            if candidate:
                created += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return {"created": created, "failed": 0}


def collect_from_search(task_id: str, keyword: str) -> dict:
    from config import Config

    keyword = (keyword or "").strip()
    if not keyword:
        raise RuntimeError("keyword 不能为空")
    provider = (Config.SEARCH_PROVIDER or "").strip()
    if not provider:
        return {"created": 0, "failed": 0, "message": "未配置搜索 Provider"}
    if provider != "custom":
        return {"created": 0, "failed": 0, "message": f"暂不支持搜索 Provider: {provider}"}
    if not Config.SEARCH_BASE_URL:
        raise RuntimeError("SEARCH_BASE_URL 未配置")

    response = requests.get(
        Config.SEARCH_BASE_URL,
        params={"q": keyword},
        headers={"Authorization": f"Bearer {Config.SEARCH_API_KEY}"} if Config.SEARCH_API_KEY else {},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    rows = payload.get("items") or payload.get("results") or []

    db = SessionLocal()
    created = 0
    try:
        for row in rows[:10]:
            url = row.get("url") or row.get("link") or row.get("source_url")
            if not url:
                continue
            title = row.get("title") or url
            content = row.get("summary") or row.get("snippet") or ""
            classification = classify_material(title, content, url, "search_result")
            candidate = upsert_candidate(
                db,
                title=title,
                content=content,
                source_url=url,
                platform=row.get("source") or "search",
                suggested_material_type=classification["material_type"],
                confidence=classification["confidence"],
                classification_reason=classification["reason"],
                source_kind="search_result",
            )
            if candidate:
                created += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return {"created": created, "failed": 0}


def classify_material(title: str, content: str | None, source_url: str | None, source_kind: str) -> dict:
    text = f"{title}\n{content or ''}".lower()
    if source_kind in {"published_article", "generated_article"}:
        return {"material_type": "reference_article", "confidence": 0.8, "reason": "文章成品适合作为结构与表达参考"}
    reference_markers = ["爆款", "阅读", "评论", "观点", "深度", "专访", "复盘", "analysis", "opinion"]
    fact_markers = ["数据", "公告", "政策", "财报", "报告", "发布", "融资", "模型", "论文", "研究"]
    reference_score = sum(1 for marker in reference_markers if marker in text)
    fact_score = sum(1 for marker in fact_markers if marker in text)
    if reference_score > fact_score + 1:
        return {"material_type": "reference_article", "confidence": 0.68, "reason": "更像观点型或文章型参考"}
    return {"material_type": "fact_material", "confidence": 0.72, "reason": "包含可追溯事实、事件或数据线索"}


def upsert_candidate(
    db,
    *,
    title: str,
    content: str | None,
    source_url: str | None,
    platform: str,
    suggested_material_type: str,
    confidence: float,
    classification_reason: str,
    source_kind: str,
    topic_id: int | None = None,
    article_id: int | None = None,
) -> MaterialCandidate | None:
    if suggested_material_type not in MATERIAL_TYPES:
        suggested_material_type = "fact_material"
    digest = source_hash(source_url, title, source_kind)
    exists = (
        db.query(MaterialCandidate)
        .filter(MaterialCandidate.source_hash == digest)
        .filter(MaterialCandidate.suggested_material_type == suggested_material_type)
        .first()
    )
    if exists:
        return None
    exists_benchmark = (
        db.query(Benchmark)
        .filter(Benchmark.source_hash == digest)
        .filter(Benchmark.material_type == suggested_material_type)
        .first()
    )
    if exists_benchmark:
        return None
    candidate = MaterialCandidate(
        title=title[:200],
        content=_truncate(content or "", 6000),
        source_url=source_url,
        platform=platform or "unknown",
        suggested_material_type=suggested_material_type,
        status="candidate",
        confidence=confidence,
        classification_reason=classification_reason,
        source_kind=source_kind,
        topic_id=topic_id,
        article_id=article_id,
        source_hash=digest,
    )
    db.add(candidate)
    return candidate


def approve_candidate(candidate_id: int, material_type: str | None = None) -> dict:
    from config import Config

    db = SessionLocal()
    try:
        candidate = db.query(MaterialCandidate).filter(MaterialCandidate.id == candidate_id).first()
        if not candidate:
            raise RuntimeError("Material candidate not found")
        selected_type = material_type or candidate.suggested_material_type
        if selected_type not in MATERIAL_TYPES:
            raise RuntimeError("material_type must be reference_article or fact_material")
        existing = (
            db.query(Benchmark)
            .filter(Benchmark.source_hash == candidate.source_hash)
            .filter(Benchmark.material_type == selected_type)
            .first()
        )
        if existing:
            candidate.status = "approved"
            db.commit()
            return {"benchmark_id": existing.id, "deduplicated": True}

        file_path = _write_benchmark_file(Config.BENCHMARKS_DIR, candidate, selected_type)
        benchmark = Benchmark(
            title=candidate.title,
            platform=candidate.platform,
            source_url=candidate.source_url,
            file_path=file_path,
            material_type=selected_type,
            source_kind=candidate.source_kind,
            source_hash=candidate.source_hash,
            classification_reason=candidate.classification_reason,
            approved_from_candidate_id=candidate.id,
        )
        db.add(benchmark)
        candidate.status = "approved"
        db.commit()
        db.refresh(benchmark)
        return {"benchmark_id": benchmark.id, "deduplicated": False}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def reject_candidate(candidate_id: int) -> dict:
    db = SessionLocal()
    try:
        candidate = db.query(MaterialCandidate).filter(MaterialCandidate.id == candidate_id).first()
        if not candidate:
            raise RuntimeError("Material candidate not found")
        candidate.status = "rejected"
        db.commit()
        return {"candidate_id": candidate_id}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _candidate_content(item: dict) -> str:
    pieces = [item.get("summary") or ""]
    if item.get("source_url"):
        fetched = _fetch_source_excerpt(item.get("source_url"))
        if fetched:
            pieces.append(fetched)
    return _truncate("\n\n".join(piece for piece in pieces if piece), 5000)


def _fetch_source_excerpt(url: str | None) -> str:
    if not url or not str(url).startswith(("http://", "https://")):
        return ""
    try:
        response = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", response.text, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return _truncate(text, 2000)
    except Exception:
        return ""


def _write_benchmark_file(root: str, candidate: MaterialCandidate, material_type: str) -> str:
    os.makedirs(root, exist_ok=True)
    slug = re.sub(r"[^\w\u4e00-\u9fff]", "-", candidate.title[:50]).strip("-") or f"material-{candidate.id}"
    path = os.path.join(root, f"{date.today().strftime('%Y%m%d')}-{slug}.md").replace("\\", "/")
    suffix = 2
    base, ext = os.path.splitext(path)
    while os.path.exists(path):
        path = f"{base}-{suffix}{ext}"
        suffix += 1
    frontmatter = {
        "title": candidate.title,
        "platform": candidate.platform,
        "source_url": candidate.source_url or "",
        "material_type": material_type,
        "source_kind": candidate.source_kind,
        "source_hash": candidate.source_hash,
    }
    fm = "\n".join(f"{key}: {value}" for key, value in frontmatter.items())
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"---\n{fm}\n---\n\n{candidate.content or candidate.title}\n")
    return path


def _latest_stat(article: Article):
    if not article.stats:
        return None
    return max(article.stats, key=lambda stat: stat.fetched_at)


def _read_file(path: str | None) -> str:
    if not path or not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _truncate(text: str, limit: int) -> str:
    return (text or "").strip()[:limit]
