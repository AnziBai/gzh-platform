"""Publish article drafts to WeChat."""

import json
import os
import re
import subprocess
from datetime import datetime, timezone

from services.ai_client import find_claude_bin, get_ai_client
from services.prompt_loader import load_auditor_spec, load_writer_spec
from services.task_manager import task_manager


def run_publish(task_id: str, file_path: str):
    from config import Config

    task_manager.push_log(task_id, f"准备发布：{os.path.basename(file_path)}", progress=5)
    if not os.path.exists(file_path):
        raise RuntimeError(f"文章文件不存在：{file_path}")

    _run_auto_add_images(task_id, file_path, Config)
    _dedup_frontmatter(task_id, file_path)
    _run_audit(task_id, file_path, Config)
    media_id = _run_wenyan_publish(task_id, file_path, Config)
    _run_git_commit(task_id, file_path, media_id, Config)

    if media_id:
        _persist_publish_result(file_path, media_id)
        task_manager.push_log(task_id, "已写入数据库", progress=100)

    return {"media_id": media_id, "file_path": file_path}


def _run_auto_add_images(task_id: str, file_path: str, Config):
    task_manager.push_log(task_id, "步骤1：自动配图...", progress=10)

    script = os.path.join(Config.GZHPUBLISHER_ROOT, "scripts", "auto_add_images.py")
    if not os.path.exists(script):
        task_manager.push_log(task_id, f"配图脚本不存在，跳过：{script}")
        return

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    try:
        proc = subprocess.run(
            ["python", script, file_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            env=env,
            cwd=Config.GZHPUBLISHER_ROOT,
        )
        if proc.returncode == 0:
            for line in proc.stdout.strip().split("\n"):
                line = line.strip()
                if line and not line.startswith("正在为文章"):
                    task_manager.push_log(task_id, f"[配图] {line[:120]}")
            task_manager.push_log(task_id, "配图完成", progress=25)
        else:
            err = (proc.stderr or proc.stdout or "")[:300]
            task_manager.push_log(task_id, f"配图报错，继续审查：{err}")
    except subprocess.TimeoutExpired:
        task_manager.push_log(task_id, "配图超时，跳过")
    except Exception as exc:
        task_manager.push_log(task_id, f"配图异常，继续审查：{exc}")


def _run_audit(task_id: str, file_path: str, Config):
    task_manager.push_log(task_id, "步骤2：审查文章质量...", progress=30)

    with open(file_path, "r", encoding="utf-8") as f:
        article_content = f.read()

    writer_spec, writer_source = load_writer_spec(Config)
    auditor_spec, auditor_source = load_auditor_spec(Config)
    prompt = f"""你是公众号文章质量审查员。请严格按照以下两份规范审查文章。

=== 写作规范 ===

{writer_spec}

=== 审查规范 ===

{auditor_spec}

=== 待审查文章 ===

{article_content}

请只输出审查报告。审查结果必须明确写成 `审查结果：PASS` 或 `审查结果：FAIL`。
"""

    client = get_ai_client(Config)
    task_manager.push_log(task_id, f"审查模型：{client.label()}", progress=35)
    task_manager.push_log(task_id, f"写作规范：{writer_source}")
    task_manager.push_log(task_id, f"审查规范：{auditor_source}")
    audit_report = client.generate_text(prompt).text.strip()

    for line in audit_report[:600].split("\n"):
        if line.strip():
            task_manager.push_log(task_id, f"[审查] {line.strip()[:120]}")

    task_manager.push_log(task_id, "", progress=55)
    _assert_audit_passed(audit_report)
    task_manager.push_log(task_id, "审查通过", progress=60)


def _assert_audit_passed(audit_report: str):
    upper = (audit_report or "").upper()
    has_fail = bool(re.search(r"\bFAIL\b", upper))
    has_pass = bool(re.search(r"\bPASS\b", upper))

    if has_fail and not has_pass:
        issues_match = re.search(
            r"必须修改的问题[^\n]*\n(.*?)(?:\n#{1,3}\s|\Z)",
            audit_report,
            re.DOTALL,
        )
        issues_text = issues_match.group(1).strip()[:500] if issues_match else audit_report[-400:].strip()
        raise RuntimeError(f"审查未通过，请修改后重新发布。\n\n{issues_text}")

    if not has_pass and not has_fail:
        fail_count = audit_report.count("❌")
        pass_count = audit_report.count("✅")
        if fail_count > pass_count:
            raise RuntimeError(f"审查未通过（{fail_count} 项失败），请修改后重新发布。\n\n{audit_report[:400]}")
        raise RuntimeError(f"审查模型未输出明确 PASS/FAIL，请调整模型或提示词。\n\n{audit_report[:400]}")


def _run_wenyan_publish(task_id: str, file_path: str, Config) -> str | None:
    task_manager.push_log(task_id, "步骤3：用 orangeheart 主题发布到微信草稿箱...", progress=65)

    script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "publish_wenyan.mjs")
    if not os.path.exists(script_path):
        raise RuntimeError(f"发布脚本不存在：{script_path}")

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    if Config.WECHAT_APP_ID:
        env["WECHAT_APP_ID"] = Config.WECHAT_APP_ID
    if Config.WECHAT_APP_SECRET:
        env["WECHAT_APP_SECRET"] = Config.WECHAT_APP_SECRET

    try:
        proc = subprocess.run(
            ["node", script_path, file_path, "orangeheart"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            env=env,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("发布超时（120s），请检查微信 API 连通性。")

    stderr = proc.stderr.strip()
    if stderr:
        task_manager.push_log(task_id, f"[node stderr] {stderr[:200]}")

    if proc.returncode != 0:
        raise RuntimeError(f"发布脚本退出码 {proc.returncode}: {proc.stdout[:300]} {stderr[:300]}")

    stdout = proc.stdout.strip()
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"发布脚本输出非 JSON：{stdout[:300]}") from exc

    if not result.get("success"):
        raise RuntimeError(f"发布失败：{result.get('error', '未知错误')}")

    media_id = result.get("media_id")
    task_manager.push_log(task_id, f"发布成功，media_id: {media_id}", progress=85)
    return media_id


def _run_git_commit(task_id: str, file_path: str, media_id: str | None, Config):
    task_manager.push_log(task_id, "步骤4：Git 归档...", progress=90)

    rel_path = os.path.relpath(file_path, Config.GZHPUBLISHER_ROOT).replace("\\", "/")
    commit_msg = f"feat(articles): {os.path.splitext(os.path.basename(file_path))[0]}"
    if media_id:
        commit_msg += f" [media_id: {media_id[:20]}...]"

    try:
        subprocess.run(["git", "add", rel_path], cwd=Config.GZHPUBLISHER_ROOT, capture_output=True, timeout=15)
        proc = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=Config.GZHPUBLISHER_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        if proc.returncode == 0:
            task_manager.push_log(task_id, f"[git] {proc.stdout.strip()[:100]}", progress=95)
        else:
            task_manager.push_log(task_id, f"[git] {(proc.stdout + proc.stderr).strip()[:100]}")
    except Exception as exc:
        task_manager.push_log(task_id, f"Git 归档失败，不影响发布：{exc}")


def _persist_publish_result(file_path: str, media_id: str):
    from database import SessionLocal
    from models import Article

    db = SessionLocal()
    try:
        article = db.query(Article).filter(Article.file_path == file_path).first()
        if article:
            article.media_id = media_id
            article.status = "published"
            article.publish_timestamp = datetime.now(timezone.utc)
            db.commit()
    except Exception as exc:
        db.rollback()
        import logging
        logging.getLogger(__name__).error("写回发布结果到数据库失败: %s", exc)
    finally:
        db.close()


def _dedup_frontmatter(task_id: str, file_path: str):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.split("\n")
    all_fms = []
    i = 0
    while i < len(lines):
        while i < len(lines) and lines[i].strip() == "":
            i += 1
        if i < len(lines) and lines[i].strip() == "---":
            start = i
            i += 1
            while i < len(lines) and lines[i].strip() != "---":
                i += 1
            end = i
            all_fms.append((start, end, "\n".join(lines[start:end + 1])))
            i += 1
        else:
            break

    if len(all_fms) <= 1:
        return

    best_fm = all_fms[0][2]
    for _, _, fm in all_fms:
        if "cover:" in fm:
            best_fm = fm
            break

    last_end = all_fms[-1][1]
    body_lines = lines[last_end + 1:]
    while body_lines and body_lines[0].strip() == "":
        body_lines.pop(0)

    fixed = best_fm + "\n\n" + "\n".join(body_lines)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(fixed)

    task_manager.push_log(task_id, f"[清理] 移除了 {len(all_fms) - 1} 个重复 frontmatter 块")


def _find_claude_bin():
    from config import Config

    return find_claude_bin(Config)
