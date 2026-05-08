import os
import re
import yaml


def scan_articles_dir(articles_dir):
    """扫描目录下所有 .md 文件，返回列表。"""
    results = []
    if not os.path.isdir(articles_dir):
        return results

    for filename in os.listdir(articles_dir):
        if not filename.endswith(".md"):
            continue

        file_path = os.path.join(articles_dir, filename).replace("\\", "/")
        try:
            parsed = parse_frontmatter(file_path)
            frontmatter = parsed["frontmatter"]
            content = parsed["content"]

            slug = os.path.splitext(filename)[0]
            title = frontmatter.get("title", slug)
            word_count = _count_chinese_chars(content)
            image_count = _count_images(content)

            results.append({
                "filename": filename,
                "file_path": file_path,
                "slug": slug,
                "title": title,
                "word_count": word_count,
                "image_count": image_count,
                "frontmatter": frontmatter,
                "content": content,
            })
        except Exception as e:
            print(f"[WARNING] Skipping {filename}: {e}")
            continue

    return results


def parse_frontmatter(file_path):
    """读取文件，解析 YAML frontmatter，返回 {frontmatter: dict, content: str}。"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw = f.read()
    except FileNotFoundError:
        return {"frontmatter": {}, "content": ""}

    if not raw.startswith("---"):
        return {"frontmatter": {}, "content": raw}

    # 找第二个 ---
    end = raw.find("---", 3)
    if end == -1:
        return {"frontmatter": {}, "content": raw}

    yaml_block = raw[3:end].strip()
    content = raw[end + 3:].lstrip("\n")

    try:
        frontmatter = yaml.safe_load(yaml_block) or {}
    except yaml.YAMLError as e:
        print(f"[WARNING] YAML parse error in {file_path}: {e}")
        frontmatter = {}

    return {"frontmatter": frontmatter, "content": content}


def import_articles_to_db(db_session, articles_dir):
    """扫描目录，为每个文件在数据库中创建 Article 记录（如果不存在）。"""
    from models import Article

    articles = scan_articles_dir(articles_dir)
    imported = 0

    for item in articles:
        existing = db_session.query(Article).filter(Article.slug == item["slug"]).first()
        if existing:
            continue

        article = Article(
            title=item["title"],
            slug=item["slug"],
            file_path=item["file_path"],
            status="draft",
            word_count=item["word_count"],
            image_count=item["image_count"],
        )
        db_session.add(article)
        imported += 1

    db_session.commit()
    return imported


def _count_chinese_chars(text):
    """统计中文字符数。"""
    return len(re.findall(r'[\u4e00-\u9fff]', text))


def _count_images(text):
    """统计 <img 标签数量。"""
    return len(re.findall(r'<img\s', text, re.IGNORECASE))


def infer_structure_type(title: str, content: str) -> str:
    """基于标题和正文关键词推断文章结构类型。"""
    title = title or ""
    content = content or ""

    # 标题信号
    if re.search(r'vs|与.{2,6}对比|该选哪个|区别|差异', title, re.IGNORECASE):
        return "对比分析式"
    if re.search(r'为什么.{0,4}(亏|赚)|亏钱的人|聪明人', title):
        return "痛点共鸣式"
    if re.search(r'怎么做|如何.{2,8}|操作|完整框架|识别要点', title):
        return "操作指南式"

    # 正文信号
    if re.search(r'第[一二三四五六]阶段', content):
        return "个人成长叙事式"
    if re.search(r'误区\s*[123]|痛点\s*[123]|问题\s*[123]', content):
        return "痛点共鸣式"
    if re.search(r'弹[上下中]|CDVA|带鱼法则|QR值|六字诀', content):
        return "技术概念深入解析"
    if re.search(r'回测|上证|成分股|《概率的朋友》第', content):
        return "书籍知识提取式"
    if re.search(r'破产|警示|陷阱|搞混', content):
        return "警示性叙事式"

    return "未分类"
