from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from docx import Document
from pypdf import PdfReader

from ..errors import ApiError, ErrorCode


SUPPORTED_EXTENSIONS = {".md", ".txt", ".pdf", ".docx"}
MIME_TYPES = {
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@dataclass(frozen=True)
class TextBlock:
    text: str
    page_number: int | None = None
    paragraph_index: int | None = None


def parse_document(filename: str, content: bytes) -> tuple[list[TextBlock], str]:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ApiError(ErrorCode.UNSUPPORTED_FILE, "仅支持 Markdown、TXT、PDF 和 DOCX 文件", 415)
    try:
        if extension in {".md", ".txt"}:
            text = content.decode("utf-8-sig")
            blocks = [TextBlock(line.strip(), paragraph_index=index) for index, line in enumerate(text.splitlines()) if line.strip()]
        elif extension == ".pdf":
            blocks = []
            for page_index, page in enumerate(PdfReader(BytesIO(content)).pages, start=1):
                for paragraph_index, line in enumerate((page.extract_text() or "").splitlines()):
                    if line.strip():
                        blocks.append(TextBlock(line.strip(), page_index, paragraph_index))
        else:
            blocks = [
                TextBlock(paragraph.text.strip(), paragraph_index=index)
                for index, paragraph in enumerate(Document(BytesIO(content)).paragraphs)
                if paragraph.text.strip()
            ]
    except Exception as exc:
        raise ApiError(ErrorCode.UNSUPPORTED_FILE, "文件损坏或无法解析", 415) from exc
    if not blocks or not any(block.text.strip() for block in blocks):
        message = "文件未提取到可检索文字；扫描版 PDF 请先执行 OCR"
        raise ApiError(ErrorCode.UNSUPPORTED_FILE, message, 415)
    return blocks, MIME_TYPES[extension]
