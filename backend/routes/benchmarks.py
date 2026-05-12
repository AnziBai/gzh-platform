import os
from flask import Blueprint, request
from database import SessionLocal
from models import Benchmark
from utils import success_response, error_response

benchmarks_bp = Blueprint("benchmarks", __name__)
MATERIAL_TYPES = {"reference_article", "fact_material"}


@benchmarks_bp.route("/benchmarks")
def list_benchmarks():
    from config import Config
    db = SessionLocal()
    try:
        material_type = request.args.get("material_type")
        q = db.query(Benchmark).order_by(Benchmark.created_at.desc())
        if material_type in MATERIAL_TYPES:
            q = q.filter(Benchmark.material_type == material_type)
        db_records = q.all()
        result = [_serialize(b) for b in db_records]

        # Also scan filesystem for .md files not yet in DB
        bm_dir = Config.BENCHMARKS_DIR
        if os.path.isdir(bm_dir):
            db_paths = {b.file_path for b in db_records}
            _skip_files = {"index.md", "readme.md"}
            for fname in os.listdir(bm_dir):
                if not fname.endswith(".md"):
                    continue
                if fname.lower() in _skip_files:
                    continue
                fpath = os.path.join(bm_dir, fname).replace("\\", "/")
                if fpath not in db_paths:
                    item = _serialize_fs(fpath, fname)
                    if material_type in MATERIAL_TYPES and item["material_type"] != material_type:
                        continue
                    result.append(item)

        return success_response(result)
    except Exception as e:
        return error_response(str(e), 500)
    finally:
        db.close()


@benchmarks_bp.route("/benchmarks", methods=["POST"])
def create_benchmark():
    from services.article_service import parse_frontmatter
    from config import Config

    body = request.get_json(silent=True) or {}
    title = body.get("title", "").strip()
    content = body.get("content", "").strip()
    platform = body.get("platform", "manual").strip()
    source_url = body.get("source_url", "").strip()
    material_type = body.get("material_type", "reference_article").strip()

    if not title:
        return error_response("title 不能为空", 400)
    if material_type not in MATERIAL_TYPES:
        return error_response("material_type must be reference_article or fact_material", 400)

    # Sanitize title: first line only, strip newlines
    title = title.split("\n")[0].strip()[:100] or "未命名素材"

    db = SessionLocal()
    try:
        # Save to filesystem
        import re
        from datetime import date
        # Clean title: take first line, strip whitespace
        clean_title = (title or "").split("\n")[0].strip()[:50]
        slug = re.sub(r"[^\w\u4e00-\u9fff]", "-", clean_title).strip("-")
        fname = f"{date.today().strftime('%Y%m%d')}-{slug}.md"
        bm_dir = Config.BENCHMARKS_DIR
        os.makedirs(bm_dir, exist_ok=True)
        fpath = os.path.join(bm_dir, fname).replace("\\", "/")

        md_content = f"---\ntitle: {title}\nplatform: {platform}\nsource_url: {source_url}\nmaterial_type: {material_type}\n---\n\n{content}"
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(md_content)

        bm = Benchmark(
            title=title,
            platform=platform,
            source_url=source_url or None,
            file_path=fpath,
            material_type=material_type,
        )
        db.add(bm)
        db.commit()
        db.refresh(bm)
        return success_response(_serialize(bm)), 201
    except Exception as e:
        db.rollback()
        return error_response(str(e), 500)
    finally:
        db.close()


@benchmarks_bp.route("/benchmarks/<int:bm_id>", methods=["DELETE"])
def delete_benchmark(bm_id):
    db = SessionLocal()
    try:
        bm = db.query(Benchmark).filter(Benchmark.id == bm_id).first()
        if not bm:
            return error_response("Benchmark not found", 404)
        db.delete(bm)
        db.commit()
        return success_response({"deleted": bm_id})
    except Exception as e:
        db.rollback()
        return error_response(str(e), 500)
    finally:
        db.close()


@benchmarks_bp.route("/benchmarks/<int:bm_id>", methods=["PUT"])
def update_benchmark(bm_id):
    body = request.get_json(silent=True) or {}
    db = SessionLocal()
    try:
        bm = db.query(Benchmark).filter(Benchmark.id == bm_id).first()
        if not bm:
            return error_response("Benchmark not found", 404)

        material_type = body.get("material_type")
        if material_type is not None:
            material_type = str(material_type).strip()
            if material_type not in MATERIAL_TYPES:
                return error_response("material_type must be reference_article or fact_material", 400)
            bm.material_type = material_type

        for key in ("title", "platform", "source_url"):
            if key in body:
                value = body.get(key)
                setattr(bm, key, str(value).strip() if value is not None else None)

        db.commit()
        db.refresh(bm)
        return success_response(_serialize(bm))
    except Exception as e:
        db.rollback()
        return error_response(str(e), 500)
    finally:
        db.close()


@benchmarks_bp.route("/benchmarks/<int:bm_id>")
def get_benchmark(bm_id):
    from services.article_service import parse_frontmatter
    db = SessionLocal()
    try:
        bm = db.query(Benchmark).filter(Benchmark.id == bm_id).first()
        if not bm:
            return error_response("Benchmark not found", 404)
        data = _serialize(bm)
        if bm.file_path and os.path.exists(bm.file_path):
            parsed = parse_frontmatter(bm.file_path)
            data["content"] = parsed["content"]
        return success_response(data)
    except Exception as e:
        return error_response(str(e), 500)
    finally:
        db.close()


def _serialize(b: Benchmark) -> dict:
    return {
        "id": b.id,
        "title": b.title,
        "platform": b.platform,
        "source_url": b.source_url,
        "file_path": b.file_path,
        "structure_type": b.structure_type,
        "relevance_score": b.relevance_score,
        "material_type": b.material_type or "reference_article",
        "created_at": b.created_at.isoformat() if b.created_at else None,
    }


def _serialize_fs(fpath: str, fname: str) -> dict:
    from services.article_service import parse_frontmatter
    parsed = parse_frontmatter(fpath)
    fm = parsed.get("frontmatter", {})
    title = (fm.get("title") or os.path.splitext(fname)[0]).split("\n")[0].strip()[:100]
    return {
        "id": None,
        "title": title or "未命名素材",
        "platform": fm.get("platform", "unknown"),
        "source_url": fm.get("source_url"),
        "file_path": fpath,
        "structure_type": fm.get("structure_type"),
        "relevance_score": None,
        "material_type": fm.get("material_type", "reference_article"),
        "created_at": None,
    }
