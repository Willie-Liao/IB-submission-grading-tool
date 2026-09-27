#!/usr/bin/env python3
"""Learn calibration notes from graded sample folders and patch the task schema."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from documents import STUDENT_IMAGE_CAP, extract_student_files, submission_files
from models import (
    CalibrationLearn,
    StudentContent,
    TaskSchema,
    dump_model,
    merge_learned_calibration,
    render_comparison,
    schema_json,
)
from pipeline import (
    MINIMAX_MODEL,
    call_minimax,
    complete_model,
    fill_prompt,
    load_prompt,
    user_with_blocks,
)
from token_usage import TokenLedger

COMMENT_FILE = "comment.md"
CONTENT_FILE = "content.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Learn calibration_notes from graded sample folders."
    )
    parser.add_argument("--task-schema", required=True, help="Shared task_schema.json from step 1")
    parser.add_argument(
        "--samples",
        help="Folder of sample subfolders, each with comment.md and work or content.json",
    )
    parser.add_argument(
        "--students",
        help="Class folder whose content.json files receive empty calibration slots",
    )
    return parser.parse_args()


def list_sample_dirs(samples_dir: Path) -> list[Path]:
    samples: list[Path] = []
    for item in sorted(samples_dir.iterdir(), key=lambda path: path.name):
        if not item.is_dir():
            continue
        if item.name.startswith(".") or item.name.startswith("_"):
            continue
        if (item / COMMENT_FILE).is_file():
            samples.append(item)
    return samples


def sample_text_and_blocks(sample_dir: Path) -> tuple[str, list[dict]]:
    comment = (sample_dir / COMMENT_FILE).read_text(encoding="utf-8")
    lines = [
        f"### Sample folder: {sample_dir.name}",
        "",
        "Teacher comment and scores:",
        comment.strip(),
        "",
    ]
    blocks: list[dict] = []
    content_path = sample_dir / CONTENT_FILE
    if content_path.is_file():
        content = StudentContent.model_validate_json(content_path.read_text(encoding="utf-8"))
        lines.extend(
            [
                "Student work (from content.json):",
                render_comparison(content.task),
                "",
            ]
        )
    else:
        files = submission_files(sample_dir)
        if not files:
            raise ValueError(f"{sample_dir} has {COMMENT_FILE} but no content.json or submission files.")
        lines.append("Student submission files follow as text or images in order.")
        lines.append("")
        blocks = extract_student_files(files)
    return "\n".join(lines), blocks


def build_user_content(samples_dir: Path) -> str | list[dict]:
    sample_dirs = list_sample_dirs(samples_dir)
    if not sample_dirs:
        raise SystemExit(f"No sample folders with {COMMENT_FILE} found in {samples_dir}.")
    text_parts: list[str] = []
    all_blocks: list[dict] = []
    for sample_dir in sample_dirs:
        text, blocks = sample_text_and_blocks(sample_dir)
        text_parts.append(text)
        all_blocks.extend(blocks)
    body = "\n".join(text_parts)
    user_text = fill_prompt(load_prompt("learn_user.md"), {"SAMPLES": body})
    return user_with_blocks(user_text, all_blocks, STUDENT_IMAGE_CAP)


def build_system_prompt(task: TaskSchema) -> str:
    return fill_prompt(
        load_prompt("learn_system.md"),
        {
            "TASK_SCHEMA": dump_model(task),
            "CALIBRATION_JSON_SCHEMA": schema_json(CalibrationLearn),
        },
    )


def patch_student_content(learned: CalibrationLearn, students_dir: Path) -> int:
    patched = 0
    for folder in students_dir.iterdir():
        if not folder.is_dir():
            continue
        content_path = folder / CONTENT_FILE
        if not content_path.is_file():
            continue
        content = StudentContent.model_validate_json(content_path.read_text(encoding="utf-8"))
        updated = merge_learned_calibration(content.task, learned)
        if updated:
            content.comparison = render_comparison(content.task)
            content_path.write_text(dump_model(content), encoding="utf-8")
            patched += 1
    return patched


def main() -> None:
    args = parse_args()
    task_path = Path(args.task_schema)
    task = TaskSchema.model_validate_json(task_path.read_text(encoding="utf-8"))

    if args.samples:
        task.grading_sample_reference = str(Path(args.samples).resolve())
    samples_path = task.grading_sample_reference.strip()
    if not samples_path:
        print("grading_sample_reference is empty. Pass --samples or set it in task_schema.json.")
        return

    samples_dir = Path(samples_path)
    if not samples_dir.is_dir():
        raise SystemExit(f"Sample folder not found: {samples_dir}")

    class_dir = Path(args.students) if args.students else task_path.parent
    ledger = TokenLedger(class_dir, MINIMAX_MODEL)
    system_prompt = build_system_prompt(task)
    user_content = build_user_content(samples_dir)
    learned, usage = complete_model(system_prompt, user_content, CalibrationLearn, call_minimax)
    ledger.record("learn", usage)

    updated = merge_learned_calibration(task, learned)
    task_path.write_text(dump_model(task), encoding="utf-8")
    print(f"Updated {updated} calibration field(s) on {task_path}")

    if args.students:
        patched = patch_student_content(learned, Path(args.students))
        print(f"Patched calibration on {patched} existing content.json file(s).")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise
