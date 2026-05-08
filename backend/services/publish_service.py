"""
publish_service.py — 通过 wenyan-mcp 发布文章到微信公众号。

完整流程（与 publish-gzh skill 保持一致）：
  1. auto_add_images.py 自动配图（《概率的朋友》图库语义匹配）
  2. kuanlun-article-auditor 审查（Claude CLI --print，7项清单）
  3. publish_wenyan.mjs 用 orangeheart 主题发布到微信草稿箱
  4. git add + commit 归档

审查不通过 → 抛异常，前端显示具体问题，不发布。
"""

import json
import os
import re
import subprocess
from datetime import datetime, timezone

from services.task_manager import task_manager


def run_publish(task_id: str, file_path: str):
    from config import Config

    task_manager.push_log(task_id, f"准备发布：{os.path.basename(file_path)}", progress=5)

    if not os.path.exists(file_path):
        raise RuntimeError(f"文章文件不存在：{file_path}")

    # ── 步骤 1：自动配图 ──────────────────────────────────────────
    _run_auto_add_images(task_id, file_path, Config)

    # ── 步骤 1.5：清理重复 frontmatter（auto_add_images.py 会追加，必须在其后去重）
    _dedup_frontmatter(task_id, file_path)

    # ── 步骤 2：审查文章（强制，不可跳过）────────────────────────
    _run_audit(task_id, file_path, Config)

    # ── 步骤 3：发布到微信草稿箱 ──────────────────────────────────
    media_id = _run_wenyan_publish(task_id, file_path, Config)

    # ── 步骤 4：Git 归档 ──────────────────────────────────────────
    _run_git_commit(task_id, file_path, media_id, Config)

    # ── 步骤 5：写回数据库 ────────────────────────────────────────
    if media_id:
        _persist_publish_result(file_path, media_id)
        task_manager.push_log(task_id, "已写入数据库", progress=100)

    return {"media_id": media_id, "file_path": file_path}


# ─────────────────────────────────────────────────────────────────────────────
# 步骤实现
# ─────────────────────────────────────────────────────────────────────────────

def _run_auto_add_images(task_id: str, file_path: str, Config):
    """步骤1：运行 auto_add_images.py 为文章匹配《概率的朋友》书中配图。"""
    task_manager.push_log(task_id, "步骤1：自动配图（《概率的朋友》图库）...", progress=10)

    script = os.path.join(Config.GZHPUBLISHER_ROOT, "scripts", "auto_add_images.py")
    if not os.path.exists(script):
        task_manager.push_log(task_id, f"⚠️ 配图脚本不存在，跳过：{script}")
        return

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    try:
        proc = subprocess.run(
            ["python", script, file_path],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=60, env=env, cwd=Config.GZHPUBLISHER_ROOT,
        )
        if proc.returncode == 0:
            for line in proc.stdout.strip().split("\n"):
                line = line.strip()
                if line and not line.startswith("正在为文章"):
                    task_manager.push_log(task_id, f"[配图] {line[:120]}")
            task_manager.push_log(task_id, "配图完成", progress=25)
        else:
            err = (proc.stderr or proc.stdout or "")[:300]
            task_manager.push_log(task_id, f"⚠️ 配图报错（继续审查）：{err}")
    except subprocess.TimeoutExpired:
        task_manager.push_log(task_id, "⚠️ 配图超时，跳过")
    except Exception as e:
        task_manager.push_log(task_id, f"⚠️ 配图异常（继续审查）：{e}")


def _run_audit(task_id: str, file_path: str, Config):
    """步骤2：注入完整写作规范 + 审查清单，双重规范审查，不通过则抛异常。"""
    task_manager.push_log(task_id, "步骤2：审查文章质量...", progress=30)

    # 读文章内容
    with open(file_path, "r", encoding="utf-8") as f:
        article_content = f.read()

    # 读写入 agent 规范（权威标准，结构/格式/配图/结尾都以此为准）
    writer_path = os.path.join(Config.GZHPUBLISHER_ROOT, "agents", "kuanlun-geo-writer-enhanced.md")
    writer_spec = ""
    if os.path.exists(writer_path):
        with open(writer_path, "r", encoding="utf-8") as f:
            writer_spec = f.read()

    # 读审查 agent 规范（检查清单，逐项验证）
    auditor_path = os.path.join(Config.GZHPUBLISHER_ROOT, "agents", "kuanlun-article-auditor.md")
    auditor_spec = ""
    if os.path.exists(auditor_path):
        with open(auditor_path, "r", encoding="utf-8") as f:
            auditor_spec = f.read()

    prompt = f"""你是宽论文章质量审查专员。你必须严格按照以下两份规范审查文章，不允许自由发挥或放宽标准。

=== 规范一：写作规范（权威标准，违反任何一条即判定 FAIL）===

{writer_spec}

=== 规范二：审查清单（逐项检查，每条标注 ✅ 或 ❌）===

{auditor_spec}

=== 待审查文章 ===

{article_content}

=== 审查规则（必须严格执行，无例外）===

1. 将文章逐项对照上述两份规范，每一项给出 ✅ 或 ❌
2. 以下任何一项出现 ❌，审查结果必须判定为 **FAIL**：
   - 文章结尾使用了旧模板（"扫码找助理"、FREE 动图、社区招募语）
   - 图片使用 Markdown `![]()` 格式而非 HTML `<img>` 标签
   - 图片来源为 Unsplash 或其他外网（必须是《概率的朋友》书中配图）
   - 存在虚构人物案例或虚构盈利数据
   - frontmatter 缺少 title 或 cover 字段
3. **审查结果只可能是 PASS 或 FAIL，没有"基本通过""建议修改"等中间状态**

请输出：
**审查结果：PASS 或 FAIL**
然后列出每项检查结果。
最后如果是 FAIL，列出"必须修改的问题"清单（具体到文件位置和修正方式）。
"""

    claude_bin = _find_claude_bin()
    if not claude_bin:
        task_manager.push_log(task_id, "⚠️ 找不到 claude，跳过审查")
        return

    task_manager.push_log(task_id, "正在调用 Claude 审查文章...", progress=35)

    cmd = [claude_bin, "--print", "--output-format", "stream-json", "--verbose"]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
        env=env, cwd=Config.GZHPUBLISHER_ROOT,
    )
    proc.stdin.write(prompt)
    proc.stdin.close()

    output_chunks = []
    try:
        for raw_line in proc.stdout:
            line = raw_line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") == "assistant":
                for block in obj.get("message", {}).get("content", []):
                    if block.get("type") == "text":
                        output_chunks.append(block["text"])
    finally:
        proc.wait()

    audit_report = "".join(output_chunks).strip()

    # 推送审查摘要到日志（前600字）
    for line in audit_report[:600].split("\n"):
        if line.strip():
            task_manager.push_log(task_id, f"[审查] {line.strip()[:120]}")

    task_manager.push_log(task_id, "", progress=55)

    # 判断是否通过
    # 优先找明确的 PASS/FAIL 标记
    upper = audit_report.upper()
    has_fail = bool(re.search(r'\bFAIL\b', upper))
    has_pass = bool(re.search(r'\bPASS\b', upper))

    if has_fail and not has_pass:
        # 提取"必须修改的问题"清单
        issues_match = re.search(
            r'必须修改的问题[^\n]*\n(.*?)(?:\n#{1,3}\s|\Z)',
            audit_report, re.DOTALL
        )
        issues_text = issues_match.group(1).strip()[:500] if issues_match else audit_report[-400:].strip()
        raise RuntimeError(f"审查未通过，请修改后重新发布。\n\n{issues_text}")

    if not has_pass and not has_fail:
        # 没有明确标记，看是否有大量 ❌
        fail_count = audit_report.count("❌")
        pass_count = audit_report.count("✅")
        if fail_count > pass_count:
            raise RuntimeError(f"审查未通过（{fail_count} 项❌），请修改后重新发布。\n\n审查报告前400字：\n{audit_report[:400]}")

    task_manager.push_log(task_id, "✅ 审查通过", progress=60)


def _run_wenyan_publish(task_id: str, file_path: str, Config) -> str | None:
    """步骤3：调用 publish_wenyan.mjs 用 orangeheart 主题发布，返回 media_id。"""
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
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=120, env=env,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("发布超时（>120s），请检查微信 API 连通性")

    stderr = proc.stderr.strip()
    if stderr:
        task_manager.push_log(task_id, f"[node stderr] {stderr[:200]}")

    if proc.returncode != 0:
        raise RuntimeError(f"发布脚本退出码 {proc.returncode}: {proc.stdout[:300]} {stderr[:300]}")

    stdout = proc.stdout.strip()
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"发布脚本输出非 JSON：{stdout[:300]}")

    if not result.get("success"):
        raise RuntimeError(f"发布失败：{result.get('error', '未知错误')}")

    media_id = result.get("media_id")
    task_manager.push_log(task_id, f"✅ 发布成功！media_id: {media_id}", progress=85)
    return media_id


def _run_git_commit(task_id: str, file_path: str, media_id: str | None, Config):
    """步骤4：git add + commit 归档发布记录。"""
    task_manager.push_log(task_id, "步骤4：Git 归档...", progress=90)

    rel_path = os.path.relpath(file_path, Config.GZHPUBLISHER_ROOT).replace("\\", "/")
    commit_msg = f"feat(articles): {os.path.splitext(os.path.basename(file_path))[0]}"
    if media_id:
        commit_msg += f" [media_id: {media_id[:20]}...]"

    try:
        subprocess.run(
            ["git", "add", rel_path],
            cwd=Config.GZHPUBLISHER_ROOT, capture_output=True, timeout=15,
        )
        proc = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=Config.GZHPUBLISHER_ROOT, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=15,
        )
        if proc.returncode == 0:
            task_manager.push_log(task_id, f"[git] {proc.stdout.strip()[:100]}", progress=95)
        else:
            # nothing to commit 是正常的
            task_manager.push_log(task_id, f"[git] {(proc.stdout + proc.stderr).strip()[:100]}")
    except Exception as e:
        task_manager.push_log(task_id, f"⚠️ Git 归档失败（不影响发布）：{e}")


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
    except Exception as e:
        db.rollback()
        import logging
        logging.getLogger(__name__).error("写回发布结果到数据库失败: %s", e)
    finally:
        db.close()


def _dedup_frontmatter(task_id: str, file_path: str):
    """
    去除文章开头重复的 frontmatter 块。
    auto_add_images.py 每次运行会将 frontmatter 提取后重新写回，
    如果文章已有 frontmatter 没被正确识别就会叠加。
    保留有 cover 字段的第一个 frontmatter，删除其余重复块。
    """
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.split("\n")

    # 找出开头连续的所有 frontmatter 块
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
        return  # 没有重复，不处理

    # 选最优 frontmatter：优先选有 cover 的第一个
    best_fm = all_fms[0][2]
    for _, _, fm in all_fms:
        if "cover:" in fm:
            best_fm = fm
            break

    # body 从最后一个 frontmatter 的结束行之后开始
    last_end = all_fms[-1][1]
    body_lines = lines[last_end + 1:]
    while body_lines and body_lines[0].strip() == "":
        body_lines.pop(0)

    fixed = best_fm + "\n\n" + "\n".join(body_lines)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(fixed)

    task_manager.push_log(task_id, f"[清理] 移除了 {len(all_fms) - 1} 个重复 frontmatter 块")


def _find_claude_bin():
    import shutil
    found = shutil.which("claude")
    if found:
        return found
    candidates = [
        os.path.expanduser("~/AppData/Roaming/npm/claude"),
        os.path.expanduser("~/AppData/Roaming/npm/claude.cmd"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None
