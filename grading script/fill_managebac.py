#!/usr/bin/env python3
"""Fill ManageBac task grades from the Fall namelist workbook (sheet E9 only).

Column A: student name
Column B: 0–8 points-bar selection (click)
Column C: paper score (type into Score or N/A)

Requires cli-anything-browser + DOMShell (logged-in Chrome on the task form).

One-student check before a full run:

  python fill_managebac.py --task-url "<managebac edit task URL>"
  python fill_managebac.py --task-url "<url>" --apply --limit 1

Confirm the points-bar value and paper score on screen, then drop --limit.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

DEFAULT_WORKBOOK = Path(
    "/Users/willieliao/工作/JCID/Grading/Namelist 2026-2027 Fall.xlsx"
)
SHEET_NAME = "E9"
BROWSER_CMD = "cli-anything-browser"
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = {"r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}


@dataclass(frozen=True)
class GradeRow:
    name: str
    points_bar: int
    paper_score: str


class BrowserError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fill ManageBac from namelist E9 (points bar + paper score)."
    )
    parser.add_argument(
        "--workbook",
        type=Path,
        default=DEFAULT_WORKBOOK,
        help=f"Path to namelist xlsx (reads sheet {SHEET_NAME} only)",
    )
    parser.add_argument(
        "--task-url",
        default="",
        help="ManageBac task edit URL (required with --apply)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Perform clicks and typing (default is dry-run only)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Process at most N students (0 = all)",
    )
    return parser.parse_args()


def _col_row(ref: str) -> tuple[str, int]:
    match = re.fullmatch(r"([A-Z]+)(\d+)", ref)
    if not match:
        raise ValueError(f"Bad cell ref: {ref}")
    return match.group(1), int(match.group(2))


def _load_shared_strings(z: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    strings: list[str] = []
    for si in root.findall("m:si", NS):
        strings.append(
            "".join(
                t.text or ""
                for t in si.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")
            )
        )
    return strings


def _resolve_sheet_path(z: zipfile.ZipFile, sheet_name: str) -> str:
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    rid_to_target = {rel.get("Id"): rel.get("Target") for rel in rels}
    for sheet in wb.findall("m:sheets/m:sheet", NS):
        if sheet.get("name") != sheet_name:
            continue
        rid = sheet.get(f"{{{REL_NS['r'].split('}')[0][1:]}}}id")
        if rid is None:
            rid = sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        target = rid_to_target.get(rid, "")
        if target.startswith("/"):
            target = target.lstrip("/")
        if not target.startswith("xl/"):
            target = f"xl/{target}"
        return target
    raise ValueError(f"Sheet {sheet_name!r} not found in workbook")


def load_e9_rows(workbook: Path) -> list[GradeRow]:
    if not workbook.is_file():
        raise FileNotFoundError(workbook)

    with zipfile.ZipFile(workbook) as z:
        shared = _load_shared_strings(z)
        sheet_path = _resolve_sheet_path(z, SHEET_NAME)
        sheet = ET.fromstring(z.read(sheet_path))

    cells_by_row: dict[int, dict[str, str]] = {}
    for cell in sheet.findall(".//m:sheetData/m:row/m:c", NS):
        ref = cell.get("r")
        if not ref:
            continue
        col, row_num = _col_row(ref)
        value_el = cell.find("m:v", NS)
        if value_el is None or value_el.text is None:
            raw = ""
        elif cell.get("t") == "s":
            raw = shared[int(value_el.text)]
        else:
            raw = value_el.text
        cells_by_row.setdefault(row_num, {})[col] = raw.strip()

    rows: list[GradeRow] = []
    for row_num in sorted(cells_by_row):
        if row_num < 2:
            continue
        cols = cells_by_row[row_num]
        name = cols.get("A", "").strip()
        if not name:
            continue
        b_raw = cols.get("B", "").strip()
        c_raw = cols.get("C", "").strip()
        if not b_raw or not c_raw:
            print(f"Skip row {row_num} ({name!r}): missing B or C", file=sys.stderr)
            continue
        try:
            points = int(float(b_raw))
        except ValueError:
            print(f"Skip row {row_num} ({name!r}): bad points-bar {b_raw!r}", file=sys.stderr)
            continue
        if points < 0 or points > 8:
            print(
                f"Skip row {row_num} ({name!r}): points-bar {points} outside 0–8",
                file=sys.stderr,
            )
            continue
        rows.append(GradeRow(name=name, points_bar=points, paper_score=c_raw))
    return rows


class BrowserCLI:
    def __init__(self, cmd: str = BROWSER_CMD) -> None:
        self.cmd = cmd
        self._daemon = False

    @staticmethod
    def is_available(cmd: str = BROWSER_CMD) -> bool:
        return shutil.which(cmd) is not None

    def _run(self, args: list[str], *, json_out: bool = True) -> str:
        full = [self.cmd]
        if json_out:
            full.append("--json")
        full.extend(args)
        try:
            proc = subprocess.run(
                full,
                check=False,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise BrowserError(
                f"{self.cmd} not found. Install CLI-Anything browser harness."
            ) from exc
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            raise BrowserError(err or f"Command failed: {' '.join(full)}")
        return proc.stdout.strip()

    def _parse_json(self, stdout: str) -> object:
        if not stdout:
            return {}
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            return {"raw": stdout}

    def daemon_start(self) -> None:
        self._run(["session", "daemon-start"], json_out=False)
        self._daemon = True

    def daemon_stop(self) -> None:
        if not self._daemon:
            return
        try:
            self._run(["session", "daemon-stop"], json_out=False)
        finally:
            self._daemon = False

    def page_open(self, url: str) -> None:
        self._run(["page", "open", url], json_out=False)

    def grep(self, pattern: str) -> list[dict]:
        data = self._parse_json(self._run(["fs", "grep", pattern]))
        if isinstance(data, dict):
            for key in ("matches", "results", "entries"):
                if key in data and isinstance(data[key], list):
                    return [x for x in data[key] if isinstance(x, dict)]
            if "path" in data:
                return [data]
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        raw = data.get("raw", "") if isinstance(data, dict) else ""
        paths = re.findall(r"(/[\w\[\]/.\-]+)", raw)
        return [{"path": p, "text": pattern} for p in paths]

    def ls(self, path: str = "/") -> list[dict]:
        data = self._parse_json(self._run(["fs", "ls", path]))
        if isinstance(data, dict) and "entries" in data:
            entries = data["entries"]
            if isinstance(entries, list):
                return [e for e in entries if isinstance(e, dict)]
        return []

    def click(self, path: str) -> None:
        self._run(["act", "click", path], json_out=False)

    def type_text(self, path: str, text: str) -> None:
        self._run(["act", "type", path, text], json_out=False)


def _path_prefix(path: str) -> str:
    if "/" not in path:
        return path
    return path.rsplit("/", 1)[0]


def _ancestor_paths(path: str, depth: int = 6) -> list[str]:
    parts = [p for p in path.split("/") if p]
    paths: list[str] = []
    for i in range(len(parts), 0, -1):
        paths.append("/" + "/".join(parts[:i]))
        if len(paths) >= depth:
            break
    return paths


def _entry_label(entry: dict) -> str:
    for key in ("name", "text", "label", "value"):
        val = entry.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def _entry_path(entry: dict) -> str:
    path = entry.get("path") or entry.get("name")
    if isinstance(path, str) and path.startswith("/"):
        return path
    name = _entry_label(entry)
    if name.startswith("/"):
        return name
    return ""


def _score_button_path(row_entries: list[dict], points: int) -> str | None:
    target = str(points)
    for entry in row_entries:
        label = _entry_label(entry)
        role = str(entry.get("role", "")).lower()
        if label == target and role in ("button", "radio", "menuitem", "option", ""):
            path = _entry_path(entry)
            if path:
                return path
    for entry in row_entries:
        if _entry_label(entry) == target:
            path = _entry_path(entry)
            if path:
                return path
    return None


def _paper_score_path(row_entries: list[dict]) -> str | None:
    for entry in row_entries:
        label = _entry_label(entry).lower()
        role = str(entry.get("role", "")).lower()
        if "score or n/a" in label:
            path = _entry_path(entry)
            if path:
                return path
        if role in ("textbox", "searchbox", "combobox") and "score" in label:
            path = _entry_path(entry)
            if path:
                return path
    for entry in row_entries:
        role = str(entry.get("role", "")).lower()
        if role in ("textbox", "searchbox", "combobox"):
            path = _entry_path(entry)
            if path:
                return path
    return None


def collect_row_entries(browser: BrowserCLI, anchor_path: str) -> list[dict]:
    seen: set[str] = set()
    merged: list[dict] = []
    for base in _ancestor_paths(anchor_path):
        for entry in browser.ls(base):
            path = _entry_path(entry)
            key = path or json.dumps(entry, sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            merged.append(entry)
    return merged


def resolve_name_paths(browser: BrowserCLI, name: str) -> list[str]:
    matches = browser.grep(name)
    paths: list[str] = []
    for match in matches:
        path = match.get("path") or ""
        text = str(match.get("text", ""))
        if path and name.lower() in text.lower():
            paths.append(path)
        elif path and name.lower() in path.lower():
            paths.append(path)
    if not paths:
        for match in matches:
            path = match.get("path")
            if isinstance(path, str) and path.startswith("/"):
                paths.append(path)
    return paths


def fill_one(
    browser: BrowserCLI | None,
    row: GradeRow,
    *,
    apply: bool,
) -> str:
    if not apply:
        print(
            f"[dry-run] {row.name}: points-bar click {row.points_bar}; "
            f"paper score {row.paper_score!r}"
        )
        return "dry-run"

    assert browser is not None
    paths = resolve_name_paths(browser, row.name)
    if not paths:
        return f"skip {row.name}: name not found in gradebook"
    if len(paths) > 1:
        return f"skip {row.name}: ambiguous matches ({len(paths)})"

    entries = collect_row_entries(browser, paths[0])
    score_path = _score_button_path(entries, row.points_bar)
    paper_path = _paper_score_path(entries)

    if not score_path:
        return f"skip {row.name}: no points-bar button for {row.points_bar}"
    if not paper_path:
        return f"skip {row.name}: no Score or N/A field found"

    browser.click(score_path)
    browser.click(paper_path)
    browser.type_text(paper_path, row.paper_score)
    print(f"[applied] {row.name}: points-bar {row.points_bar}, paper {row.paper_score}")
    return "applied"


def main() -> int:
    args = parse_args()
    try:
        grades = load_e9_rows(args.workbook)
    except (OSError, ValueError) as exc:
        print(f"Workbook error: {exc}", file=sys.stderr)
        return 1

    if args.limit > 0:
        grades = grades[: args.limit]

    if not grades:
        print("No grade rows to process.", file=sys.stderr)
        return 1

    print(f"Loaded {len(grades)} row(s) from sheet {SHEET_NAME} in {args.workbook}")

    if not args.apply:
        for row in grades:
            fill_one(None, row, apply=False)
        print("Dry-run complete. Re-run with --apply to write to ManageBac.")
        return 0

    if not BrowserCLI.is_available():
        print(
            f"{BROWSER_CMD} not on PATH. Install CLI-Anything browser harness first.",
            file=sys.stderr,
        )
        return 1

    if not args.task_url.strip():
        print("--task-url is required when using --apply.", file=sys.stderr)
        return 1

    browser = BrowserCLI()
    try:
        browser.daemon_start()
        browser.page_open(args.task_url)
        counts = {"applied": 0, "dry-run": 0, "skip": 0}
        for row in grades:
            status = fill_one(browser, row, apply=True)
            if status.startswith("skip"):
                print(status, file=sys.stderr)
                counts["skip"] += 1
            else:
                counts["applied"] += 1
        print(
            f"Done: applied={counts['applied']} skipped={counts['skip']} "
            f"(sheet {SHEET_NAME})"
        )
    except BrowserError as exc:
        print(f"Browser error: {exc}", file=sys.stderr)
        return 1
    finally:
        browser.daemon_stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
