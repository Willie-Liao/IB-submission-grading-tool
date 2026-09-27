#!/usr/bin/env python3
"""
Check student submissions for Criterion B.
Checks for submissions inside each student's 'Grade_6_Yoga_B' subfolder.
Reports on correct submissions, misplaced files, and missing work.
"""

import os
from pathlib import Path
from collections import Counter


def get_file_extension_info(file_path: Path) -> dict:
    """Get file extension and format category."""
    ext = file_path.suffix.lower()

    format_categories = {
        ".docx": "Word Document",
        ".doc": "Word Document",
        ".pdf": "PDF",
        ".png": "Image",
        ".jpg": "Image",
        ".jpeg": "Image",
        ".webp": "Image",
        ".gif": "Image",
        ".txt": "Text",
        ".md": "Markdown",
    }

    return {
        "extension": ext,
        "format": format_categories.get(ext, "Other"),
        "name": file_path.name,
    }


def scan_submissions(base_dir: Path) -> dict:
    """Scan for student submissions in the directory.
    
    Looks for submissions inside each student's 'Grade_6_Yoga_B' subfolder.
    Also reports files found directly in student folder (misplaced).
    """
    submissions = []
    misplaced_files = []  # Files directly in student folder (not in Grade_6_Yoga_B)
    missing_subfolder = []  # Students without Grade_6_Yoga_B folder
    no_submissions = []  # Students with empty Grade_6_Yoga_B folder

    # Folders to exclude (reference documents, not student submissions)
    EXCLUDED_FOLDERS = {"rubric_task_clarification", "sample_submissions", "student_calibration_notes"}
    
    # The subfolder name where submissions should be stored
    SUBMISSION_FOLDER = "Grade_6_Yoga_B"

    if not base_dir.exists():
        return {"error": f"Directory not found: {base_dir}"}

    # Look for student folders
    for item in sorted(base_dir.iterdir()):
        if item.is_dir() and not item.name.startswith(".") and item.name not in EXCLUDED_FOLDERS:
            student_name = item.name
            
            # Look for the submission subfolder inside the student folder
            submission_dir = item / SUBMISSION_FOLDER
            
            # Check for files directly in student folder (misplaced)
            files_in_root = [f for f in item.iterdir() if f.is_file() and not f.name.startswith(".")]
            if files_in_root:
                for f in files_in_root:
                    file_info = get_file_extension_info(f)
                    misplaced_files.append({
                        "student": student_name,
                        "file": file_info["name"],
                        "extension": file_info["extension"],
                        "format": file_info["format"],
                    })
            
            if not submission_dir.exists():
                # Student has no Grade_6_Yoga_B folder
                missing_subfolder.append(student_name)
                continue
                
            # Check for submission files in the Grade_6_Yoga_B subfolder
            student_files = []
            for file_path in submission_dir.iterdir():
                if file_path.is_file() and not file_path.name.startswith("."):
                    file_info = get_file_extension_info(file_path)
                    student_files.append({
                        "student": student_name,
                        "file": file_info["name"],
                        "extension": file_info["extension"],
                        "format": file_info["format"],
                        "path": str(file_path.relative_to(base_dir)),
                    })

            if student_files:
                submissions.extend(student_files)
            else:
                # Folder exists but is empty
                no_submissions.append(student_name)

    return {
        "submissions": submissions,
        "misplaced_files": misplaced_files,
        "missing_subfolder": missing_subfolder,
        "no_submissions": no_submissions,
    }


def display_summary(result: dict):
    """Display a formatted summary of submissions."""
    submissions = result.get("submissions", [])
    misplaced = result.get("misplaced_files", [])
    missing_folder = result.get("missing_subfolder", [])
    empty_folder = result.get("no_submissions", [])

    print("\n" + "=" * 70)
    print("STUDENT SUBMISSIONS SUMMARY")
    print("=" * 70)

    # Summary stats
    total_students = len(set(
        [s["student"] for s in submissions] +
        [m["student"] for m in misplaced] +
        missing_folder + empty_folder
    ))

    print(f"\n📊 Overview:")
    print(f"   Total Students: {total_students}")
    print(f"   ✓ Correct submissions (in Grade_6_Yoga_B folder): {len(set(s['student'] for s in submissions))}")
    print(f"   ⚠ Misplaced files (in student root folder): {len(set(m['student'] for m in misplaced))}")
    print(f"   ✗ Missing Grade_6_Yoga_B folder: {len(missing_folder)}")
    print(f"   ∅ Empty Grade_6_Yoga_B folder: {len(empty_folder)}")

    # Section 1: Correct Submissions
    if submissions:
        print("\n" + "-" * 70)
        print("✓ CORRECT SUBMISSIONS (in Grade_6_Yoga_B folder)")
        print("-" * 70)

        # Count by format
        format_counts = Counter(s["format"] for s in submissions)
        ext_counts = Counter(s["extension"] for s in submissions)

        print(f"\n   Total Files: {len(submissions)}")
        print("\n   Format Breakdown:")
        for fmt, count in format_counts.most_common():
            print(f"      {fmt:20s}: {count:3d} file(s)")

        # Group by student
        students = {}
        for sub in submissions:
            if sub["student"] not in students:
                students[sub["student"]] = []
            students[sub["student"]].append(sub)

        print("\n   By Student:")
        for i, (student, files) in enumerate(sorted(students.items()), 1):
            print(f"\n   {i}. {student}")
            for f in files:
                print(f"      └─ {f['file']} ({f['format']})")

    # Section 2: Misplaced Files
    if misplaced:
        print("\n" + "-" * 70)
        print("⚠ MISPLACED FILES (should be in Grade_6_Yoga_B subfolder)")
        print("-" * 70)

        students_with_misplaced = {}
        for m in misplaced:
            if m["student"] not in students_with_misplaced:
                students_with_misplaced[m["student"]] = []
            students_with_misplaced[m["student"]].append(m)

        for i, (student, files) in enumerate(sorted(students_with_misplaced.items()), 1):
            print(f"\n   {i}. {student}")
            for f in files:
                print(f"      └─ {f['file']} ({f['format']})")

    # Section 3: Missing Subfolder
    if missing_folder:
        print("\n" + "-" * 70)
        print("✗ MISSING Grade_6_Yoga_B FOLDER")
        print("-" * 70)
        for i, student in enumerate(sorted(missing_folder), 1):
            print(f"   {i}. {student}")

    # Section 4: Empty Folder
    if empty_folder:
        print("\n" + "-" * 70)
        print("∅ EMPTY Grade_6_Yoga_B FOLDER (no files submitted)")
        print("-" * 70)
        for i, student in enumerate(sorted(empty_folder), 1):
            print(f"   {i}. {student}")

    # Nothing found at all
    if not submissions and not misplaced and not missing_folder and not empty_folder:
        print("\n   No student folders found.")

    print("\n" + "=" * 70)


def main():
    # Get the directory where this script is located
    script_dir = Path(__file__).parent

    print("=" * 70)
    print("Checking Student Submissions for Criterion B")
    print(f"Directory: {script_dir}")
    print("Looking for: Grade_6_Yoga_B subfolder in each student folder")
    print("=" * 70)

    result = scan_submissions(script_dir)

    if "error" in result:
        print(f"\nError: {result['error']}")
        return

    display_summary(result)


if __name__ == "__main__":
    main()
