"""Shared readers for docx, text PDF, and picture PDF documents."""

from __future__ import annotations

import base64
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
import fitz

PICTURE_PAGE_ALNUM_LIMIT = 40
RUBRIC_PICTURE_PAGE_CAP = 15
STUDENT_IMAGE_CAP = 5

RUBRIC_EXTENSIONS = {".docx", ".pdf"}
STUDENT_EXTENSIONS = {".docx", ".pdf", ".png", ".jpg", ".jpeg", ".webp"}


def alphanumeric_count(text: str) -> int:
    return sum(1 for char in text if char.isalnum())


def page_is_picture(page: fitz.Page) -> bool:
    text = page.get_text() or ""
    has_images = bool(page.get_images(full=True))
    return has_images and alphanumeric_count(text) < PICTURE_PAGE_ALNUM_LIMIT


def is_picture_pdf(path: str | Path) -> bool:
    document = fitz.open(path)
    try:
        if document.page_count == 0:
            return False
        return all(page_is_picture(document[index]) for index in range(document.page_count))
    finally:
        document.close()


def _image_mime(path: Path) -> str:
    extension = path.suffix.lower().lstrip(".")
    if extension == "jpg":
        return "image/jpeg"
    return f"image/{extension}"


def _extract_text_image_blocks_in_order(element, rels) -> list[dict]:
    ordered_blocks: list[dict] = []
    text_parts: list[str] = []

    def flush_text() -> None:
        text = "".join(text_parts).strip()
        if text:
            ordered_blocks.append({"type": "text", "text": text})
        text_parts.clear()

    for node in element.iter():
        if node.tag == qn("a:blip"):
            flush_text()
            relationship_id = node.get(qn("r:embed"))
            if relationship_id and relationship_id in rels:
                image_part = rels[relationship_id].target_part
                content_type = image_part.content_type or "image/png"
                encoded = base64.b64encode(image_part.blob).decode("utf-8")
                ordered_blocks.append(
                    {"type": "image", "data": encoded, "mime": content_type}
                )
            continue
        if node.text:
            text_parts.append(node.text)
        if node.tail:
            text_parts.append(node.tail)
    flush_text()
    return ordered_blocks


def extract_docx(path: str | Path) -> list[dict]:
    document = Document(str(path))
    blocks: list[dict] = []
    relationships = document.part.rels
    for element in document.element.body:
        tag = element.tag.split("}")[-1]
        if tag == "p":
            blocks.extend(_extract_text_image_blocks_in_order(element, relationships))
        elif tag == "tbl":
            for row_index, row in enumerate(element.findall(".//" + qn("w:tr")), start=1):
                for col_index, cell in enumerate(row.findall(qn("w:tc")), start=1):
                    cell_blocks = _extract_text_image_blocks_in_order(cell, relationships)
                    if not cell_blocks:
                        continue
                    blocks.append(
                        {
                            "type": "text",
                            "text": f"[Table row {row_index}, col {col_index}]",
                        }
                    )
                    blocks.extend(cell_blocks)
    return blocks


def render_pdf_page_images(path: str | Path, max_pages: int) -> list[dict]:
    document = fitz.open(path)
    blocks: list[dict] = []
    try:
        page_count = min(document.page_count, max_pages)
        for index in range(page_count):
            pixmap = document[index].get_pixmap(dpi=150)
            encoded = base64.b64encode(pixmap.tobytes("png")).decode("utf-8")
            blocks.append(
                {
                    "type": "text",
                    "text": f"[Page {index + 1} image]",
                }
            )
            blocks.append({"type": "image", "data": encoded, "mime": "image/png"})
        if document.page_count > max_pages:
            blocks.append(
                {
                    "type": "text",
                    "text": f"[Truncated after {max_pages} of {document.page_count} pages]",
                }
            )
    finally:
        document.close()
    return blocks


def extract_pdf_text(path: str | Path) -> list[dict]:
    document = fitz.open(path)
    blocks: list[dict] = []
    try:
        for index in range(document.page_count):
            text = document[index].get_text().strip()
            if text:
                blocks.append({"type": "text", "text": f"[Page {index + 1}]\n{text}"})
    finally:
        document.close()
    return blocks


def extract_pdf(path: str | Path, *, max_picture_pages: int | None = None) -> list[dict]:
    if is_picture_pdf(path):
        limit = max_picture_pages if max_picture_pages is not None else RUBRIC_PICTURE_PAGE_CAP
        return render_pdf_page_images(path, limit)
    return extract_pdf_text(path)


def extract_image(path: str | Path) -> list[dict]:
    file_path = Path(path)
    encoded = base64.b64encode(file_path.read_bytes()).decode("utf-8")
    return [{"type": "image", "data": encoded, "mime": _image_mime(file_path)}]


def extract_file(path: str | Path, *, max_picture_pages: int | None = None) -> list[dict]:
    file_path = Path(path)
    extension = file_path.suffix.lower()
    if extension == ".docx":
        return extract_docx(file_path)
    if extension == ".pdf":
        return extract_pdf(file_path, max_picture_pages=max_picture_pages)
    if extension in {".png", ".jpg", ".jpeg", ".webp"}:
        return extract_image(file_path)
    raise ValueError(f"Unsupported file type: {extension}")


def document_text(blocks: list[dict]) -> str:
    return "\n".join(block["text"] for block in blocks if block["type"] == "text").strip()


def load_rubric_or_template(path: str | Path) -> tuple[str, list[dict]]:
    """Return text, or page images when the PDF is a picture PDF.

    Rubric and template files are .docx or .pdf only.
    """
    file_path = Path(path)
    extension = file_path.suffix.lower()
    if extension not in RUBRIC_EXTENSIONS:
        raise ValueError("Rubric and template files must be .docx or .pdf.")
    if not file_path.exists():
        raise FileNotFoundError(file_path)
    if extension == ".docx":
        return document_text(extract_docx(file_path)), []
    if is_picture_pdf(file_path):
        return "", render_pdf_page_images(file_path, RUBRIC_PICTURE_PAGE_CAP)
    return document_text(extract_pdf_text(file_path)), []


def submission_files(folder: Path) -> list[Path]:
    found: list[Path] = []
    for path in folder.iterdir():
        if not path.is_file() or path.name.startswith("~$"):
            continue
        if path.suffix.lower() in STUDENT_EXTENSIONS:
            found.append(path)
    return sorted(found, key=lambda item: item.name)


def extract_student_files(files: list[Path]) -> list[dict]:
    blocks: list[dict] = []
    for file_path in files:
        blocks.append({"type": "text", "text": f"[File: {file_path.name}]"})
        blocks.extend(extract_file(file_path, max_picture_pages=STUDENT_IMAGE_CAP))
    return blocks


def blocks_to_llm_content(blocks: list[dict], max_images: int = STUDENT_IMAGE_CAP) -> list[dict]:
    content: list[dict] = []
    image_count = 0
    dropped = 0
    for block in blocks:
        if block["type"] == "text":
            content.append({"type": "text", "text": block["text"]})
        elif block["type"] == "image":
            if image_count < max_images:
                mime = block["mime"] if "/" in block["mime"] else f"image/{block['mime']}"
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{block['data']}"},
                    }
                )
                image_count += 1
            else:
                dropped += 1
    if dropped:
        content.append(
            {
                "type": "text",
                "text": f"[{dropped} images omitted after the limit of {max_images}]",
            }
        )
    return content
