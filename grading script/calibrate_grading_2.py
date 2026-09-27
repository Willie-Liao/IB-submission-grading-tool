#!/usr/bin/env python3
"""Step 2: merge every file in a student folder into content.json.

This step fills student_answer only. It does not read teacher comments and
it does not grade.
"""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

from documents import STUDENT_IMAGE_CAP, extract_student_files, submission_files
from models import AnswerFill, StudentContent, TaskSchema, dump_model, merge_student_answers, render_comparison
from pipeline import (
    MINIMAX_MODEL,
    call_minimax,
    complete_model,
    fill_prompt,
    list_student_dirs,
    load_prompt,
    parse_student_name,
    save_checkpoint,
    user_with_blocks,
)

print_lock = Lock()
CONTENT_FILE = "content.json"


def print_safe(message: str) -> None:
    with print_lock:
        print(message)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fill the task schema from student files.")
    parser.add_argument("--students", required=True, help="Folder whose subfolders are students")
    parser.add_argument("--task-schema", required=True, help="Blank task_schema.json from step 1")
    return parser.parse_args()


def build_system_prompt(task: TaskSchema) -> str:
    return fill_prompt(
        load_prompt("step2_system.md"),
        {"TASK_SCHEMA": dump_model(task)},
    )


def fill_one(
    folder: Path,
    blank: TaskSchema,
    system_prompt: str,
    checkpoint_dir: Path,
) -> str:
    student_name = parse_student_name(folder.name)
    content_path = folder / CONTENT_FILE
    files = submission_files(folder)
    file_paths = [str(path) for path in files]
    if content_path.exists():
        save_checkpoint(
            checkpoint_dir,
            folder.name,
            "completed",
            file_paths,
            provider="minimax",
            model=MINIMAX_MODEL,
        )
        print_safe(f"Skip {folder.name}: {CONTENT_FILE} already exists")
        return "skipped"

    save_checkpoint(
        checkpoint_dir,
        folder.name,
        "in_progress",
        file_paths,
        provider="minimax",
        model=MINIMAX_MODEL,
    )
    try:
        user_text = fill_prompt(
            load_prompt("step2_user.md"),
            {"STUDENT_NAME": student_name},
        )
        blocks = extract_student_files(files)
        user_content = user_with_blocks(user_text, blocks, STUDENT_IMAGE_CAP)
        filled = complete_model(system_prompt, user_content, AnswerFill, call_minimax)
        task = merge_student_answers(blank, filled)
        content = StudentContent(task=task, comparison=render_comparison(task))
        content_path.write_text(dump_model(content), encoding="utf-8")
        save_checkpoint(
            checkpoint_dir,
            folder.name,
            "completed",
            file_paths,
            provider="minimax",
            model=MINIMAX_MODEL,
        )
        print_safe(f"Filled {folder.name}")
        return "filled"
    except Exception as exc:
        save_checkpoint(
            checkpoint_dir,
            folder.name,
            "failed",
            file_paths,
            error=str(exc),
            provider="minimax",
            model=MINIMAX_MODEL,
        )
        print_safe(f"Failed {folder.name}: {exc}")
        return "failed"


def main() -> None:
    args = parse_args()
    blank = TaskSchema.model_validate_json(Path(args.task_schema).read_text(encoding="utf-8"))
    students = list_student_dirs(args.students)
    if not students:
        raise SystemExit(f"No student submissions found in {args.students}.")
    checkpoint_dir = Path(args.students) / "step2_fill_checkpoints"
    system_prompt = build_system_prompt(blank)
    pending = [folder for folder in students if not (folder / CONTENT_FILE).exists()]
    if not pending:
        print("Every student already has content.json.")
        return

    warmup_user = load_prompt("cache_warmup_user.md")
    print("Warming the prompt cache...")
    call_minimax(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": warmup_user},
        ]
    )

    workers = len(pending)
    results = {"filled": 0, "skipped": 0, "failed": 0}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(fill_one, folder, blank, system_prompt, checkpoint_dir)
            for folder in pending
        ]
        for future in as_completed(futures):
            results[future.result()] += 1
    print(
        f"Done. Filled {results['filled']}, skipped {results['skipped']}, failed {results['failed']}."
    )
    if results["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise
