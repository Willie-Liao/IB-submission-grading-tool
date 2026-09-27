#!/usr/bin/env python3
"""
List student submission file formats and paths into JSON.

No LLM/API calls are made.
"""

import argparse
import json
from pathlib import Path

SUPPORTED_EXT = (".docx", ".pdf", ".png", ".jpg", ".jpeg", ".webp")
NON_STUDENT_DIRS = {"student_calibration_notes"}


def build_report(target_dir: Path) -> dict:
    if not target_dir.exists() or not target_dir.is_dir():
        raise FileNotFoundError(f"Directory not found: {target_dir}")

    students = sorted(
        d for d in target_dir.iterdir() if d.is_dir() and d.name not in NON_STUDENT_DIRS
    )

    report_students = []
    for student_dir in students:
        files = sorted(
            f
            for f in student_dir.iterdir()
            if f.is_file()
            and f.suffix.lower() in SUPPORTED_EXT
            and not f.name.startswith("~$")
        )

        file_entries = [
            {
                "file_name": f.name,
                "format": f.suffix.lower().lstrip("."),
                "path": str(f),
            }
            for f in files
        ]

        report_students.append(
            {
                "student_folder": student_dir.name,
                "file_count": len(file_entries),
                "files": file_entries,
            }
        )

    return {
        "target_directory": str(target_dir),
        "supported_formats": [ext.lstrip(".") for ext in SUPPORTED_EXT],
        "student_count": len(report_students),
        "students": report_students,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export student submission formats and paths to JSON."
    )
    parser.add_argument(
        "--dir",
        default="grade_9_A",
        help="Student directory to scan (default: grade_9_A)",
    )
    parser.add_argument(
        "--out",
        default="grade_9_A/submission_file_report.json",
        help="Output JSON file path (default: grade_9_A/submission_file_report.json)",
    )
    args = parser.parse_args()

    target_dir = Path(args.dir)
    output_path = Path(args.out)

    report = build_report(target_dir)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"✓ Saved report: {output_path}")
    print(f"  Students scanned: {report['student_count']}")


if __name__ == "__main__":
    main()
