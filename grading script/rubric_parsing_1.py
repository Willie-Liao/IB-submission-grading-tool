#!/usr/bin/env python3
"""Step 1: parse a rubric into JSON, then build a blank task schema.

A template produces template=true. Without a template, the first five student
folders produce template=false. The comment skeleton is empty until step 3.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from documents import RUBRIC_PICTURE_PAGE_CAP, load_rubric_or_template, submission_files
from documents import extract_student_files
from models import (
    RubricSchema,
    TaskSchemaDraft,
    dump_model,
    finalize_task_schema,
    schema_json,
)
from pipeline import (
    MINIMAX_MODEL,
    call_minimax,
    complete_model,
    fill_prompt,
    list_student_dirs,
    load_prompt,
    user_with_blocks,
)
from token_usage import TokenLedger

SAMPLE_LIMIT = 5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse a rubric and build a task schema.")
    parser.add_argument("--rubric", required=True, help="Rubric .docx or .pdf")
    parser.add_argument("--out", required=True, help="Directory for rubric_schema.json and task_schema.json")
    parser.add_argument("--criterion", required=True, help="Criterion letter, such as A, B, C, or D")
    parser.add_argument("--year", required=True, help="MYP year, such as 1, 3, or 5")
    parser.add_argument("--template", help="Worksheet .docx or .pdf. Wins over --students.")
    parser.add_argument("--students", help="Folder of student submissions, used when there is no template")
    parser.add_argument("--force", action="store_true", help="Replace an existing task_schema.json")
    return parser.parse_args()


def document_user_text(label: str, text: str, images: list[dict]) -> str:
    if images:
        return f"{label}\nThe document is attached as page images in order."
    if not text.strip():
        raise ValueError(f"{label} has no extractable text.")
    return text


def parse_rubric(path: Path, criterion: str, year: str) -> tuple[RubricSchema, dict]:
    text, images = load_rubric_or_template(path)
    system = fill_prompt(
        load_prompt("step1_rubric_system.md"),
        {"RUBRIC_JSON_SCHEMA": schema_json(RubricSchema)},
    )
    document = document_user_text("RUBRIC:", text, images)
    user = fill_prompt(
        load_prompt("step1_rubric_user.md"),
        {"CRITERION": criterion, "YEAR": year, "DOCUMENT": document},
    )
    user_content = user_with_blocks(user, images, RUBRIC_PICTURE_PAGE_CAP)
    rubric, usage = complete_model(system, user_content, RubricSchema, call_minimax)
    rubric.assignment_overview.criterion = criterion
    rubric.assignment_overview.grade_or_year = year
    return rubric, usage


def parse_template(path: Path, rubric: RubricSchema) -> tuple[TaskSchemaDraft, dict]:
    text, images = load_rubric_or_template(path)
    system = fill_prompt(
        load_prompt("step1_template_system.md"),
        {"TASK_JSON_SCHEMA": schema_json(TaskSchemaDraft)},
    )
    document = document_user_text("TEMPLATE:", text, images)
    user = fill_prompt(
        load_prompt("step1_template_user.md"),
        {"RUBRIC_SCHEMA": dump_model(rubric), "DOCUMENT": document},
    )
    user_content = user_with_blocks(user, images, RUBRIC_PICTURE_PAGE_CAP)
    return complete_model(system, user_content, TaskSchemaDraft, call_minimax)


def induce_from_students(students_dir: Path, rubric: RubricSchema) -> tuple[TaskSchemaDraft, dict]:
    students = list_student_dirs(students_dir)
    if not students:
        raise ValueError(f"No student submissions found in {students_dir}.")
    if len(students) < SAMPLE_LIMIT:
        print(f"Warning: found {len(students)} submissions; using all of them.")
    sample = students[:SAMPLE_LIMIT]
    blocks: list[dict] = []
    for folder in sample:
        blocks.append({"type": "text", "text": f"[Student folder: {folder.name}]"})
        blocks.extend(extract_student_files(submission_files(folder)))
    system = fill_prompt(
        load_prompt("step1_induce_system.md"),
        {"TASK_JSON_SCHEMA": schema_json(TaskSchemaDraft)},
    )
    user = fill_prompt(
        load_prompt("step1_induce_user.md"),
        {
            "RUBRIC_SCHEMA": dump_model(rubric),
            "SUBMISSIONS": "The submissions follow this message.",
        },
    )
    user_content = user_with_blocks(user, blocks, RUBRIC_PICTURE_PAGE_CAP)
    return complete_model(system, user_content, TaskSchemaDraft, call_minimax)


def main() -> None:
    args = parse_args()
    if not args.template and not args.students:
        raise SystemExit("Pass --template or --students.")
    out_dir = Path(args.out)
    task_path = out_dir / "task_schema.json"
    rubric_path = out_dir / "rubric_schema.json"
    if task_path.exists() and not args.force:
        raise SystemExit(f"{task_path} already exists. Pass --force to replace it.")

    ledger = TokenLedger(out_dir, MINIMAX_MODEL)
    print(f"Reading rubric {args.rubric}...")
    rubric, rubric_usage = parse_rubric(Path(args.rubric), args.criterion, args.year)
    ledger.record("step1", rubric_usage)
    if args.template:
        print(f"Reading template {args.template}...")
        draft, task_usage = parse_template(Path(args.template), rubric)
        template = True
    else:
        print(f"Inducing a task schema from up to {SAMPLE_LIMIT} submissions...")
        draft, task_usage = induce_from_students(Path(args.students), rubric)
        template = False
    ledger.record("step1", task_usage)
    task = finalize_task_schema(draft, rubric, template=template)

    out_dir.mkdir(parents=True, exist_ok=True)
    rubric_path.write_text(dump_model(rubric), encoding="utf-8")
    task_path.write_text(dump_model(task), encoding="utf-8")
    print(f"Wrote {rubric_path}")
    print(f"Wrote {task_path}")
    print(
        "Set grading_sample_reference or run learn_calibration.py, then edit "
        "calibration_notes and comment headings "
        "in task_schema.json before running step 2."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise
