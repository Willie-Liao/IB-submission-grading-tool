"""Shared prompt loading, student folders, and validated LLM calls."""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI, RateLimitError
from pydantic import BaseModel, ValidationError

from models import extract_json_object

SCRIPT_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = SCRIPT_DIR / "prompts" / "pipeline"
PROJECT_ROOT = SCRIPT_DIR.parent

load_dotenv()
load_dotenv(PROJECT_ROOT / ".env")

MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY")
MINIMAX_BASE_URL = os.getenv("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1")
MINIMAX_MODEL = os.getenv("MINIMAX_MODEL", "MiniMax-M3")

SKIP_DIRS = {
    "__pycache__",
    "grading_checkpoints",
    "step2_fill_checkpoints",
    "step3_grade_checkpoints",
    ".git",
    ".cursor",
    ".venv",
    "venv",
    "env",
    ".env",
    "prompts",
    "tests",
    "skill",
}

PLACEHOLDER_RE = re.compile(r"\{\{[A-Z0-9_]+\}\}")


def load_prompt(filename: str) -> str:
    path = PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    content = path.read_text(encoding="utf-8")
    if not content.strip():
        raise ValueError(f"Prompt file is empty: {path}")
    return content


def fill_prompt(template: str, values: dict[str, str]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    leftover = PLACEHOLDER_RE.findall(rendered)
    if leftover:
        raise ValueError(f"Unfilled prompt placeholders: {', '.join(leftover)}")
    return rendered


def parse_student_name(folder_name: str) -> str:
    parts = folder_name.replace("-", "_").split("_")
    return parts[-1].capitalize() if len(parts) > 1 else parts[0].capitalize()


def list_student_dirs(base_dir: str | Path) -> list[Path]:
    from documents import submission_files

    base = Path(base_dir)
    if not base.is_dir():
        raise FileNotFoundError(base)
    students: list[Path] = []
    for item in sorted(base.iterdir(), key=lambda path: path.name):
        if not item.is_dir():
            continue
        if item.name.startswith(".") or item.name.startswith("_"):
            continue
        if item.name in SKIP_DIRS:
            continue
        if submission_files(item):
            students.append(item)
    return students


def strip_think_blocks(content: str) -> str:
    return re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()


def call_minimax(messages: list[dict]) -> str:
    if not MINIMAX_API_KEY:
        raise RuntimeError("MINIMAX_API_KEY is missing. Set it in .env.")
    client = OpenAI(api_key=MINIMAX_API_KEY, base_url=MINIMAX_BASE_URL)
    delay = 10
    for attempt in range(6):
        try:
            response = client.chat.completions.create(
                model=MINIMAX_MODEL,
                messages=messages,
                temperature=1,
                extra_body={"thinking": {"type": "disabled"}},
            )
            return strip_think_blocks(response.choices[0].message.content or "")
        except RateLimitError:
            if attempt == 5:
                raise
            print(f"Rate limited. Retrying in {delay}s... ({attempt + 1}/6)")
            time.sleep(delay)
            delay *= 2
    return ""


def complete_model(system: str, user_content, model_cls: type[BaseModel], call) -> BaseModel:
    """Validate one model response. On failure, repair once without changing the system prompt."""
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]
    raw = call(messages)
    try:
        return model_cls.model_validate(extract_json_object(raw))
    except (ValidationError, ValueError, TypeError) as exc:
        repair = (
            "The previous JSON failed validation:\n"
            f"{exc}\n"
            "Return only the corrected JSON object."
        )
        repaired = call(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
                {"role": "assistant", "content": raw},
                {"role": "user", "content": repair},
            ]
        )
        return model_cls.model_validate(extract_json_object(repaired))


def checkpoint_path(checkpoint_dir: Path, student_name: str) -> Path:
    safe_name = re.sub(r"[^\w\-_.]", "_", student_name)
    return checkpoint_dir / f"{safe_name}_checkpoint.json"


def save_checkpoint(
    checkpoint_dir: Path,
    student_name: str,
    status: str,
    file_paths: list[str],
    *,
    score: int | None = None,
    error: str | None = None,
    provider: str,
    model: str,
) -> None:
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "student_name": student_name,
        "file_paths": file_paths,
        "status": status,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "score": score,
        "error": error,
        "provider": provider,
        "model": model,
        "thread_id": threading.current_thread().name,
    }
    checkpoint_path(checkpoint_dir, student_name).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def user_with_blocks(text: str, blocks: list[dict], max_images: int) -> str | list[dict]:
    from documents import blocks_to_llm_content

    if not blocks:
        return text
    content: list[dict] = [{"type": "text", "text": text}]
    content.extend(blocks_to_llm_content(blocks, max_images=max_images))
    return content
