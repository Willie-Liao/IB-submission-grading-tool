#!/usr/bin/env python3
"""Step 3: grade filled content.json against the rubric and write comment.md.

This call is text only. It does not open the student's files again.
"""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

from models import (
    CommentFormat,
    RubricSchema,
    StudentContent,
    TaskSchema,
    assert_comment_matches,
    dump_model,
    render_comment_md,
    render_comparison,
    schema_json,
)
from pipeline import (
    MINIMAX_MODEL,
    call_minimax,
    complete_model,
    fill_prompt,
    list_student_dirs,
    load_prompt,
    parse_student_name,
    save_checkpoint,
)

print_lock = Lock()
CONTENT_FILE = "content.json"
COMMENT_FILE = "comment.md"


def print_safe(message: str) -> None:
    with print_lock:
        print(message)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Grade filled student schemas.")
    parser.add_argument("--students", required=True, help="Folder whose subfolders are students")
    parser.add_argument("--rubric-schema", required=True, help="rubric_schema.json from step 1")
    parser.add_argument("--task-schema", required=True, help="task_schema.json with the comment skeleton")
    return parser.parse_args()


def build_system_prompt(rubric: RubricSchema, task: TaskSchema) -> str:
    return fill_prompt(
        load_prompt("step3_system.md"),
        {
            "RUBRIC_SCHEMA": dump_model(rubric),
            "COMMENT_SKELETON": dump_model(task.comment),
            "COMMENT_JSON_SCHEMA": schema_json(CommentFormat),
            "VISUAL_RELATED": "true" if task.visual_related_submission else "false",
        },
    )


def grade_one(
    folder: Path,
    system_prompt: str,
    skeleton: CommentFormat,
    checkpoint_dir: Path,
) -> str:
    student_name = parse_student_name(folder.name)
    content_path = folder / CONTENT_FILE
    comment_path = folder / COMMENT_FILE
    if comment_path.exists():
        print_safe(f"Skip {folder.name}: {COMMENT_FILE} already exists")
        return "skipped"
    if not content_path.exists():
        save_checkpoint(
            checkpoint_dir,
            folder.name,
            "failed",
            [],
            error=f"Missing {CONTENT_FILE}",
            provider="minimax",
            model=MINIMAX_MODEL,
        )
        print_safe(f"Failed {folder.name}: missing {CONTENT_FILE}")
        return "failed"

    save_checkpoint(
        checkpoint_dir,
        folder.name,
        "in_progress",
        [str(content_path)],
        provider="minimax",
        model=MINIMAX_MODEL,
    )
    try:
        content = StudentContent.model_validate_json(content_path.read_text(encoding="utf-8"))
        comparison = render_comparison(content.task, include_grading_details=True)
        user_text = fill_prompt(
            load_prompt("step3_user.md"),
            {"STUDENT_NAME": student_name, "COMPARISON": comparison},
        )
        comment = complete_model(system_prompt, user_text, CommentFormat, call_minimax)
        assert_comment_matches(comment, skeleton)
        content.task.comment = comment
        content_path.write_text(dump_model(content), encoding="utf-8")
        comment_path.write_text(render_comment_md(student_name, comment), encoding="utf-8")
        save_checkpoint(
            checkpoint_dir,
            folder.name,
            "completed",
            [str(content_path)],
            score=comment.overall.score,
            provider="minimax",
            model=MINIMAX_MODEL,
        )
        print_safe(f"Graded {folder.name}: {comment.overall.score}/8")
        return "graded"
    except Exception as exc:
        save_checkpoint(
            checkpoint_dir,
            folder.name,
            "failed",
            [str(content_path)],
            error=str(exc),
            provider="minimax",
            model=MINIMAX_MODEL,
        )
        print_safe(f"Failed {folder.name}: {exc}")
        return "failed"


def main() -> None:
    args = parse_args()
    rubric = RubricSchema.model_validate_json(Path(args.rubric_schema).read_text(encoding="utf-8"))
    task = TaskSchema.model_validate_json(Path(args.task_schema).read_text(encoding="utf-8"))
    students = list_student_dirs(args.students)
    if not students:
        raise SystemExit(f"No student submissions found in {args.students}.")
    checkpoint_dir = Path(args.students) / "step3_grade_checkpoints"
    system_prompt = build_system_prompt(rubric, task)
    pending = [folder for folder in students if not (folder / COMMENT_FILE).exists()]
    if not pending:
        print("Every student already has comment.md.")
        return

    warmup_user = load_prompt("cache_warmup_user.md")
    print("Warming the prompt cache...")
    call_minimax(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": warmup_user},
        ]
    )

    results = {"graded": 0, "skipped": 0, "failed": 0}
    with ThreadPoolExecutor(max_workers=len(pending)) as executor:
        futures = [
            executor.submit(grade_one, folder, system_prompt, task.comment, checkpoint_dir)
            for folder in pending
        ]
        for future in as_completed(futures):
            results[future.result()] += 1
    print(
        f"Done. Graded {results['graded']}, skipped {results['skipped']}, failed {results['failed']}."
    )
    if results["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise
