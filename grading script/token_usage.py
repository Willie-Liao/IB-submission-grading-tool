"""Local token rollups in Langfuse usage shape. Tracing stays off; nothing is exported."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

os.environ.setdefault("LANGFUSE_TRACING_ENABLED", "false")

from langfuse import Langfuse  # noqa: E402

_LANGFUSE = Langfuse(
    public_key=os.getenv("LANGFUSE_PUBLIC_KEY", "local"),
    secret_key=os.getenv("LANGFUSE_SECRET_KEY", "local"),
    host=os.getenv("LANGFUSE_HOST", "http://127.0.0.1:0"),
    tracing_enabled=False,
)

TOKEN_USAGE_FILE = "token_usage.json"
STEP_KEYS = ("step1", "learn", "step2", "step3")


def empty_usage() -> dict[str, int]:
    return {"input": 0, "output": 0, "total": 0, "calls": 0}


def add_usage(base: dict[str, int], extra: dict[str, int]) -> dict[str, int]:
    return {
        "input": base["input"] + extra["input"],
        "output": base["output"] + extra["output"],
        "total": base["total"] + extra["total"],
        "calls": base["calls"] + extra["calls"],
    }


def usage_from_response(response: Any) -> dict[str, int]:
    """Read prompt/completion totals from an OpenAI-compatible completion response."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return empty_usage()
    prompt = getattr(usage, "prompt_tokens", None) or 0
    completion = getattr(usage, "completion_tokens", None) or 0
    total = getattr(usage, "total_tokens", None)
    if total is None:
        total = prompt + completion
    return {
        "input": int(prompt),
        "output": int(completion),
        "total": int(total),
        "calls": 1,
    }


def default_ledger(model: str) -> dict[str, Any]:
    steps = {step: empty_usage() for step in STEP_KEYS}
    return {
        "model": model,
        "steps": steps,
        "students": {},
        "total": empty_usage(),
    }


class TokenLedger:
    """Thread-safe token totals for one class folder."""

    def __init__(self, class_dir: Path, model: str) -> None:
        self.path = Path(class_dir) / TOKEN_USAGE_FILE
        self.lock = threading.Lock()
        self.model = model
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.data = default_ledger(model)

    def record(
        self,
        step: str,
        usage: dict[str, int],
        *,
        student_folder: str | None = None,
    ) -> None:
        if step not in STEP_KEYS:
            raise ValueError(f"Unknown step {step!r}. Expected one of {STEP_KEYS}.")
        if not usage["calls"]:
            return
        with self.lock:
            self.data["model"] = self.model
            self.data["steps"][step] = add_usage(self.data["steps"][step], usage)
            self.data["total"] = add_usage(self.data["total"], usage)
            if student_folder:
                students = self.data.setdefault("students", {})
                entry = students.setdefault(
                    student_folder,
                    {key: empty_usage() for key in ("step2", "step3")},
                )
                if step in entry:
                    entry[step] = add_usage(entry[step], usage)
            self._write()

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def langfuse_client() -> Langfuse:
    """Return the module Langfuse client (tracing disabled)."""
    return _LANGFUSE
