import os
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROMPTS_DIR = BACKEND_DIR / "prompts"


def read_text_if_exists(path: str | os.PathLike) -> str | None:
    try:
        path = Path(path)
        if path.exists():
            return path.read_text(encoding="utf-8")
    except OSError:
        return None
    return None


def read_builtin_prompt(name: str) -> str:
    path = PROMPTS_DIR / name
    return path.read_text(encoding="utf-8")


def load_writer_spec(config) -> tuple[str, str]:
    external_path = Path(config.GZHPUBLISHER_ROOT) / "agents" / "kuanlun-geo-writer-enhanced.md"
    external = read_text_if_exists(external_path)
    if external:
        return external, str(external_path)
    return read_builtin_prompt("writer_default.md"), str(PROMPTS_DIR / "writer_default.md")


def load_auditor_spec(config) -> tuple[str, str]:
    external_path = Path(config.GZHPUBLISHER_ROOT) / "agents" / "kuanlun-article-auditor.md"
    external = read_text_if_exists(external_path)
    if external:
        return external, str(external_path)
    return read_builtin_prompt("auditor_default.md"), str(PROMPTS_DIR / "auditor_default.md")
